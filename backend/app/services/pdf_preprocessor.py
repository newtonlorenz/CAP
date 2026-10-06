from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import os
import re
import shutil
import tempfile
from statistics import mean
from typing import Any, Callable, Optional

from app.config import settings
from app.services.pdf_parser import PdfParser
from app.services.ocr_service import run_ocr_with_fallback
from app.services.pdf_layout import extract_layout_pages
from app.services.section_parser import infer_numbered_rows, parse_section_blocks


SECTION_INLINE_RE = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+\S+")
SECTION_ID_ONLY_RE = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s*$")
LIST_MARKER_RE = re.compile(r"^\s*(\d{1,3}|[a-zA-Z]|[ivxlcdm]+)(?:[\)\.])?\s*$", re.IGNORECASE)
OBLIGATION_RE = re.compile(r"\b(shall|must|should|may|required)\b", re.IGNORECASE)
NOISE_TOKEN_RE = re.compile(r"\btt\b|,\d+|\d+,", re.IGNORECASE)


@dataclass
class PageQuality:
    page_number: int
    char_count: int
    word_count: int
    heading_candidate_count: int
    section_block_count: int
    recovered_row_count: int
    obligation_sentence_count: int
    heading_continuity_score: float
    section_id_success_score: float
    table_row_recovery_score: float
    requirement_sentence_score: float
    glyph_corruption_score: float
    parseability_score: float
    has_text_layer: bool
    is_separator: bool
    is_low_quality: bool


@dataclass
class PreprocessResult:
    pages: list[dict[str, Any]]
    page_quality: list[PageQuality]
    low_quality_pages: list[int]
    ocr_applied: bool
    ocr_pages: int
    warning_count: int
    warnings: list[str]
    family_fingerprint: Optional[str]
    cleanup_paths: list[str]
    parseability_score: float
    fallback_trigger_reason: Optional[str]
    diagnostics: dict[str, Any]
    structured_requirements: Optional[list[dict[str, Any]]] = None
    ocr_pdf_path: Optional[str] = None


