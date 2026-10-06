from __future__ import annotations

import asyncio
import base64
import os
import signal
import sys
import tempfile
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from app.config import settings
from app.services.ai_provider import ProviderConfig, create_parser, parse_candidates
from app.services.document_reader import default_reader
from app.services.text_normalizer import normalize_for_match

VISION_EXTRACTION_PROMPT = """You are extracting regulatory requirements from a PDF page image.

Return ONLY JSON with:
{{
  "requirements": [
    {{
      "reference_id": string|null,
      "title": string|null,
      "text": string,
      "requirement_type": "mandatory"|"recommended"|"informational",
      "parent_reference": string|null,
      "confidence": number
    }}
  ]
}}

Rules:
- Extract requirement statements only.
- Preserve source wording.
- "shall", "must", "required" => mandatory.
- "should", "may" => recommended.
- Confidence below 0.70 if uncertain.
- If section numbering appears corrupted, still extract text and set best-effort reference.

Document type: {document_type}
Page number: {page_number}

Native extracted text for anchoring context:
{page_text}
"""


VISION_JSON_SCHEMA = {
    "name": "vision_requirements",
    "schema": {
        "type": "object",
        "properties": {
            "requirements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "reference_id": {"type": ["string", "null"]},
                        "title": {"type": ["string", "null"]},
                        "text": {"type": "string"},
                        "requirement_type": {"type": "string"},
                        "parent_reference": {"type": ["string", "null"]},
                        "confidence": {"type": "number"},
                    },
                    "required": [
                        "reference_id",
                        "title",
                        "text",
                        "requirement_type",
                        "parent_reference",
                        "confidence",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["requirements"],
        "additionalProperties": False,
    },
}


@dataclass
class VisionParseResult:
    items: list[dict]
    warnings: list[str]


async def parse_requirements_from_page_image(
    *,
    file_path: str,
    page_number: int,
    document_type: str,
    page_text: str,
    event_logger=None,
    provider_config: ProviderConfig | None = None,
    deadline: float | None = None,
) -> VisionParseResult:
    if not settings.vision_fallback_enabled:
        return VisionParseResult(items=[], warnings=[])
    try:
        config = provider_config or ProviderConfig.from_settings(settings)
        if config.provider == "none":
            return VisionParseResult(items=[], warnings=[])
        parser = create_parser(config)
    except ValueError as exc:
        return VisionParseResult(items=[], warnings=[str(exc)])

    deadline = deadline if deadline is not None else time.monotonic() + settings.extraction_page_timeout_seconds
    try:
        image_data_uri = await _bounded_render_page_png_data_uri(
            file_path,
            page_number,
            dpi=settings.vision_fallback_render_dpi,
            timeout=min(settings.pdf_preprocess_timeout_seconds, _remaining_time(deadline)),
        )
    except TimeoutError:
        raise
    except Exception as exc:
        warning = f"Vision render failed: {exc}"
        await _log(event_logger, "ai_error", page_number, warning, level="warn")
        return VisionParseResult(items=[], warnings=[warning])

    prompt = VISION_EXTRACTION_PROMPT.format(
        document_type=document_type,
        page_number=page_number,
        page_text=(page_text or "")[:6000],
    )

    warnings: list[str] = []
    attempts = 0
    max_attempts = 2
    raw = ""
    while attempts < max_attempts:
        attempts += 1
        try:
            raw = await asyncio.wait_for(
                parser.complete(
                    prompt, VISION_JSON_SCHEMA, image_uri=image_data_uri, max_tokens=2500
                ),
                timeout=min(config.timeout, _remaining_time(deadline)),
            )
            break
        except TimeoutError:
            if time.monotonic() >= deadline:
                raise
            warning = f"Vision fallback timeout on attempt {attempts}/{max_attempts}"
            warnings.append(warning)
            await _log(event_logger, "ai_timeout", page_number, warning, level="warn")
        except Exception as exc:
            warning = f"Vision fallback error on attempt {attempts}/{max_attempts}: {exc}"
            warnings.append(warning)
            await _log(event_logger, "ai_error", page_number, warning, level="warn")
        if attempts < max_attempts:
            await asyncio.sleep(min(2 ** (attempts - 1), _remaining_time(deadline)))

    if not raw:
        return VisionParseResult(items=[], warnings=warnings)

    try:
        candidates = parse_candidates(raw, page_number)
    except ValueError as exc:
        return VisionParseResult(items=[], warnings=warnings + [str(exc)])
    parsed = _vision_candidates(candidates)
    anchored = _anchor_requirements(parsed, page_text)
    return VisionParseResult(items=anchored, warnings=warnings)


def _remaining_time(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Vision page deadline exceeded")
    return remaining


async def _bounded_render_page_png_data_uri(
    file_path: str, page_number: int, *, dpi: int, timeout: float
) -> str:
    # A thread cannot interrupt native PDFium work. Isolate it in a process group
    # so cancellation and deadline expiry can terminate the renderer and its children.
    deadline = time.monotonic() + timeout
    with tempfile.TemporaryDirectory(prefix="cap-vision-") as staging:
        output = Path(staging) / "page.png"
        spawn = asyncio.create_task(asyncio.create_subprocess_exec(
            sys.executable, "-m", "app.services.vision_parser", "--render",
            str(Path(file_path).resolve()), str(page_number), str(dpi), str(output),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
            env=dict(os.environ, TMPDIR=staging, PYTHONPATH=str(Path(__file__).resolve().parents[2])
                     + os.pathsep + os.environ.get("PYTHONPATH", "")),
        ))
        process = None
        try:
            process = await asyncio.shield(spawn)
            await asyncio.wait_for(process.wait(), timeout=_remaining_time(deadline))
            if process.returncode != 0 or not output.exists():
                raise ValueError("PDF page rendering failed")
            if output.stat().st_size > 32 * 1024 * 1024:
                raise ValueError("Rendered PDF page exceeds the safe output limit")
            encoded = base64.b64encode(output.read_bytes()).decode("ascii")
            _remaining_time(deadline)
            return f"data:image/png;base64,{encoded}"
        finally:
            # A cancellation during process creation must still reap the child.
            if process is None:
                process = await asyncio.shield(spawn)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if process.returncode is None:
                await process.wait()


def _render_child() -> None:
    import resource

    _, file_path, page_number, dpi, output = sys.argv[1:]
    cpu_limit = max(1, int(settings.pdf_preprocess_timeout_seconds))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit + 1))
    resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024 * 1024, 32 * 1024 * 1024))
    if sys.platform.startswith("linux"):
        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    Path(output).write_bytes(default_reader.render_png(file_path, int(page_number), dpi=int(dpi)))


