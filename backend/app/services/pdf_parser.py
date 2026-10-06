"""Local PDF parsing with optional, explicitly configured AI fallback."""

from app.services.ai_parser import parse_requirements_from_text
from app.services.pdf_extractor import extract_text_from_pdf

NATIVE_PIPELINE_VERSION = "born_digital_v4"


class PdfParser:
    def extract_pages(self, file_path: str) -> list[dict]:
        return extract_text_from_pdf(file_path)

    async def parse_requirements(
        self, text, document_type, page_number, event_logger=None, provider_config=None
    ) -> list[dict]:
        return await parse_requirements_from_text(
            text=text,
            document_type=document_type,
            page_number=page_number,
            event_logger=event_logger,
            provider_config=provider_config,
        )
