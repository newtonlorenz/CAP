"""Extraction orchestration: deterministic rules, optional AI and source anchoring."""

import asyncio
import inspect
import time
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.config import settings
from app.services.ai_provider import AIParser, ProviderConfig, create_parser
from app.services.rule_parser import OBLIGATION_RE, parse_requirements_rule_based
from app.services.section_parser import parse_section_blocks
from app.services.text_normalizer import normalize_for_match


@dataclass
class AIParseAttemptResult:
    items: list[dict]
    warnings: list[str]
    failed_chunks: int = 0


async def _maybe_log(event_logger, payload: dict) -> None:
    if not event_logger:
        return
    try:
        result = event_logger(payload)
        if inspect.isawaitable(result):
            await result
    except Exception:
        return


def get_parser(config: ProviderConfig | None = None) -> AIParser:
    """Build a parser from a snapshot; clients are never cached across runs."""
    return create_parser(config or ProviderConfig.from_settings(settings))


def _candidate_spans(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    candidates = list(lines)
    for i in range(len(lines) - 1):
        candidates.append(f"{lines[i]} {lines[i + 1]}".strip())
    for i in range(len(lines) - 2):
        candidates.append(f"{lines[i]} {lines[i + 1]} {lines[i + 2]}".strip())
    return candidates


def _anchor_ai_results(ai_results: list[dict], text: str, min_similarity: float) -> list[dict]:
    if not ai_results:
        return []
    candidates = _candidate_spans(text)
    normalized_candidates = [(cand, normalize_for_match(cand)) for cand in candidates]
    anchored: list[dict] = []
    for item in ai_results:
        raw_text = item.get("text", "")
        if not raw_text:
            continue
        norm_target = normalize_for_match(raw_text)
        best_ratio = 0.0
        best_text = None
        for candidate, norm_candidate in normalized_candidates:
            if not norm_candidate:
                continue
            ratio = SequenceMatcher(None, norm_target, norm_candidate).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_text = candidate
        anchored_item = dict(item)
        anchored_item.setdefault("parser_strategy", "ai_chunked")
        anchored_item.setdefault("source_excerpt", raw_text[:280])
        if best_text and best_ratio >= min_similarity:
            anchored_item["text"] = best_text
            if anchored_item.get("confidence", 1.0) < 0.7:
                anchored_item["needs_review"] = True
                anchored_item["review_reason"] = "low_confidence"
            anchored.append(anchored_item)
            continue
        anchored_item["needs_review"] = True
        anchored_item["review_reason"] = "anchor_mismatch"
        anchored.append(anchored_item)
    return anchored


def _chunk_text_for_ai(text: str, *, max_chunk_chars: int = 1500) -> list[str]:
    blocks = parse_section_blocks(text.splitlines())
    chunks: list[str] = []

    if blocks:
        for block in blocks:
            heading = f"{block.section_id} {block.title}".strip()
            body = "\n".join(line for line in block.lines if line is not None).strip()
            chunk = "\n".join(part for part in [heading, body] if part).strip()
            if not chunk:
                continue
            if len(chunk) <= max_chunk_chars:
                chunks.append(chunk)
                continue
            chunks.extend(_split_large_chunk(chunk, max_chunk_chars=max_chunk_chars))
        if chunks:
            return chunks

    return _split_large_chunk(text, max_chunk_chars=max_chunk_chars)


def _split_large_chunk(text: str, *, max_chunk_chars: int = 1500) -> list[str]:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in lines:
        line_len = len(line) + 1
        if current and current_len + line_len > max_chunk_chars:
            chunks.append("\n".join(current).strip())
            current = [line]
            current_len = line_len
            continue
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current).strip())
    return [chunk for chunk in chunks if chunk]


