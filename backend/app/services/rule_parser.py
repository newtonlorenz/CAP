"""Deterministic requirement parsing. No settings, SDKs or network dependencies."""

import re

from app.services.section_parser import (
    infer_numbered_rows,
    recover_noisy_markers,
)
from app.services.text_normalizer import normalize_for_match

MANDATORY_KEYWORDS = (
    "shall",
    "must",
    "is required to",
    "are required to",
    "required",
    "is responsible to",
    "is responsible for",
)
RECOMMENDED_KEYWORDS = ("should", "is recommended")
GUIDANCE_PREFIXES = ("guidance:", "note:", "guideline:")
SECTION_RE = re.compile(r"^\s*(\d+(?:\.\d+)*\.?)(?:[:\s]+)(.*)$")
SECTION_ID_ONLY_RE = re.compile(r"^\s*(\d+(?:\.\d+)*\.?)\s*$")
ARTICLE_RE = re.compile(
    r"^\s*(Article\s+\d+[A-Za-z]?(?:\([a-z]\))?)(?:[:\s]+)(.*)$",
    re.IGNORECASE,
)
TABLE_ROW_RE = re.compile(r"^\s*(\d+)\s*\|\s*(.*)$")
TABLE_SECTION_RE = re.compile(r"^\s*\[TABLE_SECTION:(.+)\]\s*$")
SECTION_CONTINUATION_RE = re.compile(r"^\s*\[SECTION_CONTINUATION:(.+)\]\s*$")
LIST_ITEM_RE = re.compile(r"^\s*(\d{1,3})(?:[\)\.])?\s+(.*)$")
LETTER_ITEM_RE = re.compile(r"^\s*([a-zA-Z])(?:[\)\.])?\s+(.*)$")
ROMAN_ITEM_RE = re.compile(r"^\s*([ivxlcdm]+)(?:[\)\.])?\s+(.*)$", re.IGNORECASE)
BULLET_RE = re.compile(r"^\s*[•\-\u2022]\s+(.*)$")
PARENT_INTRO_RE = re.compile(
    r"(following|including|includes|as follows)\s*[:;]?\s*$", re.IGNORECASE
)
OBLIGATION_RE = re.compile(
    r"\b(shall|must|should|may)\b|is required to|are required to",
    re.IGNORECASE,
)
SECTION_REF_START_RE = re.compile(
    r"^(section|sections|sec\.|article|articles|clause|clauses|item|items|requirement|requirements)\b|\d+(?:\.\d+)+",
    re.IGNORECASE,
)
TIME_FRAGMENT_RE = re.compile(
    r"^(day|days|month|months|year|years|hour|hours|minute|minutes)\b", re.IGNORECASE
)
EXPLICIT_LIST_NUM_RE = re.compile(r"^\s*\d+[\)\.]")


def _is_guidance_line(line: str) -> bool:
    return line.strip().lower().startswith(GUIDANCE_PREFIXES)


def _append_guidance(text: str, guidance_lines: list[str]) -> str:
    if not guidance_lines:
        return text
    cleaned = [g.strip() for g in guidance_lines if g.strip()]
    if not cleaned:
        return text
    suffix = "\n".join(cleaned)
    if not text:
        return suffix
    return f"{text}\n{suffix}"


def _join_lines_preserve_format(lines: list[str]) -> str:
    output: list[str] = []
    paragraph: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if paragraph:
                output.append(" ".join(paragraph))
                paragraph = []
            continue
        if _is_list_item_line(stripped) or BULLET_RE.match(stripped) or _is_guidance_line(stripped):
            if paragraph:
                output.append(" ".join(paragraph))
                paragraph = []
            output.append(stripped)
            continue
        paragraph.append(stripped)
    if paragraph:
        output.append(" ".join(paragraph))
    return "\n".join(output).strip()


def _requirement_type(text: str) -> str:
    lower = text.lower()
    if re.match(r"\s*(?:\d+[.)]?\s+)?\[test\]", lower):
        return "mandatory"
    if any(k in lower for k in MANDATORY_KEYWORDS) or re.search(
        r"\b(may only|may not|is not permitted|are not permitted|not allowed)\b", lower
    ):
        return "mandatory"
    if any(k in lower for k in RECOMMENDED_KEYWORDS):
        return "recommended"
    return "informational"