async def preprocess_pdf_for_extraction(
    file_path: str,
    adapter: PdfParser,
    document_type: str,
    event_logger: Optional[Callable[[dict], object]] = None,
) -> PreprocessResult:
    async def _log(stage: str, message: str, **extra) -> None:
        if event_logger is None:
            return
        payload = {"stage": stage, "message": message}
        payload.update(extra)
        result = event_logger(payload)
        if hasattr(result, "__await__"):
            await result

    await _log("preprocess_start", "Analyzing parseability and canonical layout")

    pages = _extract_pages_with_layout(file_path, adapter)
    quality = [_analyze_page(page) for page in pages]
    non_separator = [item for item in quality if not item.is_separator]
    low_quality_pages = [item.page_number for item in non_separator if item.is_low_quality]
    low_quality_ratio = len(low_quality_pages) / max(1, len(non_separator))
    parseability_score = (
        mean(item.parseability_score for item in non_separator) if non_separator else 0.0
    )

    image_only_pages = [
        item.page_number
        for item in quality
        if not item.has_text_layer and item.char_count < 40
    ]
    # A scanned page has no text and otherwise looks like a separator here.
    image_only_ratio = len(image_only_pages) / max(1, len(quality))

    warnings: list[str] = []
    cleanup_paths: list[str] = []
    ocr_applied = False
    ocr_pages = 0
    ocr_reason = ""
    ocr_pdf_path: Optional[str] = None

    should_ocr, ocr_reason = _should_run_ocr(
        mode=settings.ocr_mode,
        enabled=settings.ocr_enabled,
        image_only_ratio=image_only_ratio,
    )

    if should_ocr:
        await _log("ocr_start", f"Applying OCR rescue path ({ocr_reason})")
        temp_dir = tempfile.mkdtemp(prefix="cap-ocr-")
        cleanup_paths.append(temp_dir)
        ocr_result = run_ocr_with_fallback(
            file_path,
            work_dir=temp_dir,
            languages=settings.ocr_languages,
            timeout_seconds=settings.ocr_timeout_seconds,
        )
        if ocr_result.applied and ocr_result.output_path:
            ocr_pdf_path = ocr_result.output_path
            pages = _extract_pages_with_layout(ocr_result.output_path, adapter)
            quality = [_analyze_page(page) for page in pages]
            non_separator = [item for item in quality if not item.is_separator]
            low_quality_pages = [item.page_number for item in non_separator if item.is_low_quality]
            low_quality_ratio = len(low_quality_pages) / max(1, len(non_separator))
            parseability_score = (
                mean(item.parseability_score for item in non_separator) if non_separator else 0.0
            )
            ocr_applied = True
            ocr_pages = len(image_only_pages)
            await _log("ocr_end", "OCR rescue path completed")
        else:
            warning = ocr_result.error or "OCR rescue path failed"
            warnings.append(warning)
            await _log("ocr_skipped", warning, level="warn")
    else:
        if image_only_pages:
            await _log("ocr_skipped", f"OCR rescue skipped ({ocr_reason})")
        else:
            await _log("ocr_not_applicable", "No image-only pages detected")

    fallback_trigger_reason = _vision_fallback_reason(
        low_quality_ratio=low_quality_ratio,
        low_quality_pages=low_quality_pages,
    )
    await _log(
        "fallback_decision",
        fallback_trigger_reason or "Vision fallback not required",
        low_quality_ratio=round(low_quality_ratio, 3),
        parseability_score=round(parseability_score, 3),
    )

    family_fingerprint = build_family_fingerprint(pages, document_type=document_type)
    diagnostics = _build_diagnostics_payload(
        quality=quality,
        pages=pages,
        parseability_score=parseability_score,
        low_quality_ratio=low_quality_ratio,
        low_quality_pages=low_quality_pages,
        fallback_trigger_reason=fallback_trigger_reason,
        ocr_reason=ocr_reason,
    )

    await _log(
        "preprocess_end",
        (
            f"Preprocessing complete "
            f"(parseability={parseability_score:.2f}, low-quality pages={len(low_quality_pages)})"
        ),
    )

    return PreprocessResult(
        pages=pages,
        page_quality=quality,
        low_quality_pages=low_quality_pages,
        ocr_applied=ocr_applied,
        ocr_pages=ocr_pages,
        warning_count=len(warnings),
        warnings=warnings,
        family_fingerprint=family_fingerprint,
        cleanup_paths=cleanup_paths,
        parseability_score=parseability_score,
        fallback_trigger_reason=fallback_trigger_reason,
        diagnostics=diagnostics,
        ocr_pdf_path=ocr_pdf_path,
    )


def cleanup_preprocess_artifacts(paths: list[str]) -> None:
    for path in paths:
        if not path:
            continue
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)


def build_family_fingerprint(pages: list[dict[str, Any]], *, document_type: str) -> Optional[str]:
    tokens: list[str] = []
    for page in pages[:3]:
        lines = [line.strip() for line in (page.get("text") or "").splitlines() if line.strip()]
        for line in lines:
            lower = line.lower()
            if lower.startswith("page "):
                continue
            if "table of contents" in lower:
                continue
            if len(line) < 8:
                continue
            tokens.append(line)
            if len(tokens) >= 6:
                break
        if len(tokens) >= 6:
            break

    if not tokens:
        return None

    normalized = " ".join(tokens).lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return None

    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
    prefix = " ".join(normalized.split()[:6]).replace(" ", "-")
    return f"{document_type}:{prefix}:{digest}"[:160]


def _extract_pages_with_layout(
    file_path: str, adapter: PdfParser
) -> list[dict[str, Any]]:
    native_pages = adapter.extract_pages(file_path)
    try:
        layout_pages = extract_layout_pages(file_path)
    except Exception:
        return native_pages
    return _merge_layout_and_native(layout_pages, native_pages)


