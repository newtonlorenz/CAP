import re
from typing import List, Optional

from app.services.document_reader import default_reader
import pdfplumber

from app.services.text_normalizer import (
    collapse_whitespace,
    dehyphenate_lines,
    detect_repeated_lines,
    merge_inline_hyphenation,
    normalize_unicode,
    normalize_for_match,
    remove_repeated_lines,
)

SECTION_HEADING_RE = re.compile(r"^\s*(\d+(?:\.\d+)*\.?)(?:[:\s]+)(.*)$", re.IGNORECASE)
ARTICLE_HEADING_RE = re.compile(r"^\s*(Article\s+\d+[A-Za-z]?(?:\([a-z]\))?)(?:[:\s]+)(.*)$")
SECTION_ID_ONLY_RE = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s*$")
LIST_ITEM_RE = re.compile(r"^\s*(\d{1,3})(?:[\)\.])?\s+")
GUIDANCE_RE = re.compile(r"^\s*(guidance|note|guideline)\s*:", re.IGNORECASE)
OBLIGATION_RE = re.compile(
    r"\b(shall|must|should|may|required|responsible)\b|is required to|are required to",
    re.IGNORECASE,
)
SECTION_REF_TAIL_RE = re.compile(
    r"(section|sections|sec\.|cf\.|cf|see|see also|requirement|requirements|clause|clauses|item|items|article|articles)\s*$",
    re.IGNORECASE,
)


def _looks_like_guide_page(raw_text: str) -> bool:
    """Detect guide pages where pdfplumber can interleave columns."""
    if not raw_text:
        return False
    lines = [line_text.strip() for line_text in raw_text.splitlines() if line_text.strip()]
    for line in lines[:10]:
        lower = line.lower()
        if lower == "guide" or lower.startswith("guide continued"):
            return True
    return False


def extract_text_from_pdf(file_path: str) -> List[dict]:
    """Extract text from PDF page by page. Uses pdfplumber primarily, PDFium as fallback."""
    try:
        pages = _extract_with_pdfplumber(file_path)
    except Exception:
        return _extract_with_pdfium(file_path)

    return pages


def _extract_with_pdfplumber(file_path: str) -> List[dict]:
    pages = []
    fallback_pages = None
    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            tables = page.extract_tables() or []

            if _looks_like_guide_page(text):
                # Prefer PDFium for these pages; it produces a more coherent reading order.
                if fallback_pages is None:
                    fallback_pages = default_reader.read_pages(file_path)
                text = fallback_pages[i]["text"] or ""

            if not text.strip():
                # Fallback for blank pages only, to avoid full re-extraction.
                if fallback_pages is None:
                    fallback_pages = default_reader.read_pages(file_path)
                text = fallback_pages[i]["text"] or ""

            pages.append({"page_number": i + 1, "text": text, "tables": tables})


    normalized_pages = _normalize_pages(pages)
    output = []
    for page in normalized_pages:
        full_text = page["text"]
        tables = page.get("tables") or []
        table_blocks = []
        for table in tables:
            if _table_is_duplicate(table, full_text):
                continue
            table_blocks.append(_tables_to_text([table]))

        if table_blocks:
            section_id = _find_last_section(full_text)
            if section_id:
                full_text += f"\n\n[TABLE_SECTION:{section_id}]\n"
            for block in table_blocks:
                full_text += "\n\n[TABLE]\n" + block

        output.append({"page_number": page["page_number"], "text": full_text})

    return output


def _extract_with_pdfium(file_path: str) -> List[dict]:
    return default_reader.read_pages(file_path)


def _tables_to_text(tables: list) -> str:
    lines = []
    for table in tables:
        for row in table:
            cells = [_normalize_cell(c or "") for c in row]
            lines.append(" | ".join(cells))
        lines.append("")
    return "\n".join(lines)


def _normalize_pages(pages: List[dict]) -> List[dict]:
    page_lines = []
    for page in pages:
        text = normalize_unicode(page.get("text", ""))
        lines = [collapse_whitespace(line) for line in text.splitlines()]
        lines = [line for line in lines if line]
        page_lines.append(lines)

    repeated = detect_repeated_lines(page_lines)
    normalized_pages = []
    prev_section_id: Optional[str] = None
    for idx, page in enumerate(pages):
        lines = page_lines[idx]
        lines = remove_repeated_lines(lines, repeated)
        lines = dehyphenate_lines(lines)
        lines = _join_section_references(lines)
        lines = _join_section_lines(lines)
        lines = [merge_inline_hyphenation(line) for line in lines]
        first_heading_index = _first_section_heading_index(lines)
        if prev_section_id:
            if first_heading_index is None and _has_content(lines):
                lines.insert(0, f"[SECTION_CONTINUATION:{prev_section_id}]")
            elif first_heading_index > 0 and _has_content_before_heading(
                lines, first_heading_index
            ):
                lines.insert(0, f"[SECTION_CONTINUATION:{prev_section_id}]")
        normalized_text = "\n".join(lines)
        normalized_pages.append(
            {
                "page_number": page["page_number"],
                "text": normalized_text,
                "tables": page.get("tables", []),
            }
        )
        last_section = _find_last_section("\n".join(lines))
        if last_section:
            prev_section_id = last_section
    return normalized_pages


