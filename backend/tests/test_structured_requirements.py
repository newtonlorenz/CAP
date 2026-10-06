"""Synthetic tagged JSON tests; no source document wording is copied here."""

import pytest
import json
from pathlib import Path

from app.services.structured_requirements import parse_structured_requirements, extract_with_recovery
from app.services.pdf_worker import _promote_ocr_numbered_paragraphs


def block(kind, content, page, x=1):
    return {
        "type": kind,
        "content": content,
        "page number": page,
        "bounding box": [x, 2, x + 10, 12],
    }


def table_row(marker, *parts, page):
    return {
        "type": "table row",
        "cells": [
            {"type": "table cell", "kids": [block("paragraph", marker, page, 1)]} if marker else {"type": "table cell", "kids": []},
            {"type": "table cell", "kids": [block("paragraph", part, page, 20) for part in parts]},
        ],
    }


def table(identifier, rows, page, previous=None):
    result = {"type": "table", "id": identifier, "page number": page, "rows": rows}
    if previous is not None:
        result["previous table id"] = previous
    return result


def document(*nodes):
    return {"kids": list(nodes)}


def test_hierarchy_toc_nested_children_and_continuations():
    payload = document(
        block("heading", "Contents", 1),
        {"type": "list", "list items": [
            block("list item", "1.1 Overview", 1),
            block("list item", "1.1.1 Details..... 4", 1),
        ]},
        block("paragraph", "Sample chapter", 2),
        block("list item", "1", 2),
        block("heading", "1.1 Overview", 3),
        {"type": "list", "list items": [{
            **block("list item", "1.1.1 Details", 3),
            "kids": [
                block("paragraph", "Introductory information.", 3),
                table(10, [table_row("1", "The system shall record:", "• time", "• actor", page=3)], 3),
            ],
        }]},
        table(11, [table_row("", "• reason", page=4), table_row("2", "The system shall report.", page=4)], 4, previous=10),
    )
    rows = parse_structured_requirements(payload)
    assert [row["reference_id"] for row in rows] == ["1", "1.1", "1.1.1", "1.1.1.1", "1.1.1.2"]
    assert [row["parent_reference"] for row in rows] == [None, "1", "1.1", "1.1.1", "1.1.1"]
    assert rows[0]["title"] == "Sample chapter"
    assert rows[2]["requirement_type"] == "informational"
    assert "Introductory information." in rows[2]["original_text"]
    assert rows[3]["requirement_type"] == "mandatory"
    assert rows[3]["original_text"] == "The system shall record:\n• time\n• actor\n• reason"
    assert "• reason" not in rows[4]["text"]
    assert rows[3]["page_number"] == 3
    assert {loc["page_number"] for loc in rows[3]["source_locations"]} == {3, 4}
    assert all(len(loc["bounding_box"]) == 4 for loc in rows[3]["source_locations"])
    assert all(not row["needs_review"] for row in rows)
    assert all(row["parser_strategy"] == "opendataloader" for row in rows)


def test_contents_can_end_at_numbered_body_heading_without_divider():
    payload = document(
        {**block("heading", "Contents", 1), "kids": [
            block("heading", "1 Nested contents entry", 1),
            block("list item", "2", 1),
        ]},
        block("heading", "1.1 Contents entry..... 2", 1),
        block("heading", "1 Main topic", 2),
        block("heading", "1.1 Section", 2),
        table(1, [table_row("1", "The system shall log events.", page=2)], 2),
    )
    rows = parse_structured_requirements(payload)
    assert [row["reference_id"] for row in rows] == ["1", "1.1", "1.1.1"]
    assert rows[0]["title"] == "Main topic"
    assert rows[-1]["parent_reference"] == "1.1"
    assert all(not row["needs_review"] for row in rows)


