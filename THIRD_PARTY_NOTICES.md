# Third-party components

CAP's Sustainable Use License 1.0 applies only to the rights its licensor can grant.
Dependencies and their bundled components retain their own licences and notices.

The generated [runtime inventory](docs/public/third-party/inventory.json) records
locked Python/npm versions, licence metadata, npm integrity values and copied notice
texts from the installed macOS preparation environment. It checks installed package
names and versions against both locks; npm integrity values are recorded from the
lock, not independently verified against installed bytes. Reproduce with
`.venv/bin/python scripts/dependency-notices.py` after installing the runtime lock
and frontend lock. The current 108 records have no unresolved local `review_items`:
et-xmlfile and openpyxl supply `LICENCE` files in their installed wheel metadata;
the exact locked agent-base 6.0.2 and https-proxy-agent 5.0.1 packages include their
full MIT texts in their nested installed READMEs. Review `review_items` again after
each regeneration. This is an installed-platform inventory, not a complete SBOM or
legal compatibility opinion.

et-xmlfile's `LICENCE.python` also carries Python Software Foundation terms for
included standard-library code; its MIT metadata alone does not describe that
bundled code. The inventory lists the exact copied notice paths.

The PDF stack uses pdfplumber, pdfminer.six and pypdfium2/PDFium. The inventory includes
PDFium's bundled component notices, not just the Python wrapper licence. PyMuPDF,
Ghostscript, OCRmyPDF, pikepdf, img2pdf and fpdf2 are not application runtime dependencies
in this refactor. Optional Tesseract and all container OS packages require the notices
from the actual release images. Do not infer Linux binary coverage from macOS wheels.

OCR images build Tesseract 5.5.3 from its checksum-pinned upstream source archive.
The build disables optional curl and archive readers. The Apache-2.0 licence is
retained at `/usr/local/share/licenses/tesseract/LICENSE` in each OCR image.
Leptonica and language data retain their distribution notices under `/usr/share/doc`.
The build options do not change those licences. See the
[container dependency notes](docs/public/container-dependencies.md) for verification.

`certifi` retains its MPL-2.0 licence. DOMPurify offers MPL-2.0 or Apache-2.0 terms;
retain the distributed notices. The vendored Page Feedback React archive includes
its MIT licence. Its [public widget source](https://github.com/newtonlorenz/page-feedback-widget/tree/6dd8c8f9303af094df2272fa55289fe79b363214)
matches the archive source and licence; its compiled files matched a fresh build.
Its independent service is not part of CAP. Redis 7.2 is selected
rather than a floating Redis 7 tag; include the server's original notices with images.

Before distributing binaries/images, generate an SBOM and licence bundle from each
actual target platform and image, including Linux wheels, OS packages, Redis and any
optional binaries actually shipped. Resolve new notice review items and check licence
obligations against the adopted CAP terms. Updating a dependency requires refreshing
this record.

The optional structured PDF image includes `opendataloader-pdf==2.5.11` (Apache-2.0),
its bundled Java application and component notices, plus the distribution's Java
runtime. The wheel's `opendataloader_pdf/LICENSE`, `NOTICE` and `THIRD_PARTY` directory
remain installed in the image. Copies of those notices are included in
`docs/public/third-party/opendataloader-pdf/`. No hybrid/AI extras are installed.
Review the actual target image's Java/OS SBOM in addition to these upstream notices.
