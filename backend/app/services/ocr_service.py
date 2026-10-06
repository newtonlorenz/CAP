"""Optional local OCR, using Tesseract and PDFium without Ghostscript."""

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium

from app.services.document_reader import default_reader


@dataclass
class OCRRunResult:
    applied: bool
    output_path: str | None
    error: str | None


def run_ocr_with_fallback(
    input_path: str,
    *,
    work_dir: str,
    languages: str,
    timeout_seconds: int,
) -> OCRRunResult:
    """Keep native text pages and OCR scanned pages within one total deadline.

    Called inside the bounded PDF worker. The source PDF is never overwritten.
    """
    executable = shutil.which("tesseract")
    if not executable:
        return OCRRunResult(
            False, None, "Local OCR requires Tesseract; install the OCR image or binary."
        )
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    output = work / "searchable.pdf"
    deadline = time.monotonic() + timeout_seconds
    try:
        native_pages = default_reader.read_pages(input_path)
        with pdfium.PdfDocument(input_path) as source, pdfium.PdfDocument.new() as result:
            for index, page in enumerate(native_pages):
                if time.monotonic() >= deadline:
                    raise TimeoutError
                if len(page["text"].strip()) >= 40:
                    result.import_pages(source, [index])
                    continue
                image = work / f"page-{index}.png"
                image.write_bytes(default_reader.render_png(input_path, index + 1, dpi=200))
                prefix = work / f"page-{index}"
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                completed = subprocess.run(
                    [executable, str(image), str(prefix), "-l", languages, "pdf"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=remaining,
                    check=False,
                )
                generated = prefix.with_suffix(".pdf")
                if completed.returncode or not generated.is_file():
                    return OCRRunResult(
                        False, None, "Tesseract failed; check the installed OCR languages."
                    )
                with pdfium.PdfDocument(generated) as ocr_page:
                    result.import_pages(ocr_page)
                image.unlink()
            result.save(output)
        return OCRRunResult(True, str(output), None)
    except (subprocess.TimeoutExpired, TimeoutError):
        return OCRRunResult(False, None, "Local OCR exceeded its time limit.")
    except Exception:
        return OCRRunResult(False, None, "Local OCR could not process this PDF.")
