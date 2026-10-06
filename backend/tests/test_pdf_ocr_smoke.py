"""Runtime smoke for the OCR image and the combined structured OCR image.

Run with python directly; production images do not contain pytest.
"""

import asyncio
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont
import pypdfium2 as pdfium

from app.services.pdf_worker import bounded_preprocess
from reportlab.pdfgen.canvas import Canvas


class TestPdfOcrSmoke(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("CAP_OCR_SMOKE_ENGINE") in {"native", "opendataloader"},
        "Run explicitly in an OCR image with CAP_OCR_SMOKE_ENGINE set",
    )
    def test_mixed_native_and_scanned_pages(self):
        engine = os.environ["CAP_OCR_SMOKE_ENGINE"]
        with tempfile.TemporaryDirectory(prefix="cap-mixed-ocr-") as directory:
            root = Path(directory)
            scan = root / "scan.pdf"
            image = Image.new("RGB", (1700, 2200), "white")
            draw = ImageDraw.Draw(image)
            draw.text((130, 160), "1 Audit controls", fill="black", font=ImageFont.load_default(size=58))
            draw.text((130, 280), "1.1 Record retention", fill="black", font=ImageFont.load_default(size=46))
            draw.text((130, 370), "The system shall retain an audit trail.", fill="black", font=ImageFont.load_default(size=36))
            image.save(scan, "PDF", resolution=180)
            native = root / "native.pdf"
            canvas = Canvas(str(native))
            canvas.setFont("Helvetica-Bold", 18)
            canvas.drawString(60, 760, "2 Reporting")
            canvas.setFont("Helvetica-Bold", 14)
            canvas.drawString(60, 710, "2.1 Report availability")
            canvas.setFont("Helvetica", 11)
            canvas.drawString(60, 680, "The system shall preserve the original digital report wording.")
            canvas.save()
            source = root / "mixed.pdf"
            with pdfium.PdfDocument.new() as combined, pdfium.PdfDocument(scan) as scanned, pdfium.PdfDocument(native) as digital:
                combined.import_pages(scanned)
                combined.import_pages(digital)
                combined.save(source)
            original = source.read_bytes()
            with patch.dict(os.environ, {"OCR_ENABLED": "true", "OCR_MODE": "image_only"}):
                result = asyncio.run(bounded_preprocess(str(source), "Custom certification", structure_engine=engine))
            self.assertTrue(result.ocr_applied)
            self.assertEqual(result.ocr_pages, 1)
            self.assertEqual(len(result.pages), 2)
            self.assertIn("audit trail", result.pages[0]["text"].lower())
            self.assertIn("original digital report wording", result.pages[1]["text"])
            self.assertEqual(source.read_bytes(), original)
            if engine == "opendataloader":
                references = {item["reference_id"] for item in result.structured_requirements}
                self.assertTrue({"1", "1.1", "2", "2.1"}.issubset(references), references)

    @unittest.skipUnless(
        os.environ.get("CAP_OCR_SMOKE_ENGINE") in {"native", "opendataloader"},
        "Run explicitly in an OCR image with CAP_OCR_SMOKE_ENGINE set",
    )
    def test_image_only_numbered_pdf(self):
        engine = os.environ["CAP_OCR_SMOKE_ENGINE"]

        with tempfile.TemporaryDirectory(prefix="cap-ocr-smoke-") as directory:
            source = Path(directory) / "scan.pdf"
            image = Image.new("RGB", (1700, 2200), "white")
            draw = ImageDraw.Draw(image)
            draw.text((130, 160), "1 Audit controls", fill="black", font=ImageFont.load_default(size=58))
            draw.text((130, 280), "1.1 Record retention", fill="black", font=ImageFont.load_default(size=46))
            draw.text(
                (130, 370), "The system shall retain an audit trail.",
                fill="black", font=ImageFont.load_default(size=36),
            )
            image.save(source, "PDF", resolution=180)

            with pdfium.PdfDocument(str(source)) as pdf:
                self.assertEqual(len(pdf), 1)
                self.assertFalse(pdf[0].get_textpage().get_text_range().strip())

            with patch.dict(os.environ, {"OCR_ENABLED": "true", "OCR_MODE": "image_only"}):
                result = asyncio.run(
                    bounded_preprocess(str(source), "Custom certification", structure_engine=engine)
                )

            self.assertTrue(result.ocr_applied)
            self.assertEqual(result.ocr_pages, 1)
            self.assertEqual(len(result.pages), 1)
            self.assertIn("audit trail", result.pages[0]["text"].lower())
            self.assertIsNone(result.ocr_pdf_path)

            if engine == "opendataloader":
                requirements = result.structured_requirements or []
                by_reference = {row["reference_id"]: row for row in requirements}
                self.assertIn("1", by_reference)
                self.assertIn("1.1", by_reference)
                self.assertEqual(by_reference["1.1"]["parent_reference"], "1")
                self.assertIn("audit trail", by_reference["1.1"]["text"].lower())
                self.assertEqual(
                    result.diagnostics["structured_source"]["source_sha256"],
                    hashlib.sha256(source.read_bytes()).hexdigest(),
                )
            else:
                self.assertIsNone(result.structured_requirements)


if __name__ == "__main__":
    unittest.main()