def _dedup_requirements(requirements: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    output: list[dict] = []
    for req in requirements:
        text_key = normalize_for_match(req.get("text", ""))
        parent_key = req.get("parent_reference") or ""
        key = (text_key, parent_key)
        if key in seen:
            continue
        seen.add(key)
        output.append(req)
    return output


def _normalize_requirement_payload(item: dict, *, strategy: str) -> dict:
    normalized = dict(item)
    normalized.setdefault("parser_strategy", strategy)
    normalized.setdefault("needs_review", False)
    normalized.setdefault("review_reason", None)
    normalized.setdefault("source_excerpt", (normalized.get("text") or "")[:280])
    normalized.setdefault("confidence", 0.8)
    if normalized.get("confidence", 0.0) < 0.7 and not normalized.get("needs_review"):
        normalized["needs_review"] = True
        normalized["review_reason"] = "low_confidence"
    return normalized


def _should_invoke_ai(rule_based: list[dict], text: str) -> bool:
    if not rule_based:
        return True
    if any(item.get("needs_review") for item in rule_based):
        return True
    if any(item.get("requirement_type") in ("mandatory", "recommended") for item in rule_based):
        return False
    return OBLIGATION_RE.search(text) is not None


async def _parse_ai_chunks_with_retry(
    *,
    parser: AIParser,
    text: str,
    document_type: str,
    page_number: int,
    min_similarity: float,
    event_logger=None,
) -> AIParseAttemptResult:
    chunks = _chunk_text_for_ai(text, max_chunk_chars=1500)
    all_items: list[dict] = []
    warnings: list[str] = []
    max_attempts = 3
    failed_chunks = 0

    for idx, chunk in enumerate(chunks, start=1):
        attempt = 0
        chunk_items: list[dict] = []
        succeeded = False
        while attempt < max_attempts:
            attempt += 1
            try:
                raw_items = await parser.parse(chunk, document_type, page_number)
                chunk_items = _anchor_ai_results(raw_items, chunk, min_similarity)
                succeeded = True
                break
            except TimeoutError:
                warning = (
                    f"AI timeout on chunk {idx}/{len(chunks)} (attempt {attempt}/{max_attempts})"
                )
                warnings.append(warning)
                await _maybe_log(
                    event_logger,
                    {
                        "stage": "ai_timeout",
                        "page_number": page_number,
                        "level": "warn",
                        "message": warning,
                    },
                )
            except Exception as exc:
                warning = f"AI error on chunk {idx}/{len(chunks)} (attempt {attempt}/{max_attempts}): {exc}"
                warnings.append(warning)
                await _maybe_log(
                    event_logger,
                    {
                        "stage": "ai_error",
                        "page_number": page_number,
                        "level": "warn",
                        "message": warning,
                    },
                )
            if attempt < max_attempts:
                await asyncio.sleep(2 ** (attempt - 1))
        if not succeeded:
            failed_chunks += 1
        all_items.extend(chunk_items)

    return AIParseAttemptResult(items=all_items, warnings=warnings, failed_chunks=failed_chunks)


async def parse_requirements_from_text(
    text: str,
    document_type: str,
    page_number: int,
    use_ai: bool = True,
    min_similarity: float = 0.85,
    event_logger=None,
    provider_config: ProviderConfig | None = None,
) -> list[dict]:
    """Parse requirements from text using rule-based extraction with AI fallback."""
    if not text.strip():
        return []

    rule_start = time.monotonic()
    await _maybe_log(
        event_logger,
        {"stage": "rule_parse_start", "page_number": page_number},
    )
    rule_based = parse_requirements_rule_based(text, document_type, page_number)
    rule_based = [
        _normalize_requirement_payload(item, strategy="rule_based") for item in rule_based
    ]
    await _maybe_log(
        event_logger,
        {
            "stage": "rule_parse_end",
            "page_number": page_number,
            "duration_ms": int((time.monotonic() - rule_start) * 1000),
            "message": f"{len(rule_based)} items",
        },
    )
    if (
        not use_ai
        or (provider_config.provider if provider_config else settings.ai_provider) == "none"
    ):
        return _dedup_requirements(rule_based)

    if not _should_invoke_ai(rule_based, text):
        return _dedup_requirements(rule_based)

    try:
        parser = get_parser(provider_config) if provider_config is not None else get_parser()
    except Exception as exc:
        await _maybe_log(
            event_logger,
            {
                "stage": "ai_error",
                "page_number": page_number,
                "level": "warn",
                "message": f"AI parser unavailable: {exc}",
            },
        )
        raise ValueError("The configured extraction provider is unavailable.") from exc
    ai_start = time.monotonic()
    await _maybe_log(
        event_logger,
        {"stage": "ai_parse_start", "page_number": page_number},
    )
    ai_attempt = await _parse_ai_chunks_with_retry(
        parser=parser,
        text=text,
        document_type=document_type,
        page_number=page_number,
        min_similarity=min_similarity if min_similarity is not None else 0.85,
        event_logger=event_logger,
    )
    ai_results = [
        _normalize_requirement_payload(item, strategy="ai_chunked") for item in ai_attempt.items
    ]
    await _maybe_log(
        event_logger,
        {
            "stage": "ai_parse_end",
            "page_number": page_number,
            "duration_ms": int((time.monotonic() - ai_start) * 1000),
            "message": f"{len(ai_results)} items ({len(ai_attempt.warnings)} warnings)",
        },
    )

    if ai_attempt.failed_chunks:
        raise ValueError(
            "AI extraction was incomplete; retry the document or disable AI for a local draft."
        )

    if not rule_based:
        return _dedup_requirements(ai_results)

    merged = list(rule_based)
    index_by_ref = {
        r.get("reference_id"): idx for idx, r in enumerate(merged) if r.get("reference_id")
    }
    existing_keys = {(r.get("reference_id"), r.get("text")) for r in merged}

    for item in ai_results:
        ref = item.get("reference_id")
        key = (ref, item.get("text"))
        if key in existing_keys:
            continue

        if ref and ref in index_by_ref:
            existing = merged[index_by_ref[ref]]
            should_replace = existing.get("requirement_type") == "informational" or (
                existing.get("title") and existing.get("text") == existing.get("title")
            )
            if should_replace:
                merged_item = dict(item)
                if not merged_item.get("title"):
                    merged_item["title"] = existing.get("title")
                if not merged_item.get("parent_reference"):
                    merged_item["parent_reference"] = existing.get("parent_reference")
                merged[index_by_ref[ref]] = merged_item
                existing_keys.add(key)
                continue

        merged.append(item)
        existing_keys.add(key)

    await _maybe_log(
        event_logger,
        {
            "stage": "merge",
            "page_number": page_number,
            "message": f"{len(merged)} items",
        },
    )
    return _dedup_requirements(merged)


async def parse_requirements_ai_only(
    text: str,
    document_type: str,
    page_number: int,
    min_similarity: float = 0.85,
    event_logger=None,
    provider_config: ProviderConfig | None = None,
) -> list[dict]:
    """Parse requirements using AI only (no rule-based parsing).

    Use this path when extraction must omit local numbered-section heuristics.
    """
    if not text.strip():
        return []

    if (provider_config.provider if provider_config else settings.ai_provider) == "none":
        raise ValueError("This document requires an enabled extraction provider.")

    try:
        parser = get_parser(provider_config) if provider_config is not None else get_parser()
    except Exception as exc:
        await _maybe_log(
            event_logger,
            {
                "stage": "ai_error",
                "page_number": page_number,
                "level": "warn",
                "message": f"AI parser unavailable: {exc}",
            },
        )
        raise ValueError("The configured extraction provider is unavailable.") from exc
    ai_start = time.monotonic()
    await _maybe_log(
        event_logger,
        {"stage": "ai_parse_start", "page_number": page_number},
    )
    ai_attempt = await _parse_ai_chunks_with_retry(
        parser=parser,
        text=text,
        document_type=document_type,
        page_number=page_number,
        min_similarity=min_similarity if min_similarity is not None else 0.85,
        event_logger=event_logger,
    )
    if ai_attempt.failed_chunks:
        raise ValueError(
            "AI extraction was incomplete; retry the document or choose another provider."
        )
    ai_results = [
        _normalize_requirement_payload(item, strategy="ai_chunked") for item in ai_attempt.items
    ]
    await _maybe_log(
        event_logger,
        {
            "stage": "ai_parse_end",
            "page_number": page_number,
            "duration_ms": int((time.monotonic() - ai_start) * 1000),
            "message": f"{len(ai_results)} items ({len(ai_attempt.warnings)} warnings)",
        },
    )
    for req in ai_results:
        req.setdefault("page_number", page_number)
    return _dedup_requirements(ai_results)
