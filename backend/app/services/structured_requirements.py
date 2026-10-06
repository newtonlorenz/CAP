"""Deterministic candidates from OpenDataLoader's tagged PDF JSON.

This parser uses the document's numbered headings and table cells. It does not
infer obligations from prose or invent references for unnumbered subdivisions.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

_HEADING = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+(.+?)\s*$")
_CONTENTS_HEADING = re.compile(r"^(?:table\s+of\s+)?contents\s*:?$", re.IGNORECASE)
_CONTENTS_LEADER = re.compile(r"\.{4,}\s*\S*\s*$")
_NUMBER = re.compile(r"\d+")


def _children(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Read all structural child fields, including nested lists and cells."""
    for value in node.values():
        if isinstance(value, dict):
            yield value
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    yield item


def _document_nodes(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, list):
        for item in node:
            yield from _document_nodes(item)
    elif isinstance(node, dict):
        if node.get("type") == "text block":
            direct_children = list(_children(node))
            if direct_children and all(
                isinstance(child.get("font size"), (int, float))
                and child["font size"] < 8.5
                for child in direct_children
            ) and any(
                re.search(r"\bPage\s+\d+\b", str(child.get("content", "")))
                for child in direct_children
            ):
                return  # Tagged running header and footer, not body prose.
        if node.get("type") in {"heading", "list item", "paragraph", "table"}:
            yield node
        if node.get("type") != "table":
            for child in _children(node):
                yield from _document_nodes(child)


def _cell_parts(node: Any) -> list[str]:
    if isinstance(node, list):
        return [part for item in node for part in _cell_parts(item)]
    if not isinstance(node, dict):
        return []
    parts = [node["content"].strip()] if isinstance(node.get("content"), str) and node["content"].strip() else []
    for child in _children(node):
        parts.extend(_cell_parts(child))
    return parts


def _cell_text(node: Any) -> str:
    return "\n".join(_cell_parts(node))


def _locations(node: Any) -> list[dict[str, Any]]:
    if isinstance(node, list):
        return [location for item in node for location in _locations(item)]
    if not isinstance(node, dict):
        return []
    result: list[dict[str, Any]] = []
    if isinstance(node.get("content"), str) and node["content"].strip():
        page = node.get("page number")
        box = node.get("bounding box")
        if isinstance(page, int) and page > 0:
            result.append({
                "page_number": page,
                "bounding_box": list(box) if isinstance(box, (list, tuple)) and len(box) == 4 else None,
            })
    for child in _children(node):
        result.extend(_locations(child))
    return result


def _join(existing: str, addition: str) -> str:
    if not existing:
        return addition
    if not addition:
        return existing
    # A line broken in the middle of a sentence remains a sentence. Other
    # paragraphs and bullets retain a visible boundary in the source text.
    separator = "\n" if addition.startswith(("•", "-", "a.", "b.", "c.", "Guidance:")) else " "
    return existing + separator + addition


def _candidate(
    reference: str, title: str, text: str, page: int | None, kind: str,
    locations: list[dict[str, Any]],
) -> dict[str, Any]:
    if page is None:
        page = next((loc["page_number"] for loc in locations if loc.get("page_number")), None)
    parent = reference.rpartition(".")[0] or None
    return {
        "reference_id": reference,
        "parent_reference": parent,
        "title": title[:500],
        "text": text,
        "original_text": text,
        "source_excerpt": text,
        "source_locations": locations,
        "page_number": page,
        "requirement_type": kind,
        "parser_strategy": "opendataloader",
        "needs_review": False,
        "review_reason": None,
        "confidence_score": 0.98 if kind == "mandatory" else 0.95,
    }


def _flag(candidate: dict[str, Any], reason: str) -> None:
    candidate["needs_review"] = True
    existing = candidate["review_reason"]
    candidate["review_reason"] = f"{existing}; {reason}" if existing else reason
    candidate["confidence_score"] = min(candidate["confidence_score"], 0.5)


def _append(candidate: dict[str, Any], addition: str, locations: list[dict[str, Any]]) -> None:
    joined = _join(candidate["text"], addition)
    candidate["text"] = joined
    candidate["original_text"] = joined
    candidate["source_excerpt"] = _join(candidate["source_excerpt"], addition)
    candidate["source_locations"].extend(locations)