def _split_sentences(text: str) -> list[str]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]
    if not parts:
        return []
    merged: list[str] = []
    i = 0
    while i < len(parts):
        current = parts[i]
        if current.lower().endswith("cf.") and i + 1 < len(parts):
            nxt = parts[i + 1]
            if SECTION_REF_START_RE.match(nxt):
                current = f"{current} {nxt}".strip()
                i += 1
        merged.append(current)
        i += 1
    return merged


def _coalesce_split_heading_lines(lines: list[str]) -> list[str]:
    output: list[str] = []
    normalized_lines = recover_noisy_markers(lines)
    i = 0
    while i < len(normalized_lines):
        current = normalized_lines[i]
        stripped = current.strip()
        id_only = SECTION_ID_ONLY_RE.match(stripped)
        if id_only and "." in id_only.group(1) and i + 1 < len(normalized_lines):
            nxt = normalized_lines[i + 1].strip()
            if (
                nxt
                and not SECTION_RE.match(nxt)
                and not ARTICLE_RE.match(nxt)
                and not LIST_ITEM_RE.match(nxt)
                and not BULLET_RE.match(nxt)
            ):
                output.append(f"{stripped} {nxt}".strip())
                i += 2
                continue
        output.append(current)
        i += 1
    return output


def _match_section(line: str) -> tuple[str, str] | None:
    match = SECTION_RE.match(line)
    if match:
        section_id = match.group(1).strip()
        section_id = section_id.removesuffix(".")
        title = match.group(2).strip()
        if "." not in section_id and _looks_like_list_item_title(title):
            return None
        return section_id, title
    match = ARTICLE_RE.match(line)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return None


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


def _parse_list_items(lines: list[str]) -> list[tuple[str | None, str]]:
    items: list[tuple[str | None, str]] = []
    current: str | None = None
    current_label: str | None = None
    numeric_candidates: list[int] = []
    for line in lines:
        stripped = line.strip()
        match = LIST_ITEM_RE.match(stripped)
        if not match:
            continue
        label = match.group(1).strip()
        if not label.isdigit():
            continue
        num = int(label)
        if num <= 20 or EXPLICIT_LIST_NUM_RE.match(stripped):
            numeric_candidates.append(num)
    max_reasonable_numeric = max(numeric_candidates) if numeric_candidates else None

    for line in lines:
        if _match_section(line.strip()):
            continue
        stripped = line.strip()
        if _is_guidance_line(stripped):
            if current:
                current = f"{current}\n{stripped}".strip()
            continue
        letter_match = LETTER_ITEM_RE.match(stripped)
        roman_match = ROMAN_ITEM_RE.match(stripped)
        numeric_match = LIST_ITEM_RE.match(stripped)
        if numeric_match and numeric_match.group(1).isdigit():
            label_num = int(numeric_match.group(1))
            remainder = numeric_match.group(2).strip()
            has_explicit_num = bool(EXPLICIT_LIST_NUM_RE.match(stripped))
            is_time_fragment = TIME_FRAGMENT_RE.match(remainder) is not None
            if is_time_fragment and not has_explicit_num:
                if (max_reasonable_numeric is None and label_num > 20) or (
                    max_reasonable_numeric is not None and label_num > max_reasonable_numeric + 5
                ):
                    if current:
                        current += " " + stripped
                    elif items:
                        last_label, last_text = items[-1]
                        items[-1] = (last_label, f"{last_text} {stripped}".strip())
                    continue
        if current and current_label and current_label.isdigit():
            if letter_match:
                sub_label = letter_match.group(1).strip().lower()
                sub_text = letter_match.group(2).strip()
                current += f"\n- {sub_label}. {sub_text}"
                continue
            if roman_match:
                sub_label = roman_match.group(1).strip().lower()
                sub_text = roman_match.group(2).strip()
                current += f"\n- {sub_label}. {sub_text}"
                continue
        match = None
        label: str | None = None
        for regex in (LIST_ITEM_RE, LETTER_ITEM_RE, ROMAN_ITEM_RE):
            match = regex.match(stripped)
            if match:
                if current:
                    items.append((current_label, current.strip()))
                label = match.group(1).strip()
                if regex in (LETTER_ITEM_RE, ROMAN_ITEM_RE):
                    label = label.lower()
                current_label = label
                current = match.group(2).strip()
                break
        if match:
            continue
        bullet_match = BULLET_RE.match(line)
        if bullet_match and current:
            current += "\n- " + bullet_match.group(1).strip()
            continue
        if current and stripped:
            current += " " + stripped

    if current:
        items.append((current_label, current.strip()))
    return items


