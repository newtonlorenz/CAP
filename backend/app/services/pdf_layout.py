from __future__ import annotations

import re
from typing import Any

from app.services.document_reader import default_reader

from app.services.text_normalizer import (
    collapse_whitespace,
    dehyphenate_lines,
    merge_inline_hyphenation,
)


_Y_TOLERANCE = 2.5
_COLUMN_GAP_RATIO = 0.2


def extract_layout_pages(file_path: str) -> list[dict[str, Any]]:
    """Extract born-digital text with line coordinates and stable reading order."""
    pages: list[dict[str, Any]] = []
    for page in default_reader.read_layout(file_path):
        words = page["words"]
        pages.append({
            "page_number": page["page_number"],
            "lines": _build_lines(words, page["width"]),
            "word_count": len(words),
            "page_width": page["width"], "page_height": page["height"],
        })

    _strip_repeated_headers_and_footers(pages)

    output: list[dict[str, Any]] = []
    for page in pages:
        normalized_lines = _normalize_lines_for_text(page["lines"])
        output.append(
            {
                "page_number": page["page_number"],
                "text": "\n".join(normalized_lines),
                "layout_lines": page["lines"],
                "word_count": page["word_count"],
                "page_width": page["page_width"],
                "page_height": page["page_height"],
            }
        )
    return output


def _build_lines(words: list[tuple], page_width: float) -> list[dict[str, Any]]:
    if not words:
        return []

    sorted_words = sorted(words, key=lambda w: (float(w[1]), float(w[0])))
    grouped: list[list[tuple]] = []

    for word in sorted_words:
        y0 = float(word[1])
        if not grouped:
            grouped.append([word])
            continue
        prev = grouped[-1][-1]
        prev_y0 = float(prev[1])
        if abs(y0 - prev_y0) <= _Y_TOLERANCE:
            grouped[-1].append(word)
        else:
            grouped.append([word])

    lines: list[dict[str, Any]] = []
    for group in grouped:
        ordered = sorted(group, key=lambda w: float(w[0]))
        text = " ".join(str(w[4]) for w in ordered if str(w[4]).strip()).strip()
        if not text:
            continue
        lines.append(
            {
                "text": text,
                "x0": float(min(w[0] for w in ordered)),
                "y0": float(min(w[1] for w in ordered)),
                "x1": float(max(w[2] for w in ordered)),
                "y1": float(max(w[3] for w in ordered)),
            }
        )

    ordered_lines = _order_lines(lines, page_width)
    for idx, line in enumerate(ordered_lines, start=1):
        line["line_number"] = idx
    return ordered_lines


def _order_lines(lines: list[dict[str, Any]], page_width: float) -> list[dict[str, Any]]:
    if len(lines) < 8:
        return sorted(lines, key=lambda line: (line["y0"], line["x0"]))

    x_positions = sorted(line["x0"] for line in lines)
    gaps = [x_positions[idx + 1] - x_positions[idx] for idx in range(len(x_positions) - 1)]
    if not gaps:
        return sorted(lines, key=lambda line: (line["y0"], line["x0"]))

    max_gap = max(gaps)
    if max_gap <= page_width * _COLUMN_GAP_RATIO:
        return sorted(lines, key=lambda line: (line["y0"], line["x0"]))

    split_index = gaps.index(max_gap)
    split_x = (x_positions[split_index] + x_positions[split_index + 1]) / 2
    left = [line for line in lines if line["x0"] <= split_x]
    right = [line for line in lines if line["x0"] > split_x]

    if not left or not right:
        return sorted(lines, key=lambda line: (line["y0"], line["x0"]))

    if min(len(left), len(right)) < max(2, int(len(lines) * 0.2)):
        return sorted(lines, key=lambda line: (line["y0"], line["x0"]))

    left_sorted = sorted(left, key=lambda line: (line["y0"], line["x0"]))
    right_sorted = sorted(right, key=lambda line: (line["y0"], line["x0"]))
    return left_sorted + right_sorted


def _strip_repeated_headers_and_footers(pages: list[dict[str, Any]]) -> None:
    if len(pages) < 3:
        return

    first_counts: dict[str, int] = {}
    last_counts: dict[str, int] = {}
    first_keys: list[str | None] = []
    last_keys: list[str | None] = []

    for page in pages:
        lines = page["lines"]
        first_key = _repeat_key(lines[0]["text"]) if lines else None
        last_key = _repeat_key(lines[-1]["text"]) if lines else None
        first_keys.append(first_key)
        last_keys.append(last_key)
        if first_key:
            first_counts[first_key] = first_counts.get(first_key, 0) + 1
        if last_key:
            last_counts[last_key] = last_counts.get(last_key, 0) + 1

    min_repeat = max(3, int(round(len(pages) * 0.6)))
    repeated_first = {key for key, count in first_counts.items() if count >= min_repeat}
    repeated_last = {key for key, count in last_counts.items() if count >= min_repeat}

    for idx, page in enumerate(pages):
        lines = page["lines"]
        if not lines:
            continue
        if first_keys[idx] and first_keys[idx] in repeated_first:
            lines.pop(0)
        if lines and last_keys[idx] and last_keys[idx] in repeated_last:
            lines.pop(-1)

        for line_index, line in enumerate(lines, start=1):
            line["line_number"] = line_index


def _repeat_key(text: str) -> str:
    normalized = collapse_whitespace((text or "").lower())
    normalized = re.sub(r"\d+", "#", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip(" .:-")
    if len(normalized) < 6:
        return ""
    return normalized


def _normalize_lines_for_text(lines: list[dict[str, Any]]) -> list[str]:
    text_lines = [
        collapse_whitespace(line.get("text", "")) for line in lines if line.get("text", "").strip()
    ]
    text_lines = dehyphenate_lines(text_lines)
    text_lines = [merge_inline_hyphenation(line) for line in text_lines]
    return [line for line in text_lines if line]