@pytest.mark.parametrize("title", ["Table of contents", "TABLE OF CONTENTS", " Table   of   Contents: "])
def test_table_of_contents_skips_malformed_leaders_before_body(title):
    rows = parse_structured_requirements(document(
        block("heading", title, 3),
        block("list item", "1.1 Sample entry................................tt", 3),
        block("heading", "1.2 Another entry...............................x", 3),
        block("list item", "1.3 Plain contents entry", 3),
        block("heading", "1.4 Later contents entry........................iv", 4),
        block("heading", "1 Main topic", 5),
        block("heading", "1.1 Sample entry", 6),
    ))
    assert [row["reference_id"] for row in rows] == ["1", "1.1"]
    assert [row["page_number"] for row in rows] == [5, 6]


def test_malformed_contents_leader_is_not_a_body_heading():
    rows = parse_structured_requirements(document(
        block("heading", "1 Main topic", 1),
        block("list item", "1.1 Index entry.................................tt", 1),
        block("heading", "1.1 Real section", 2),
    ))
    assert [row["reference_id"] for row in rows] == ["1", "1.1"]
    assert rows[1]["title"] == "Real section"


def test_duplicate_body_heading_still_fails_after_contents():
    with pytest.raises(ValueError, match="Duplicate OpenDataLoader reference: 1.1"):
        parse_structured_requirements(document(
            block("heading", "Table of contents", 1),
            block("list item", "1.1 Index entry.................................tt", 1),
            block("heading", "1 Main topic", 2),
            block("heading", "1.1 First section", 2),
            block("heading", "1.1 Repeated section", 3),
        ))


def test_chapter_title_after_divider_and_section_paragraphs():
    rows = parse_structured_requirements(document(
        block("list item", "2", 1),
        block("paragraph", "Second chapter", 1),
        block("heading", "2.1 Context", 2),
        block("paragraph", "First paragraph.", 2),
        block("paragraph", "Second paragraph.", 3),
    ))
    assert [r["reference_id"] for r in rows] == ["2", "2.1"]
    assert rows[0]["original_text"] == "Second chapter"
    assert rows[1]["original_text"] == "Context First paragraph. Second paragraph."
    assert {loc["page_number"] for loc in rows[1]["source_locations"]} == {2, 3}


def test_missing_immediate_parent_is_flagged_without_reparenting():
    rows = parse_structured_requirements(document(
        block("heading", "1.2.1 Missing section", 1),
        table(1, [table_row("1", "A source obligation.", page=1)], 1),
    ))
    assert rows[0]["parent_reference"] == "1.2"
    assert rows[0]["needs_review"]
    assert "missing_immediate_parent:1.2" in rows[0]["review_reason"]
    assert rows[1]["parent_reference"] == "1.2.1"


def test_unqualified_table_row_fails_without_inventing_a_root():
    with pytest.raises(ValueError, match="has no numbered section"):
        parse_structured_requirements(document(
            table(1, [table_row("1", "A source obligation.", page=1)], 1),
        ))


def test_one_cell_table_row_is_recoverable_and_never_silently_dropped():
    raw = "The service shall preserve this orphaned cell."
    single_cell = {"type": "table row", "cells": [
        {"type": "table cell", "kids": [block("paragraph", raw, 2)]},
    ]}
    payload = document(block("heading", "1 Root", 1), table(7, [single_cell], 2))
    with pytest.raises(ValueError, match="fewer than two cells"):
        parse_structured_requirements(payload)
    rows, diagnostic = extract_with_recovery(payload)
    orphan = rows[-1]
    assert diagnostic["unresolved_count"] == 1
    assert orphan["reference_id"].startswith("unresolved-")
    assert orphan["original_text"] == orphan["source_excerpt"] == raw
    assert orphan["page_number"] == 2
    assert orphan["source_locations"][0]["page_number"] == 2
    assert orphan["review_reason"] == "malformed_table_row"
    assert orphan["needs_review"]


def test_arbitrary_heading_depth_and_bounded_generated_title():
    long_source = ("The system shall " + "record details " * 50).rstrip()
    rows = parse_structured_requirements(document(
        block("heading", "1 Root", 1),
        block("heading", "1.2 Second", 1),
        block("heading", "1.2.3 Third", 1),
        block("heading", "1.2.3.4 Fourth", 1),
        block("heading", "1.2.3.4.5 Fifth", 1),
        table(1, [table_row("6", long_source, page=1)], 1),
    ))
    assert rows[-1]["reference_id"] == "1.2.3.4.5.6"
    assert rows[-1]["parent_reference"] == "1.2.3.4.5"
    assert all(not row["needs_review"] for row in rows)
    assert len(rows[-1]["title"]) == 500
    assert rows[-1]["text"] == long_source
    assert rows[-1]["original_text"] == long_source