def _is_list_item_line(line: str) -> bool:
    stripped = line.strip()
    return bool(
        LIST_ITEM_RE.match(stripped)
        or LETTER_ITEM_RE.match(stripped)
        or ROMAN_ITEM_RE.match(stripped)
    )


def _section_parent(section_id: str) -> str | None:
    if "." not in section_id:
        return None
    parts = section_id.split(".")
    if len(parts) <= 1:
        return None
    return ".".join(parts[:-1])


def parse_requirements_rule_based(
    text: str,
    document_type: str,
    page_number: int,
) -> list[dict]:
    if not text.strip():
        return []

    lower_text = text.lower()
    if "contents" in lower_text or "table of contents" in lower_text:
        return []

    if lower_text.count("....") > 5:
        return []

    requirements: list[dict] = []
    lines = _coalesce_split_heading_lines(text.splitlines())
    current_section: str | None = None
    section_titles: dict[str, str] = {}
    section_buffers: dict[str, list[str]] = {}
    table_rows: list[dict] = []
    table_sections: set[str] = set()
    in_table = False
    table_section: str | None = None
    created_refs: set[str] = set()
    continued_sections: set[str] = set()

    for line in lines:
        continuation_match = SECTION_CONTINUATION_RE.match(line.strip())
        if continuation_match:
            current_section = continuation_match.group(1).strip()
            continued_sections.add(current_section)
            section_buffers.setdefault(current_section, [])
            continue

        table_section_match = TABLE_SECTION_RE.match(line.strip())
        if table_section_match:
            table_section = table_section_match.group(1).strip()
            in_table = False
            continue

        if line.strip() == "[TABLE]":
            in_table = True
            if table_section is None:
                table_section = current_section
            continue

        if in_table:
            row_match = TABLE_ROW_RE.match(line)
            if row_match:
                if table_section:
                    table_sections.add(table_section)
                table_rows.append(
                    {
                        "section_id": table_section,
                        "row_num": row_match.group(1),
                        "content": row_match.group(2).strip(),
                    }
                )
                continue

            if "|" not in line:
                section_match = _match_section(line)
                if section_match:
                    in_table = False
                    current_section = section_match[0]
                    section_titles[current_section] = section_match[1].strip()
                    section_buffers.setdefault(current_section, [])
                    continue

            else:
                if table_rows:
                    table_rows[-1]["content"] += "\n" + line.strip()
            continue

        section_match = _match_section(line)
        if section_match:
            section_id = section_match[0]
            section_title = section_match[1].strip()
            if (
                current_section
                and "." not in section_id
                and any(
                    k in section_title.lower() for k in MANDATORY_KEYWORDS + RECOMMENDED_KEYWORDS
                )
            ):
                section_buffers.setdefault(current_section, []).append(line)
                continue

            current_section = section_id
            section_titles[current_section] = section_title
            section_buffers.setdefault(current_section, [])
            if any(k in section_title.lower() for k in MANDATORY_KEYWORDS + RECOMMENDED_KEYWORDS):
                section_buffers[current_section].append(section_title)
            continue

        if current_section:
            section_buffers.setdefault(current_section, []).append(line)

    def add_requirement(
        reference_id: str,
        text_value: str,
        title_value: str | None,
        requirement_type: str,
        parent_reference: str | None,
        confidence: float,
        *,
        needs_review: bool = False,
        review_reason: str | None = None,
        parser_strategy: str = "rule_based",
        source_excerpt: str | None = None,
    ) -> None:
        if reference_id in continued_sections:
            return  # Its heading belongs to the earlier source page, not this continuation.
        requirements.append(
            {
                "reference_id": reference_id,
                "title": title_value,
                "text": text_value,
                "requirement_type": requirement_type,
                "parent_reference": parent_reference,
                "confidence": confidence,
                "page_number": page_number,
                "needs_review": needs_review,
                "review_reason": review_reason,
                "parser_strategy": parser_strategy,
                "source_excerpt": source_excerpt or text_value[:280],
            }
        )
        created_refs.add(reference_id)

    # Table-based extraction
    added_section_parent: set[str] = set()
    for row in table_rows:
        section_id = row["section_id"]
        row_num = row["row_num"]
        content = row["content"]
        if section_id and section_id not in added_section_parent:
            title = section_titles.get(section_id, f"Section {section_id}")
            add_requirement(
                reference_id=section_id,
                text_value=title,
                title_value=title,
                requirement_type="informational",
                parent_reference=_section_parent(section_id),
                confidence=0.85,
            )
            added_section_parent.add(section_id)

        row_lines = [line for line in content.splitlines() if line.strip()]
        guidance_lines = [line for line in row_lines if _is_guidance_line(line)]
        list_items = _parse_list_items(row_lines)
        row_text_lines = [
            line
            for line in row_lines
            if not _is_list_item_line(line) and not _is_guidance_line(line)
        ]
        row_text = _join_lines_preserve_format(row_text_lines)
        if guidance_lines and not list_items:
            row_text = _append_guidance(row_text, guidance_lines)

        if row_text:
            row_ref = f"{section_id}.{row_num}" if section_id else row_num
            row_type = _requirement_type(row_text)
            add_requirement(
                reference_id=row_ref,
                text_value=row_text,
                title_value=None,
                requirement_type=row_type,
                parent_reference=section_id,
                confidence=0.9,
            )
        else:
            row_ref = f"{section_id}.{row_num}" if section_id else row_num
            row_type = "mandatory"

        for idx, (label, item) in enumerate(list_items, start=1):
            suffix = label or str(idx)
            add_requirement(
                reference_id=f"{row_ref}.{suffix}",
                text_value=item,
                title_value=None,
                requirement_type=row_type,
                parent_reference=row_ref,
                confidence=0.85,
            )

    # Section-based extraction (non-table)
    for section_id, buffer in section_buffers.items():
        if section_id in table_sections:
            continue
        block_lines = [line for line in buffer if line.strip()]
        guidance_lines = [line for line in block_lines if _is_guidance_line(line)]
        content_lines = [line for line in block_lines if not _is_guidance_line(line)]
        title = section_titles.get(section_id)
        if not content_lines and not guidance_lines:
            if title and section_id not in created_refs:
                add_requirement(
                    reference_id=section_id,
                    text_value=title,
                    title_value=None if _requirement_type(title) != "informational" else title,
                    requirement_type=_requirement_type(title),
                    parent_reference=_section_parent(section_id),
                    confidence=0.8,
                )
            continue
        block_text = _join_lines_preserve_format(content_lines)
        sentences = _split_sentences(block_text)
        obligation_sentences = [s for s in sentences if _requirement_type(s) != "informational"]
        if not obligation_sentences:
            if title and section_id not in created_refs:
                add_requirement(
                    reference_id=section_id,
                    text_value=title,
                    title_value=None if _requirement_type(title) != "informational" else title,
                    requirement_type=_requirement_type(title),
                    parent_reference=_section_parent(section_id),
                    confidence=0.8,
                )
            continue
        parent_reference = _section_parent(section_id)
        title = section_titles.get(section_id)
        # Numbered table rows use bare numbers; parenthesised lists belong inside the
        # current control and must not be merged with later table rows.
        row_lines_for_inference = []
        last_row_marker = None
        for line in block_lines:
            inline_row = (
                re.match(r"^\s*(\d{1,3})\s+(.+)$", line)
            )
            if inline_row:
                marker = int(inline_row.group(1))
                expected = last_row_marker + 1 if last_row_marker is not None else 1
                if marker != expected and not (
                    last_row_marker is None and section_id in continued_sections
                ):
                    inline_row = None
                else:
                    last_row_marker = marker
            row_lines_for_inference.extend(
                [inline_row.group(1), inline_row.group(2)] if inline_row else [line]
            )
        inferred_rows = infer_numbered_rows(row_lines_for_inference)
        if inferred_rows:
            if title and section_id not in created_refs:
                add_requirement(
                    reference_id=section_id,
                    text_value=title,
                    title_value=None if _requirement_type(title) != "informational" else title,
                    requirement_type=_requirement_type(title),
                    parent_reference=parent_reference,
                    confidence=0.8,
                    parser_strategy="section_graph",
                )
            for inferred in inferred_rows:
                if not inferred.text:
                    continue
                row_text = inferred.text.strip()
                add_requirement(
                    reference_id=f"{section_id}.{inferred.marker}",
                    text_value=row_text,
                    title_value=None,
                    requirement_type=_requirement_type(row_text),
                    parent_reference=section_id,
                    confidence=0.88,
                    parser_strategy="section_graph",
                    source_excerpt=row_text,
                )
            continue
        list_items = _parse_list_items(block_lines)
        guidance_in_items = set()
        if guidance_lines and list_items:
            for _, item in list_items:
                for guidance in guidance_lines:
                    if guidance.strip() and guidance.strip() in item:
                        guidance_in_items.add(guidance)
        guidance_to_append = [g for g in guidance_lines if g not in guidance_in_items]
        if list_items:
            orphan_lines = [
                line
                for line in content_lines
                if not _is_list_item_line(line) and OBLIGATION_RE.search(line)
            ]
            if orphan_lines:
                first_numeric_label = next(
                    (label for label, _ in list_items if label and label.isdigit()), None
                )
                if first_numeric_label and int(first_numeric_label) > 1:
                    orphan_label = str(int(first_numeric_label) - 1)
                    orphan_text = " ".join(orphan_lines).strip()
                    list_items = [(orphan_label, orphan_text)] + list_items

            parent_text = obligation_sentences[0] if obligation_sentences else title or section_id
            parent_type = _requirement_type(parent_text)
            use_parent = True
            first_item_text = list_items[0][1]
            first_item_label = list_items[0][0]
            if title and not OBLIGATION_RE.search(title):
                parent_text = title
                parent_type = "informational"
            parent_compare = parent_text
            if first_item_label:
                parent_compare = re.sub(
                    rf"^\s*{re.escape(first_item_label)}(?:[\)\.])?\s+",
                    "",
                    parent_compare,
                    count=1,
                    flags=re.IGNORECASE,
                )
            if normalize_for_match(parent_compare) == normalize_for_match(first_item_text):
                if title and normalize_for_match(title) != normalize_for_match(first_item_text):
                    parent_text = title
                    parent_type = "informational"
                else:
                    use_parent = False

            if not use_parent and guidance_to_append:
                first_label, first_item = list_items[0]
                list_items[0] = (
                    first_label,
                    _append_guidance(first_item, guidance_to_append),
                )
                guidance_to_append = []

            if PARENT_INTRO_RE.search(parent_text):
                merged_text = f"{parent_text} {' '.join(item for _, item in list_items)}".strip()
                if guidance_to_append:
                    merged_text = _append_guidance(merged_text, guidance_to_append)
                if section_id not in created_refs:
                    add_requirement(
                        reference_id=section_id,
                        text_value=merged_text,
                        title_value=title,
                        requirement_type=parent_type,
                        parent_reference=parent_reference,
                        confidence=0.9,
                    )
                continue

            if use_parent and section_id not in created_refs:
                if guidance_to_append:
                    parent_text = _append_guidance(parent_text, guidance_to_append)
                add_requirement(
                    reference_id=section_id,
                    text_value=parent_text,
                    title_value=title,
                    requirement_type=parent_type,
                    parent_reference=parent_reference,
                    confidence=0.9,
                )
            for idx, (label, item) in enumerate(list_items, start=1):
                suffix = label or str(idx)
                add_requirement(
                    reference_id=f"{section_id}.{suffix}",
                    text_value=item,
                    title_value=None,
                    requirement_type=(
                        _requirement_type(item)
                        if _requirement_type(item) != "informational" or not use_parent
                        else _requirement_type(parent_text)
                    ),
                    parent_reference=section_id,
                    confidence=0.85,
                )
            continue

        if len(obligation_sentences) == 1:
            sentence = block_text or obligation_sentences[0]
            if guidance_lines:
                sentence = _append_guidance(sentence, guidance_lines)
            if section_id not in created_refs:
                add_requirement(
                    reference_id=section_id,
                    text_value=sentence,
                    title_value=title,
                    requirement_type=_requirement_type(sentence),
                    parent_reference=parent_reference,
                    confidence=0.9,
                )
            continue

        if section_id not in created_refs:
            parent_text = block_text or " ".join(obligation_sentences)
            if guidance_lines:
                parent_text = _append_guidance(parent_text, guidance_lines)
            add_requirement(
                reference_id=section_id,
                text_value=parent_text,
                title_value=title,
                requirement_type=_requirement_type(parent_text),
                parent_reference=parent_reference,
                confidence=0.85,
            )

    return requirements
