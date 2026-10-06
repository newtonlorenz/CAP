import asyncio

import pytest


@pytest.mark.asyncio
async def test_parse_requirements_logs_ai_timeout(monkeypatch):
    from app.config import settings
    from app.services import ai_parser

    class TimeoutParser(ai_parser.AIParser):
        @property
        def provider(self) -> str:
            return "openai"

        @property
        def model(self) -> str:
            return "test"

        async def parse(self, text: str, document_type: str, page_number: int):
            raise asyncio.TimeoutError()

    monkeypatch.setattr(settings, "ai_provider_setting", "openai")
    monkeypatch.setattr(ai_parser, "get_parser", lambda: TimeoutParser())

    events = []

    async def logger(payload):
        events.append(payload)

    with pytest.raises(ValueError, match="incomplete"):
        await ai_parser.parse_requirements_from_text(
            "The operator shall keep records and retain logs.",
            document_type="standard",
            page_number=3,
            use_ai=True,
            event_logger=logger,
        )

    assert any(event.get("stage") == "ai_timeout" for event in events)


@pytest.mark.asyncio
async def test_unanchored_ai_results_are_flagged_for_review(monkeypatch):
    from app.config import settings
    from app.services import ai_parser

    class UnanchoredParser(ai_parser.AIParser):
        @property
        def provider(self) -> str:
            return "openai"

        @property
        def model(self) -> str:
            return "test"

        async def parse(self, text: str, document_type: str, page_number: int):
            return [
                {
                    "reference_id": "3.2.1",
                    "title": "Example",
                    "text": "Completely synthetic sentence not in source text",
                    "requirement_type": "mandatory",
                    "parent_reference": "3.2",
                    "confidence": 0.9,
                }
            ]

    monkeypatch.setattr(settings, "ai_provider_setting", "openai")
    monkeypatch.setattr(ai_parser, "get_parser", lambda: UnanchoredParser())

    results = await ai_parser.parse_requirements_from_text(
        "The system shall keep records.",
        document_type="standard",
        page_number=8,
        use_ai=True,
        min_similarity=0.95,
    )

    assert len(results) == 1
    assert results[0].get("needs_review") is True
    assert results[0].get("review_reason") == "anchor_mismatch"