def test_following_paragraph_continues_unfinished_table_sentence():
    rows = parse_structured_requirements(document(
        block("list item", "1", 1),
        block("paragraph", "First chapter", 1),
        block("heading", "1.1 Section", 2),
        block("list item", "1.1.1 Controls", 2),
        table(1, [table_row("1", "The system shall record the", page=2)], 2),
        block("paragraph", "event.", 3),
    ))
    assert rows[-1]["text"] == "The system shall record the event."
    assert not rows[-1]["needs_review"]
    assert {loc["page_number"] for loc in rows[-1]["source_locations"]} == {2, 3}


def test_running_footer_text_block_is_not_attached_to_last_requirement():
    rows = parse_structured_requirements(document(
        block("heading", "1 Root", 1),
        table(1, [table_row("1", "A source obligation.", page=1)], 1),
        {"type": "text block", "kids": [
            {**block("heading", "Document title Page 2", 2), "font size": 7.5},
            {**block("paragraph", "example.invalid", 2), "font size": 7.0},
        ]},
    ))
    assert rows[-1]["text"] == "A source obligation."
    assert not rows[-1]["needs_review"]


def test_duplicate_reference_is_a_failure():
    with pytest.raises(ValueError, match="Duplicate OpenDataLoader reference: 1.1"):
        parse_structured_requirements(document(
            block("heading", "1.1 First", 1),
            block("heading", "1.1 Second", 2),
        ))


def test_orphan_continuation_is_a_failure():
    with pytest.raises(ValueError, match="Orphan unnumbered"):
        parse_structured_requirements(document(
            table(2, [table_row("", "An unattached tail.", page=2)], 2, previous=1),
        ))


RECOVERY_CORPUS = json.loads(
    (Path(__file__).parent / "fixtures" / "structured_recovery_corpus.json").read_text()
)


@pytest.mark.parametrize("case", RECOVERY_CORPUS, ids=lambda case: case["name"])
def test_structural_recovery_corpus_preserves_ambiguous_source(case):
    nodes = []
    for item in case["nodes"]:
        kind, *parts = item
        if kind == "table":
            marker, body, page = parts
            nodes.append(table(10, [table_row(marker, body, page=page)], page))
        elif kind == "continuation":
            body, page = parts
            nodes.append(table(11, [table_row("", body, page=page)], page, previous=99))
        elif kind == "table_pair":
            marker, first, second, page = parts
            nodes.append(table(12, [table_row(marker, first, page=page),
                                    table_row("", second, page=page)], page))
        elif kind == "one_cell_table":
            content, page = parts
            nodes.append(table(13, [{"type": "table row", "cells": [
                {"type": "table cell", "kids": [block("paragraph", content, page)]},
            ]}], page))
        elif kind == "ocr":
            content, page = parts
            nodes.append({**block("paragraph", content, page), "font": "GlyphLessFont"})
        else:
            content, page = parts
            nodes.append(block(kind, content, page))
    payload = document(*nodes)
    _promote_ocr_numbered_paragraphs(payload)
    rows, diagnostic = extract_with_recovery(payload)
    unresolved = [row for row in rows if row["reference_id"].startswith("unresolved-")]
    assert len(unresolved) == 1
    assert diagnostic and diagnostic["unresolved_count"] == 1
    row = unresolved[0]
    assert case["reason"] in row["review_reason"]
    assert row["original_text"] == case.get("extracted", case["raw"])
    assert row["source_excerpt"] == case["raw"]
    assert row["page_number"] == case["page"]
    assert row["source_locations"]
    assert row["needs_review"]
    assert row["confidence_score"] <= 0.5
    if case["name"] == "scan with corrupt heading":
        assert [item["reference_id"] for item in rows[:2]] == ["4", "4.1"]
