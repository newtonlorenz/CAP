from app.services.text_normalizer import (
    dehyphenate_lines,
    detect_repeated_lines,
    remove_repeated_lines,
)
from app.services.pdf_extractor import _table_is_duplicate


def test_dehyphenate_lines():
    lines = ["vul-", "nerability scanning"]
    result = dehyphenate_lines(lines)
    assert result == ["vulnerability scanning"]


def test_header_footer_removal():
    pages_lines = [
        ["Header Page 1", "Content A", "1"],
        ["Header Page 2", "Content B", "2"],
        ["Header Page 3", "Content C", "3"],
    ]
    repeated = detect_repeated_lines(pages_lines, top_n=1, bottom_n=1, threshold_ratio=0.6)
    cleaned = remove_repeated_lines(pages_lines[0], repeated)
    assert cleaned == ["Content A"]


def test_table_duplicate_detection():
    table = [["1", "The base platform shall require customers to accept terms."]]
    text = "1 The base platform shall require customers to accept terms."
    assert _table_is_duplicate(table, text) is True
