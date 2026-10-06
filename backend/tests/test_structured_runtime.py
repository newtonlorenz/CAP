"""Opt-in runtime test: install the pinned optional extra and Java before running."""

import json
import os
import subprocess

import pytest
from reportlab.pdfgen import canvas

from app.services import structured_pdf
from app.services.structured_pdf import read_structured_pdf


@pytest.mark.parametrize(
    ("reported_version", "available"),
    [("openjdk version \"21.0.12\"", True), ("java version \"17.0.2\"", True),
     ("java version \"1.8.0_392\"", False), ("unexpected output", False)],
)
def test_structured_availability_requires_supported_java(
    monkeypatch, reported_version, available
):
    monkeypatch.setattr(structured_pdf.importlib.util, "find_spec", lambda _: object())
    monkeypatch.setattr(structured_pdf, "version", lambda _: structured_pdf.ENGINE_VERSION)
    monkeypatch.setattr(structured_pdf.shutil, "which", lambda _: "/usr/bin/java")
    monkeypatch.setattr(
        structured_pdf.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "", reported_version),
    )
    assert structured_pdf.structured_pdf_available() is available


def test_structured_availability_requires_pinned_package(monkeypatch):
    monkeypatch.setattr(structured_pdf.importlib.util, "find_spec", lambda _: object())
    monkeypatch.setattr(structured_pdf, "version", lambda _: "2.5.10")
    assert not structured_pdf.structured_pdf_available()


@pytest.mark.skipif(os.environ.get("CAP_TEST_STRUCTURED_PDF") != "1", reason="Optional Java runtime")
def test_real_structured_engine_reads_synthetic_pdf(tmp_path):
    source = tmp_path / "synthetic.pdf"
    pdf = canvas.Canvas(str(source))
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(72, 750, "1 Audit controls")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(72, 720, "The system shall retain an audit trail.")
    pdf.showPage()
    pdf.save()
    output = tmp_path / "structure"
    output.mkdir()
    result = read_structured_pdf(str(source), str(output), timeout=30)
    assert result["number of pages"] == 1
    assert "The system shall retain an audit trail." in json.dumps(result)
    assert result["kids"]
