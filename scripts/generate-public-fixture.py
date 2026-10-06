#!/usr/bin/env python3
"""Generate the original synthetic browser fixture; no regulatory text is copied."""

from pathlib import Path
from reportlab.pdfgen import canvas

path = Path(__file__).resolve().parents[1] / "frontend/e2e/fixtures/test.pdf"
pdf = canvas.Canvas(str(path), pagesize=(595, 842), invariant=True)
pdf.setTitle("CAP synthetic test fixture")
pdf.setAuthor("CAP test suite")
pdf.drawString(40, 790, "Synthetic requirements for software tests")
pdf.drawString(40, 740, "3.1 The example system shall retain test logs.")
pdf.drawString(40, 710, "3.2 The example operator should review those logs.")
pdf.save()
