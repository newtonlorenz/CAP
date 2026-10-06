# Container dependencies

The standard image contains the application and PostgreSQL backup tools. Structured
extraction adds Java and OpenDataLoader. OCR adds Tesseract, Leptonica and selected
language data. Use the smallest variant that supports your documents.

## OCR build boundary

CAP renders PDF pages to local PNG files before invoking Tesseract. The OCR images
build Tesseract 5.5.3 with `DISABLE_CURL` and `DISABLE_ARCHIVE`. They retain normal
language models and searchable-PDF output. Compilers remain in a separate build stage.

The [upstream build options](https://github.com/tesseract-ocr/tesseract/blob/5.5.3/CMakeLists.txt)
disable URL and archive readers. The Dockerfile verifies the source archive checksum
and checks that Tesseract does not link curl, libarchive or libxml2. Its licence
remains in the runtime image. Language packages can still be selected with
`OCR_LANGUAGE_PACKAGES`; use language-data packages, not the distribution's full
`tesseract-ocr` package.

Check a built image with:

```sh
docker run --rm --network none --entrypoint tesseract IMAGE --version
docker run --rm --network none --entrypoint tesseract IMAGE --list-langs
docker run --rm --network none --entrypoint ldd IMAGE /usr/local/bin/tesseract
```

The pipeline's page, CPU, output and wall-clock limits also apply to OCR. Disabling
optional readers reduces dependencies; it does not establish that every remaining
decoder is free from vulnerabilities.

## Release checks

Run `backend/tests/test_pdf_ocr_smoke.py` in both OCR image variants. It generates
an image-only PDF, verifies extracted wording and checks structured numbering when
OpenDataLoader is selected. Keep source-document qualification separate from this
runtime smoke check.

Generate and review an SBOM and vulnerability scan for each distributed image and
architecture. Check findings against actual package versions and reachable code.
Retain `/usr/local/share/cap/ocr-build.json` with each OCR image's SBOM. It records
the compiled Tesseract version, source checksum and build options. Package scanners
may not identify this static binary, so review its upstream advisories separately.
Do not suppress findings solely because an application test passed. Recheck the
dependency boundary after changing the base image, OCR options or accepted inputs.

The Python backup reader rejects links and copies validated regular-file members;
it does not call `tarfile.extract()` or `extractall()` on uploaded backups. Continue
tracking supported Python security patches even when a reported extraction-filter
vulnerability does not apply to that path.
