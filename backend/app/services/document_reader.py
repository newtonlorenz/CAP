"""Local document IO boundary. PDFium renders/reads; pdfplumber supplies word geometry."""

from contextlib import closing
from io import BytesIO
from typing import Protocol

import pdfplumber
import pypdfium2 as pdfium


class DocumentReader(Protocol):
    def validate(self, source, *, max_pages: int) -> int: ...
    def read_pages(self, source) -> list[dict]: ...
    def read_layout(self, source) -> list[dict]: ...
    def render_png(self, source, page_number: int, *, dpi: int) -> bytes: ...


class LocalPDFReader:
    def validate(self, source, *, max_pages: int) -> int:
        with pdfium.PdfDocument(source) as document:
            if not 0 < len(document) <= max_pages:
                raise ValueError("PDF exceeds the page limit or has no pages.")
            return len(document)

    def read_pages(self, source) -> list[dict]:
        pages = []
        with pdfium.PdfDocument(source) as document:
            for index in range(len(document)):
                with closing(document[index]) as page, closing(page.get_textpage()) as textpage:
                    pages.append({"page_number": index + 1, "text": textpage.get_text_bounded()})
        return pages

    def read_layout(self, source) -> list[dict]:
        pages = []
        with pdfplumber.open(source) as document:
            for index, page in enumerate(document.pages):
                words = page.extract_words()
                pages.append(
                    {
                        "page_number": index + 1,
                        "width": float(page.width),
                        "height": float(page.height),
                        "words": [
                            (w["x0"], w["top"], w["x1"], w["bottom"], w["text"]) for w in words
                        ],
                    }
                )
                page.close()
        return pages

    def render_png(self, source, page_number: int, *, dpi: int) -> bytes:
        if not 1 <= dpi <= 300:
            raise ValueError("Rendering resolution must be between 1 and 300 DPI.")
        with pdfium.PdfDocument(source) as document:
            if not 1 <= page_number <= len(document):
                raise ValueError("PDF page is out of bounds.")
            with closing(document[page_number - 1]) as page:
                width, height = page.get_size()
                if width * height * (dpi / 72) ** 2 > 25_000_000:
                    raise ValueError("PDF page exceeds the rendering pixel limit.")
                with closing(page.render(scale=dpi / 72)) as bitmap:
                    output = BytesIO()
                    image = bitmap.to_pil()
                    try:
                        image.save(output, format="PNG")
                    finally:
                        image.close()
                    return output.getvalue()


default_reader: DocumentReader = LocalPDFReader()