def _join_section_lines(lines: List[str]) -> List[str]:
    output: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if i + 1 < len(lines) and SECTION_ID_ONLY_RE.match(line):
            next_line = lines[i + 1]
            if _should_join_title(line, next_line):
                output.append(f"{line} {next_line}".strip())
                i += 2
                continue
        if i + 1 < len(lines) and _is_section_heading(line):
            next_line = lines[i + 1]
            if _should_join_title(line, next_line):
                output.append(f"{line} {next_line}".strip())
                i += 2
                continue
        output.append(line)
        i += 1
    return output


def _join_section_references(lines: List[str]) -> List[str]:
    output: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if i + 1 < len(lines):
            next_line = lines[i + 1]
            if SECTION_REF_TAIL_RE.search(line.strip()):
                if SECTION_ID_ONLY_RE.match(next_line) or SECTION_HEADING_RE.match(next_line):
                    output.append(f"{line} {next_line}".strip())
                    i += 2
                    continue
        output.append(line)
        i += 1
    return output


def _is_section_heading(line: str) -> bool:
    match = SECTION_HEADING_RE.match(line) or ARTICLE_HEADING_RE.match(line)
    if not match:
        return False
    title = match.group(2) if match.lastindex and match.lastindex >= 2 else ""
    if title and _looks_like_list_item_title(title):
        return False
    return True


def _should_join_title(line: str, next_line: str) -> bool:
    if LIST_ITEM_RE.match(next_line):
        return False
    if GUIDANCE_RE.match(next_line):
        return False
    if SECTION_HEADING_RE.match(next_line) or ARTICLE_HEADING_RE.match(next_line):
        return False
    if re.fullmatch(r"\d+", next_line.strip()):
        return False
    return len(next_line.split()) <= 5


def _find_last_section(text: str) -> Optional[str]:
    section_id = None
    for line in text.splitlines():
        match = SECTION_HEADING_RE.match(line)
        if match:
            title = match.group(2).strip()
            if not _looks_like_list_item_title(title):
                section_id = match.group(1).strip()
                if section_id.endswith("."):
                    section_id = section_id[:-1]
            continue
        match = ARTICLE_HEADING_RE.match(line)
        if match:
            section_id = match.group(1).strip()
    return section_id


def _table_is_duplicate(table: list, text: str) -> bool:
    if not table:
        return True
    normalized_text = normalize_for_match(text)
    row_matches = 0
    row_count = 0
    for row in table:
        if not row:
            continue
        row_count += 1
        row_text = " ".join([c or "" for c in row])
        row_text = normalize_for_match(row_text)
        if not row_text:
            continue
        if row_text in normalized_text:
            row_matches += 1
    if row_count == 0:
        return True
    return (row_matches / row_count) >= 0.6


def _looks_like_list_item_title(title: str) -> bool:
    if OBLIGATION_RE.search(title):
        return True
    stripped = title.strip()
    if stripped and stripped[0].islower():
        return True
    if stripped.startswith(("The ", "If ", "[TEST", "[Test", "[test")):
        return True
    if len(stripped.split()) > 10:
        return True
    return False


def _first_section_heading_index(lines: List[str]) -> Optional[int]:
    for idx, line in enumerate(lines):
        if _is_section_heading(line):
            return idx
    return None


def _has_content_before_heading(lines: List[str], heading_index: int) -> bool:
    for line in lines[:heading_index]:
        if line.strip() and not GUIDANCE_RE.match(line):
            return True
    return False


def _has_content(lines: List[str]) -> bool:
    for line in lines:
        if line.strip() and not GUIDANCE_RE.match(line):
            return True
    return False


def _normalize_cell(text: str) -> str:
    text = normalize_unicode(text)
    lines = [collapse_whitespace(line) for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    lines = dehyphenate_lines(lines)
    joined = " ".join(lines)
    joined = merge_inline_hyphenation(joined)
    return collapse_whitespace(joined)
