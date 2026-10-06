import pytest

from app.services import pdf_preprocessor as preprocessor


class _Adapter:
    def __init__(self, pages):
        self._pages = pages

    def extract_pages(self, file_path: str):
        return self._pages


def _layout_line(text: str, line_number: int) -> dict:
    return {
        "text": text,
        "line_number": line_number,
        "x0": 10.0,
        "y0": float(line_number * 10),
        "x1": 300.0,
        "y1": float(line_number * 10 + 8),
    }


@pytest.mark.asyncio
async def test_preprocess_uses_parseability_for_fallback_reason(monkeypatch):
    strong_text = (
        "3.1 General information\n"
        "1\n"
        "The gambling system shall present clear information to the customer.\n"
        "2\n"
        "The gambling system must keep an audit log for every session.\n"
    )
    weak_text = (
        "This section describes various topics without structured numbering but with long content. "
        "The system must do a number of things and should preserve records for later checks. "
        "The system may provide additional context where possible. "
        "This paragraph intentionally omits section headings and relies on narrative text only. "
    )

    native_pages = [
        {"page_number": 1, "text": strong_text},
        {"page_number": 2, "text": weak_text},
        {"page_number": 3, "text": weak_text},
        {"page_number": 4, "text": strong_text},
    ]
    layout_pages = [
        {
            "page_number": page["page_number"],
            "text": page["text"],
            "layout_lines": [
                _layout_line(line, idx + 1) for idx, line in enumerate(page["text"].splitlines())
            ],
            "word_count": len(page["text"].split()),
        }
        for page in native_pages
    ]

    monkeypatch.setattr(preprocessor, "extract_layout_pages", lambda _: layout_pages)
    monkeypatch.setattr(preprocessor.settings, "vision_fallback_enabled", True)
    monkeypatch.setattr(preprocessor.settings, "parseability_low_ratio_threshold", 0.15)
    monkeypatch.setattr(preprocessor.settings, "ocr_mode", "image_only")

    result = await preprocessor.preprocess_pdf_for_extraction(
        "/tmp/fake.pdf",
        _Adapter(native_pages),
        "standard",
    )

    assert result.parseability_score < 0.8
    assert len(result.low_quality_pages) >= 2
    assert result.fallback_trigger_reason is not None
    assert "Low parseability ratio" in result.fallback_trigger_reason
    assert result.ocr_applied is False


def test_should_run_ocr_image_only_threshold():
    should_run, reason = preprocessor._should_run_ocr(
        mode="image_only",
        enabled=True,
        image_only_ratio=0.60,
    )
    assert should_run is True
    assert "image-only ratio" in reason

    should_skip, reason_skip = preprocessor._should_run_ocr(
        mode="image_only",
        enabled=True,
        image_only_ratio=0.10,
    )
    assert should_skip is False
    assert "below threshold" in reason_skip
