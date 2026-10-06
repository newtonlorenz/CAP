from app.services.ai_parser import parse_requirements_rule_based
from app.services.section_parser import infer_numbered_rows, parse_section_blocks


def test_parse_section_blocks_supports_split_headings():
    lines = [
        "3.2.1",
        "Customer registration",
        "1",
        "The gambling system shall store customer details.",
    ]
    blocks = parse_section_blocks(lines)
    assert blocks
    assert blocks[0].section_id == "3.2.1"
    assert blocks[0].title == "Customer registration"


def test_infer_numbered_rows_recovers_tt_sequence_marker():
    lines = [
        "1",
        "One shall.",
        "2",
        "Two shall.",
        "3",
        "Three shall.",
        "tt",
        "Four shall.",
        "5",
        "Five shall.",
    ]
    rows = infer_numbered_rows(lines)
    assert [row.marker for row in rows] == ["1", "2", "3", "4", "5"]


def test_rule_parser_handles_split_headings_and_row_markers():
    text = """3.2.1
Customer registration
1
During registration the gambling system shall collect and store customer details.
2
The gambling system must verify age.
3
The gambling system shall record registration time.
tt
The gambling system shall confirm the player is not in ROFUS.
5
The gambling system must use encrypted transport.
"""
    requirements = parse_requirements_rule_based(text, "standard", 12)
    refs = {item["reference_id"] for item in requirements}
    assert "3.2.1" in refs
    assert "3.2.1.4" in refs
    assert "3.2.1.5" in refs
