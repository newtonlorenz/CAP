"""Resource-bounded subprocess for PDF parsing and OCR before page-level extraction."""

import asyncio
import json
import os
import re
import signal
import sys
import tempfile
import hashlib
from dataclasses import asdict
from pathlib import Path

from app.config import settings


NUMBERED_PARAGRAPH = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+\S+")
SUSPECT_NUMBERED_PARAGRAPH = re.compile(r"^\s*[IlOo](?:\.[0-9IlOo]+)+\s+\S+")


def _promote_ocr_numbered_paragraphs(payload):
    """Recover numbered headings when OCR makes every text block a paragraph."""
    if isinstance(payload, list):
        for item in payload:
            _promote_ocr_numbered_paragraphs(item)
    elif isinstance(payload, dict):
        if (
            payload.get("type") == "paragraph"
            and payload.get("font") == "GlyphLessFont"
            and (NUMBERED_PARAGRAPH.match(str(payload.get("content") or ""))
                 or SUSPECT_NUMBERED_PARAGRAPH.match(str(payload.get("content") or "")))
        ):
            payload["type"] = "heading"
        for value in payload.values():
            if isinstance(value, (dict, list)):
                _promote_ocr_numbered_paragraphs(value)


async def bounded_preprocess(file_path, document_type, *, structure_engine="native"):
    from app.services.pdf_preprocessor import PreprocessResult, PageQuality

    with tempfile.TemporaryDirectory(prefix="cap-pdf-") as staging:
        output = Path(staging) / "result.json"
        child_env = dict(
            os.environ,
            TMPDIR=staging,
            PDF_MAX_PAGES=str(settings.pdf_max_pages),
            PDF_PREPROCESS_TIMEOUT_SECONDS=str(settings.pdf_preprocess_timeout_seconds),
            PYTHONPATH=str(Path(__file__).resolve().parents[2])
            + os.pathsep
            + os.environ.get("PYTHONPATH", ""),
        )
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.services.pdf_worker",
            str(Path(file_path).resolve()),
            document_type,
            str(output),
            structure_engine,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
            env=child_env,
        )
        try:
            await asyncio.wait_for(process.wait(), timeout=settings.pdf_preprocess_timeout_seconds)
            if process.returncode != 0 or not output.exists():
                if structure_engine == "opendataloader":
                    raise ValueError(
                        "Structured PDF import failed. Check the OpenDataLoader installation, Java runtime, "
                        "source readability and processing limits. No alternative parser was used."
                    )
                raise ValueError(
                    "PDF preprocessing failed. Check that the PDF is readable, unencrypted and within the page limit."
                )
            if output.stat().st_size > 32 * 1024 * 1024:
                raise ValueError("Extracted PDF content exceeds the safe processing limit.")
            data = json.loads(output.read_text())
            data["page_quality"] = [PageQuality(**row) for row in data["page_quality"]]
            return PreprocessResult(**data)
        except asyncio.TimeoutError as exc:
            raise ValueError(
                "PDF preprocessing exceeded its time limit. Split the PDF into smaller source documents and try again."
            ) from exc
        finally:
            # The worker may have exited while a native child is still alive.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if process.returncode is None:
                await process.wait()


def main():
    import resource
    from app.services.document_reader import default_reader
    from app.services.pdf_parser import PdfParser
    from app.services.pdf_preprocessor import preprocess_pdf_for_extraction

    # CPU and output limits also bound native parsing before asyncio regains control.
    resource.setrlimit(
        resource.RLIMIT_CPU,
        (settings.pdf_preprocess_timeout_seconds, settings.pdf_preprocess_timeout_seconds + 1),
    )
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
    if sys.platform.startswith("linux"):
        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    source, kind, output, *options = sys.argv[1:]
    structure_engine = options[0] if options else "native"
    page_count = default_reader.validate(source, max_pages=settings.pdf_max_pages)
    result = asyncio.run(preprocess_pdf_for_extraction(source, PdfParser(), kind))
    if structure_engine == "opendataloader":
        from app.services.structured_pdf import read_structured_pdf, ENGINE_VERSION
        from app.services.structured_requirements import extract_with_recovery

        with tempfile.TemporaryDirectory(prefix="structure-", dir=Path(output).parent) as staging:
            payload = read_structured_pdf(
                result.ocr_pdf_path or source,
                staging,
                timeout=settings.pdf_preprocess_timeout_seconds,
            )
            if payload.get("number of pages") != page_count:
                raise ValueError("Structured PDF extraction did not cover the complete document.")
            if result.ocr_applied:
                _promote_ocr_numbered_paragraphs(payload)
            result.structured_requirements, recovery_diagnostic = extract_with_recovery(payload)
            if recovery_diagnostic:
                result.diagnostics["structured_recovery"] = recovery_diagnostic
        if not result.structured_requirements:
            raise ValueError("No numbered requirements were recovered. Review the source format.")
        result.diagnostics["structured_source"] = {
            "engine": "opendataloader", "engine_version": ENGINE_VERSION,
            "source_sha256": hashlib.sha256(Path(source).read_bytes()).hexdigest(),
            "pages": page_count,
        }
        result.diagnostics["canonical_blocks"] = [
            {key: row[key] for key in ("reference_id", "source_reference", "page_number", "source_locations", "review_reason") if key in row}
            for row in result.structured_requirements
        ]
    elif structure_engine != "native":
        raise ValueError("Unknown PDF structure engine.")
    data = asdict(result)
    # The OCR PDF lives only until the parent staging directory is removed.
    data.pop("ocr_pdf_path")
    Path(output).write_text(json.dumps(data))


if __name__ == "__main__":
    main()