def parse_structured_requirements(payload: dict, *, recover: bool = False) -> list[dict]:
    """Return source-grounded, ordered requirement candidates.

    Strict parsing rejects structural ambiguity. Recovery retains each ambiguous
    source block as a flagged candidate with an opaque, nonnumeric draft key.
    """
    if not isinstance(payload, dict):
        raise TypeError("OpenDataLoader payload must be a dictionary")

    nodes = list(_document_nodes(payload))
    candidates: list[dict[str, Any]] = []
    by_reference: dict[str, dict[str, Any]] = {}
    table_section: dict[Any, str | None] = {}
    table_last: dict[Any, dict[str, Any] | None] = {}
    current_section: str | None = None
    active_heading: dict[str, Any] | None = None
    last_table_candidate: dict[str, Any] | None = None
    previous_prose: tuple[str, int | None] | None = None
    in_contents = False
    contents_descendant_ids: set[int] = set()
    consumed_title_index: int | None = None

    def unresolved(raw: str, page: int | None, locations: list[dict[str, Any]],
                   reason: str, source_reference: str | None = None,
                   extracted_text: str | None = None) -> dict[str, Any]:
        # This key identifies a draft row only. It is never a source reference and
        # the publication gate rejects it until a reviewer resolves or excludes it.
        candidate = _candidate(f"unresolved-{len(candidates) + 1}",
                               (extracted_text if extracted_text is not None else raw)[:500],
                               extracted_text if extracted_text is not None else raw,
                               page, "informational", locations)
        candidate["source_reference"] = source_reference
        candidate["source_excerpt"] = raw
        _flag(candidate, reason)
        candidates.append(candidate)
        return candidate

    def add(candidate: dict[str, Any]) -> dict[str, Any]:
        reference = candidate["reference_id"]
        if reference in by_reference:
            if recover:
                return unresolved(candidate["source_excerpt"], candidate["page_number"],
                                  candidate["source_locations"], f"duplicate_reference:{reference}",
                                  reference, candidate["original_text"])
            raise ValueError(f"Duplicate OpenDataLoader reference: {reference}")
        by_reference[reference] = candidate
        candidates.append(candidate)
        return candidate

    for index, node in enumerate(nodes):
        node_type = node.get("type")
        content = node.get("content")
        content = content.strip() if isinstance(content, str) else ""
        page = node.get("page number")
        page = page if isinstance(page, int) and page > 0 else None

        if node_type == "heading" and _CONTENTS_HEADING.fullmatch(content):
            in_contents = True
            contents_descendant_ids = {
                id(descendant)
                for child in _children(node)
                for descendant in _document_nodes(child)
            }
            continue
        if in_contents:
            # The table of contents is a tagged list with its own headings and
            # paragraphs. A numbered body heading can also end it when the
            # document has no separate chapter divider.
            next_node = nodes[index + 1] if index + 1 < len(nodes) else {}
            outside_contents_tree = id(node) not in contents_descendant_ids
            is_divider_title = (
                outside_contents_tree
                and node_type == "paragraph"
                and next_node.get("type") == "list item"
                and _NUMBER.fullmatch(str(next_node.get("content", "")).strip())
                and next_node.get("page number") == page
                and id(next_node) not in contents_descendant_ids
            )
            is_bare_divider = (
                outside_contents_tree
                and node_type == "list item"
                and _NUMBER.fullmatch(content)
                and (
                    (isinstance(node.get("font size"), (int, float)) and node["font size"] >= 24)
                    or (
                        next_node.get("type") == "paragraph"
                        and next_node.get("page number") == page
                    )
                )
            )
            is_body_heading = (
                outside_contents_tree
                and node_type == "heading"
                and _HEADING.match(content)
                and not _CONTENTS_LEADER.search(content)
            )
            if not (is_divider_title or is_bare_divider or is_body_heading):
                continue
            in_contents = False
        if index == consumed_title_index:
            continue

        if node_type == "table":
            table_id = node.get("id")
            previous_id = node.get("previous table id")
            section = current_section
            last: dict[str, Any] | None = None
            if previous_id is not None:
                if previous_id in table_section:
                    section = table_section[previous_id]
                    last = table_last.get(previous_id)
                else:
                    section = None
            table_section[table_id] = section
            for row in node.get("rows", []):
                if not isinstance(row, dict):
                    continue
                cells = row.get("cells", [])
                if not isinstance(cells, list) or len(cells) < 2:
                    raw = _cell_text(row).strip()
                    if raw:
                        if not recover:
                            raise ValueError("Malformed OpenDataLoader table row with fewer than two cells")
                        unresolved(raw, page, _locations(row), "malformed_table_row")
                        last = None
                    continue
                marker = _cell_text(cells[0]).strip()
                body = "\n".join(_cell_text(cell) for cell in cells[1:]).strip()
                if not marker:
                    if body:
                        clear_continuation = last is not None and (
                            body.startswith(("•", "-", "Guidance:"))
                            or not last["text"].rstrip().endswith((".", "!", "?"))
                        )
                        if clear_continuation:
                            _append(last, body, _locations(cells))
                        elif not recover:
                            label = "Ambiguous" if last is not None else "Orphan"
                            raise ValueError(f"{label} unnumbered OpenDataLoader table row")
                        else:
                            reason = "ambiguous_unnumbered_table_row" if last is not None else "orphan_continuation"
                            unresolved(body, page, _locations(cells), reason)
                    continue
                if not _NUMBER.fullmatch(marker):
                    if not recover:
                        raise ValueError(f"Malformed OpenDataLoader table marker: {marker[:40]}")
                    unresolved(f"{marker}\n{body}".strip(), page, _locations(cells),
                               "malformed_table_marker", marker)
                    last = None
                    continue
                if not section:
                    if not recover:
                        raise ValueError(f"Numbered table row {marker} has no numbered section")
                    unresolved(f"{marker}\n{body}".strip(), page, _locations(cells),
                               "missing_numbered_section", marker)
                    last = None
                    continue
                reference = f"{section}.{marker}"
                title = body.split("\n", 1)[0].strip() or marker
                table_candidate = _candidate(reference, title, body, page, "mandatory", _locations(cells))
                table_candidate["source_excerpt"] = f"{marker}\n{body}".strip()
                last = add(table_candidate)
                if previous_id is not None and previous_id not in table_section:
                    _flag(last, "missing_previous_table")
                if not body:
                    _flag(last, "empty_table_requirement")
            table_last[table_id] = last
            active_heading = None
            last_table_candidate = last
            previous_prose = None
            continue

        if not content or _CONTENTS_LEADER.search(content):
            continue

        if node_type == "list item" and _NUMBER.fullmatch(content):
            # Divider pages place a large bare numeral beside their title. The
            # title can precede or follow it in the tagged reading order.
            title = None
            if previous_prose and previous_prose[1] == page:
                title = previous_prose[0]
            elif index + 1 < len(nodes):
                following = nodes[index + 1]
                if following.get("type") == "paragraph" and following.get("page number") == page:
                    title = str(following.get("content", "")).strip()
                    consumed_title_index = index + 1
            title_node = nodes[index - 1] if previous_prose and previous_prose[1] == page else None
            if consumed_title_index == index + 1:
                title_node = nodes[index + 1]
            locations = _locations(node) + (_locations(title_node) if title_node else [])
            chapter = add(_candidate(content, title or content, title or content, page, "informational", locations))
            if not title:
                _flag(chapter, "missing_chapter_title")
            current_section = content
            active_heading = chapter
            last_table_candidate = None
            previous_prose = None
            continue

        match = _HEADING.match(content) if node_type in {"heading", "list item"} else None
        if match:
            reference, title = match.groups()
            heading_candidate = _candidate(reference, title, title, page, "informational", _locations(node))
            heading_candidate["source_excerpt"] = content
            heading = add(heading_candidate)
            current_section = None if heading["reference_id"].startswith("unresolved-") else reference
            active_heading = heading
            last_table_candidate = None
            previous_prose = None
            continue

        if recover and node_type == "heading" and re.match(r"^[0-9IlOo][.\dIlOo]*\s+", content):
            active_heading = unresolved(content, page, _locations(node), "malformed_heading_reference")
            current_section = None
            last_table_candidate = None
            previous_prose = None
            continue

        if node_type == "paragraph":
            # The paragraph immediately before a divider number is its title,
            # not prose belonging to the preceding section.
            next_content = str(nodes[index + 1].get("content", "")).strip() if index + 1 < len(nodes) else ""
            if _NUMBER.fullmatch(next_content) and nodes[index + 1].get("type") == "list item" and nodes[index + 1].get("page number") == page:
                previous_prose = (content, page)
                continue
            if active_heading is not None:
                _append(active_heading, content, _locations(node))
            elif last_table_candidate is not None:
                clear_continuation = (
                    content.startswith(("•", "-", "Guidance:"))
                    or not last_table_candidate["text"].rstrip().endswith((".", "!", "?"))
                )
                _append(last_table_candidate, content, _locations(node))
                if not clear_continuation:
                    _flag(last_table_candidate, "ambiguous_following_paragraph")
            previous_prose = (content, page)

    for candidate in candidates:
        parent = candidate["parent_reference"]
        if parent and parent not in by_reference:
            _flag(candidate, f"missing_immediate_parent:{parent}")
    return candidates


def extract_with_recovery(payload: dict) -> tuple[list[dict], dict | None]:
    """Keep strict parsing as the first pass and retain structural failures."""
    try:
        strict_candidates = parse_structured_requirements(payload)
    except ValueError as exc:
        recovered = parse_structured_requirements(payload, recover=True)
        unresolved_count = sum(row["reference_id"].startswith("unresolved-") for row in recovered)
        if not unresolved_count:
            raise
        return recovered, {"reason": str(exc), "unresolved_count": unresolved_count}
    else:
        # OCR can turn one heading into an unnumbered block while the rest of
        # the document parses. Detect that partial result before storing it.
        recovered = parse_structured_requirements(payload, recover=True)
    unresolved_count = sum(row["reference_id"].startswith("unresolved-") for row in recovered)
    if unresolved_count:
        return recovered, {"reason": "Potential numbered source blocks need review",
                           "unresolved_count": unresolved_count}
    return strict_candidates, None