def _vision_candidates(candidates: list[dict]) -> list[dict]:
    output = []
    for candidate in candidates:
        confidence = candidate["confidence"]
        low_confidence = confidence < settings.vision_fallback_confidence_threshold
        output.append(dict(
            candidate,
            parser_strategy="vision",
            source_excerpt=candidate["text"][:280],
            needs_review=low_confidence,
            review_reason="low_confidence" if low_confidence else None,
        ))
    return output


def _candidate_spans(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    candidates = list(lines)
    for i in range(len(lines) - 1):
        candidates.append(f"{lines[i]} {lines[i + 1]}".strip())
    for i in range(len(lines) - 2):
        candidates.append(f"{lines[i]} {lines[i + 1]} {lines[i + 2]}".strip())
    return candidates


def _anchor_requirements(items: list[dict], page_text: str) -> list[dict]:
    candidates = _candidate_spans(page_text or "")
    normalized_candidates = [
        (candidate, normalize_for_match(candidate)) for candidate in candidates
    ]
    anchored: list[dict] = []
    for item in items:
        text = item.get("text") or ""
        target = normalize_for_match(text)
        best_ratio = 0.0
        best_text: str | None = None
        for candidate, candidate_norm in normalized_candidates:
            if not candidate_norm:
                continue
            ratio = SequenceMatcher(None, target, candidate_norm).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_text = candidate
        normalized = dict(item)
        if best_text and best_ratio >= settings.vision_anchor_min_similarity:
            normalized["text"] = best_text
            normalized["source_excerpt"] = best_text[:280]
        else:
            normalized["needs_review"] = True
            normalized["review_reason"] = "anchor_mismatch"
        anchored.append(normalized)
    return _dedupe_items(anchored)


def _dedupe_items(items: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    output: list[dict] = []
    for item in items:
        ref = str(item.get("reference_id") or "")
        key = (normalize_for_match(item.get("text", "")), ref)
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


async def _log(event_logger, stage: str, page_number: int, message: str, *, level: str) -> None:
    if not event_logger:
        return
    result = event_logger(
        {
            "stage": stage,
            "page_number": page_number,
            "message": message,
            "level": level,
        }
    )
    if hasattr(result, "__await__"):
        await result


if __name__ == "__main__":
    if len(sys.argv) != 6 or sys.argv[1] != "--render":
        raise SystemExit("Expected --render SOURCE PAGE DPI OUTPUT")
    _render_child()
