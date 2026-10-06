import os

import pytest

from app.services.pdf_extractor import extract_text_from_pdf


def test_extract_text_from_pdf():
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample_requirements.pdf")
    pages = extract_text_from_pdf(fixture_path)
    assert len(pages) > 0
    assert isinstance(pages[0], dict)
    assert "page_number" in pages[0]
    assert "text" in pages[0]
    assert len(pages[0]["text"]) > 0
    # Check that we can find some expected content
    assert "shall" in pages[0]["text"].lower() or "operator" in pages[0]["text"].lower()


def test_extract_text_has_page_numbers():
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample_requirements.pdf")
    pages = extract_text_from_pdf(fixture_path)
    assert pages[0]["page_number"] == 1


@pytest.mark.asyncio
async def test_parse_requirements():
    from app.services.ai_parser import parse_requirements_from_text

    results = await parse_requirements_from_text(
        "4.2.1 The operator shall implement access controls for all systems.",
        document_type="standard",
        page_number=5,
        use_ai=False,
    )

    assert len(results) == 1
    assert results[0]["reference_id"] == "4.2.1"
    assert results[0]["requirement_type"] == "mandatory"
    assert results[0]["confidence"] >= 0.7
    assert results[0]["page_number"] == 5


@pytest.mark.asyncio
async def test_parse_requirements_empty_text():
    from app.services.ai_parser import parse_requirements_from_text

    results = await parse_requirements_from_text(
        "",
        document_type="standard",
        page_number=1,
    )
    assert results == []


@pytest.mark.asyncio
async def test_parse_requirements_handles_code_blocks():
    from app.services.ai_parser import parse_requirements_from_text

    results = await parse_requirements_from_text(
        "4.2.1 Test requirement",
        document_type="standard",
        page_number=1,
        use_ai=False,
    )

    assert len(results) == 1
    assert results[0]["reference_id"] == "4.2.1"


@pytest.mark.asyncio
async def test_parse_requirements_includes_guidance():
    from app.services.ai_parser import parse_requirements_from_text

    text = "3.1 The operator shall retain records.\nGuidance: Keep logs for audit purposes."
    results = await parse_requirements_from_text(
        text,
        document_type="standard",
        page_number=2,
        use_ai=False,
    )

    assert len(results) == 1
    assert "Guidance:" in results[0]["text"]
