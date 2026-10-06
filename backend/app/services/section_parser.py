from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, List, Optional


SECTION_INLINE_RE = re.compile(r"^\s*(\d+(?:\.\d+)*\.?)(?:[:\s]+)(.+?)\s*$")
SECTION_ID_ONLY_RE = re.compile(r"^\s*(\d+(?:\.\d+)*\.?)\s*$")
ARTICLE_INLINE_RE = re.compile(
    r"^\s*(Article\s+\d+[A-Za-z]?(?:\([a-z]\))?)(?:[:\s]+)(.+?)\s*$",
    re.IGNORECASE,
)
LIST_MARKER_RE = re.compile(r"^\s*(\d{1,3}|[a-zA-Z]|[ivxlcdm]+)(?:[\)\.])?\s*$", re.IGNORECASE)
BULLET_RE = re.compile(r"^\s*[•\-\u2022]\s+")
OBLIGATION_RE = re.compile(r"\b(shall|must|should|may|required)\b", re.IGNORECASE)


@dataclass
class NumberedRow:
    marker: str
    text: str
    start_line: int
    end_line: int


@dataclass
class SectionBlock:
    section_id: str
    title: str
    start_line: int
    end_line: int
    lines: List[str]


def _normalize_section_id(value: str) -> str:
    section_id = value.strip()
    if section_id.endswith("."):
        section_id = section_id[:-1]
    return section_id


def recover_noisy_markers(lines: Iterable[str]) -> List[str]:
    """Recover common OCR marker artifacts, including 'tt' in numeric sequences."""
    output = [line for line in lines]
    numeric_positions: List[tuple[int, int]] = [
        (idx, int(line.strip())) for idx, line in enumerate(output) if line.strip().isdigit()
    ]

    for idx, line in enumerate(output):
        if line.strip().lower() != "tt":
            continue
        prev = next(((pos, num) for pos, num in reversed(numeric_positions) if pos < idx), None)
        nxt = next(((pos, num) for pos, num in numeric_positions if pos > idx), None)
        if not prev or not nxt:
            continue
        _, prev_num = prev
        _, next_num = nxt
        if next_num == prev_num + 2:
            output[idx] = str(prev_num + 1)

    return output


def parse_section_blocks(raw_lines: List[str]) -> List[SectionBlock]:
    """Parse section blocks and handle both inline and split headings."""
    lines = recover_noisy_markers(raw_lines)
    blocks: List[SectionBlock] = []

    current: Optional[SectionBlock] = None
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            if current is not None:
                current.lines.append("")
                current.end_line = i + 1
            i += 1
            continue

        heading = _match_heading(lines, i, current.section_id if current else None)
        if heading is not None:
            section_id, title, consumed = heading
            if current is not None:
                blocks.append(current)
            current = SectionBlock(
                section_id=section_id,
                title=title,
                start_line=i + 1,
                end_line=i + consumed,
                lines=[],
            )
            i += consumed
            continue

        if current is not None:
            current.lines.append(stripped)
            current.end_line = i + 1
        i += 1

    if current is not None:
        blocks.append(current)
    return blocks


def _match_heading(
    lines: List[str],
    index: int,
    current_section_id: Optional[str],
) -> Optional[tuple[str, str, int]]:
    line = lines[index].strip()

    inline = SECTION_INLINE_RE.match(line)
    if inline:
        section_id = _normalize_section_id(inline.group(1))
        title = inline.group(2).strip()
        if _looks_like_list_item(section_id, title, current_section_id):
            return None
        return section_id, title, 1

    article = ARTICLE_INLINE_RE.match(line)
    if article:
        return article.group(1).strip(), article.group(2).strip(), 1

    id_only = SECTION_ID_ONLY_RE.match(line)
    if not id_only:
        return None

    section_id = _normalize_section_id(id_only.group(1))
    if _is_probable_list_marker(section_id, current_section_id):
        return None

    title = ""
    consumed = 1
    if index + 1 < len(lines):
        next_line = lines[index + 1].strip()
        if (
            next_line
            and not SECTION_ID_ONLY_RE.match(next_line)
            and not SECTION_INLINE_RE.match(next_line)
            and not ARTICLE_INLINE_RE.match(next_line)
            and not BULLET_RE.match(next_line)
            and not LIST_MARKER_RE.match(next_line)
        ):
            title = next_line
            consumed = 2

    return section_id, title, consumed


def _is_probable_list_marker(section_id: str, current_section_id: Optional[str]) -> bool:
    if "." in section_id:
        return False
    if current_section_id and "." in current_section_id:
        return True
    return False


def _looks_like_list_item(
    section_id: str,
    title: str,
    current_section_id: Optional[str],
) -> bool:
    if "." in section_id:
        return False
    if current_section_id and "." in current_section_id:
        return True
    if OBLIGATION_RE.search(title):
        return False
    if len(title.split()) > 12:
        return True
    return False


def infer_numbered_rows(lines: List[str]) -> List[NumberedRow]:
    """Infer row-style requirements from alternating markers and content."""
    rows: List[NumberedRow] = []
    marker_re = re.compile(r"^\s*(\d{1,3})\s*$")

    current_marker: Optional[str] = None
    current_start: Optional[int] = None
    buffer: List[str] = []

    normalized = recover_noisy_markers(lines)

    for idx, line in enumerate(normalized):
        stripped = line.strip()
        marker_match = marker_re.match(stripped)
        if marker_match:
            if current_marker is not None and buffer:
                rows.append(
                    NumberedRow(
                        marker=current_marker,
                        text=" ".join(part for part in buffer if part).strip(),
                        start_line=(current_start or 0) + 1,
                        end_line=idx,
                    )
                )
            current_marker = marker_match.group(1)
            current_start = idx
            buffer = []
            continue

        if current_marker is not None and stripped:
            buffer.append(stripped)

    if current_marker is not None and buffer:
        rows.append(
            NumberedRow(
                marker=current_marker,
                text=" ".join(part for part in buffer if part).strip(),
                start_line=(current_start or 0) + 1,
                end_line=len(normalized),
            )
        )

    return rows