def _merge_layout_and_native(
    layout_pages: list[dict[str, Any]],
    native_pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    native_by_page = {int(page.get("page_number", 0)): page for page in native_pages}
    output: list[dict[str, Any]] = []
    for page in layout_pages:
        page_number = int(page.get("page_number", 0))
        native = native_by_page.get(page_number, {})
        native_text = native.get("text") or ""
        table_blocks = _extract_table_blocks(native_text)
        text = page.get("text") or native_text
        continuation = re.search(r"(?m)^\s*(\[SECTION_CONTINUATION:[^\]]+\])", native_text)
        if continuation and not text.lstrip().startswith("[SECTION_CONTINUATION:"):
            text = continuation.group(1) + "\n" + text
        if table_blocks:
            text = "\n".join([text] + table_blocks).strip()
        output.append(
            {
                "page_number": page_number,
                "text": text,
                "layout_lines": page.get("layout_lines", []),
                "word_count": int(page.get("word_count", 0)),
            }
        )

    present = {page["page_number"] for page in output}
    output.extend(page for page in native_pages if page["page_number"] not in present)
    return sorted(output, key=lambda page: page["page_number"])


def _extract_table_blocks(text: str) -> list[str]:
    if "[TABLE]" not in text:
        return []
    blocks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.strip().startswith(("[TABLE]", "[TABLE_SECTION:")):
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            current.append(line.strip())
            continue
        if current:
            current.append(line)
    if current:
        blocks.append("\n".join(current).strip())
    return [block for block in blocks if block.strip()]


def _should_run_ocr(*, mode: str, enabled: bool, image_only_ratio: float) -> tuple[bool, str]:
    if not enabled:
        return False, "disabled"

    normalized_mode = (mode or "image_only").strip().lower()
    if normalized_mode == "manual":
        return False, "manual mode"
    if normalized_mode == "always":
        return True, "always mode"
    if normalized_mode in {"image_only", "adaptive"}:
        if image_only_ratio >= settings.ocr_image_page_ratio_threshold:
            return True, f"image-only ratio {image_only_ratio:.2f}"
        return False, f"image-only ratio {image_only_ratio:.2f} below threshold"

    return False, f"unsupported OCR mode '{normalized_mode}'"


def _vision_fallback_reason(
    *, low_quality_ratio: float, low_quality_pages: list[int]
) -> Optional[str]:
    if not settings.vision_fallback_enabled:
        return None
    if low_quality_ratio < settings.parseability_low_ratio_threshold:
        return None
    return (
        f"Low parseability ratio {low_quality_ratio:.2f} "
        f"across pages {','.join(str(p) for p in low_quality_pages[:8])}"
    )


def _analyze_page(page: dict[str, Any]) -> PageQuality:
    text = page.get("text") or ""
    lines = [line for line in text.splitlines() if line.strip()]
    char_count = len(text)
    word_count = int(page.get("word_count") or len(re.findall(r"\b\w+\b", text)))
    has_text_layer = word_count > 0

    heading_candidate_count = sum(
        1
        for line in lines
        if SECTION_INLINE_RE.match(line.strip()) or SECTION_ID_ONLY_RE.match(line.strip())
    )
    malformed_section_candidates = sum(
        1
        for line in lines
        if re.match(r"^\s*\d+(?:\.[A-Za-z0-9]+)+", line.strip())
        and not SECTION_INLINE_RE.match(line.strip())
    )

    section_blocks = parse_section_blocks(lines)
    recovered_rows = infer_numbered_rows(lines)
    obligation_sentence_count = len(OBLIGATION_RE.findall(text))
    glyph_corruption_ratio = _glyph_corruption_ratio(text)

    is_toc = "table of contents" in text.lower() or text.lower().strip().startswith("contents")
    list_marker_count = sum(
        1
        for line in lines
        if LIST_MARKER_RE.match(line.strip()) or line.strip().startswith(("•", "-"))
    )
    has_obligation = obligation_sentence_count > 0
    is_separator = (
        is_toc
        or (char_count < 120 and not has_obligation and heading_candidate_count <= 1)
        or (char_count < 180 and heading_candidate_count <= 1 and list_marker_count <= 1)
    )

    heading_continuity_score = _heading_continuity_score(section_blocks)
    section_id_success_score = _section_id_success_score(
        heading_candidate_count, malformed_section_candidates
    )
    table_row_recovery_score = _table_row_recovery_score(lines, len(recovered_rows))
    requirement_sentence_score = _requirement_sentence_score(lines, obligation_sentence_count)
    glyph_corruption_score = min(1.0, glyph_corruption_ratio * 10.0)

    parseability_score = max(
        0.0,
        min(
            1.0,
            (0.25 * heading_continuity_score)
            + (0.25 * section_id_success_score)
            + (0.2 * table_row_recovery_score)
            + (0.2 * requirement_sentence_score)
            + (0.1 * (1.0 - glyph_corruption_score)),
        ),
    )

    is_low_quality = (not is_separator) and (
        parseability_score < settings.parseability_low_page_threshold
    )

    return PageQuality(
        page_number=int(page.get("page_number") or 0),
        char_count=char_count,
        word_count=word_count,
        heading_candidate_count=heading_candidate_count,
        section_block_count=len(section_blocks),
        recovered_row_count=len(recovered_rows),
        obligation_sentence_count=obligation_sentence_count,
        heading_continuity_score=heading_continuity_score,
        section_id_success_score=section_id_success_score,
        table_row_recovery_score=table_row_recovery_score,
        requirement_sentence_score=requirement_sentence_score,
        glyph_corruption_score=glyph_corruption_score,
        parseability_score=parseability_score,
        has_text_layer=has_text_layer,
        is_separator=is_separator,
        is_low_quality=is_low_quality,
    )


def _glyph_corruption_ratio(text: str) -> float:
    tokens = re.findall(r"\b[a-zA-Z0-9]+\b", text)
    if not tokens:
        return 0.0
    noise_count = len(NOISE_TOKEN_RE.findall(text))
    return noise_count / max(1, len(tokens))


def _heading_continuity_score(section_blocks: list[Any]) -> float:
    if not section_blocks:
        return 0.0
    numeric_ids: list[list[int]] = []
    for block in section_blocks:
        raw = getattr(block, "section_id", "")
        if not raw or raw.lower().startswith("article"):
            continue
        if not re.fullmatch(r"\d+(?:\.\d+)*", raw):
            continue
        numeric_ids.append([int(part) for part in raw.split(".") if part.isdigit()])
    if len(numeric_ids) <= 1:
        return 0.6 if numeric_ids else 0.0

    contiguous = 0
    pairs = 0
    for left, right in zip(numeric_ids, numeric_ids[1:]):
        pairs += 1
        if _section_not_regressing(left, right):
            contiguous += 1
    return contiguous / max(1, pairs)


def _section_not_regressing(left: list[int], right: list[int]) -> bool:
    common = min(len(left), len(right))
    for idx in range(common):
        if right[idx] > left[idx]:
            return True
        if right[idx] < left[idx]:
            return False
    return len(right) >= len(left)


def _section_id_success_score(heading_count: int, malformed_count: int) -> float:
    if heading_count == 0 and malformed_count == 0:
        return 0.0
    return heading_count / max(1, heading_count + malformed_count)


def _table_row_recovery_score(lines: list[str], recovered_rows: int) -> float:
    if not lines:
        return 0.0
    marker_like = sum(1 for line in lines if LIST_MARKER_RE.match(line.strip()))
    if marker_like == 0:
        return 0.7
    return min(1.0, recovered_rows / max(1, marker_like))


def _requirement_sentence_score(lines: list[str], obligation_sentence_count: int) -> float:
    candidate_sentences = max(1, sum(1 for line in lines if line.strip().endswith((".", ";", ":"))))
    return min(1.0, obligation_sentence_count / candidate_sentences)


def _build_diagnostics_payload(
    *,
    quality: list[PageQuality],
    pages: list[dict[str, Any]],
    parseability_score: float,
    low_quality_ratio: float,
    low_quality_pages: list[int],
    fallback_trigger_reason: Optional[str],
    ocr_reason: str,
) -> dict[str, Any]:
    page_metrics = [asdict(item) for item in quality]
    canonical_blocks: list[dict[str, Any]] = []
    for page in pages:
        canonical_blocks.append(
            {
                "page_number": page.get("page_number"),
                "line_count": len(page.get("layout_lines") or []),
                "lines": (page.get("layout_lines") or [])[:180],
            }
        )

    return {
        "parseability_score": parseability_score,
        "low_parseability_ratio": low_quality_ratio,
        "low_parseability_pages": low_quality_pages,
        "fallback_trigger_reason": fallback_trigger_reason,
        "ocr_reason": ocr_reason,
        "page_metrics": page_metrics,
        "canonical_blocks": canonical_blocks,
    }
