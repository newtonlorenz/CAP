"""Generate the synthetic PDF used by extraction tests."""

from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def create_sample_pdf():
    output = Path(__file__).with_name("sample_requirements.pdf")
    c = canvas.Canvas(str(output), pagesize=A4, invariant=True)
    c.setTitle("CAP synthetic requirements fixture")
    c.setAuthor("CAP test suite")

    # Page 1
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 800, "CAP Synthetic Requirements")

    c.setFont("Helvetica", 12)
    y = 750

    requirements = [
        "4.2 Information Security Requirements",
        "",
        "4.2.1 The operator shall implement access controls for all systems.",
        "",
        "4.2.2 The operator shall ensure that all passwords meet complexity requirements.",
        "",
        "4.2.3 Multi-factor authentication should be implemented for administrative access.",
        "",
        "4.3 Penetration Testing Requirements",
        "",
        "4.3.1 The operator shall conduct annual penetration tests.",
        "",
        "4.3.2 Critical vulnerabilities must be remediated within 30 days.",
    ]

    for text in requirements:
        c.drawString(50, y, text)
        y -= 20

    c.showPage()
    c.save()


if __name__ == "__main__":
    create_sample_pdf()
    print("Created sample_requirements.pdf")
