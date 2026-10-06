# Architecture and integration boundaries

React calls the FastAPI API. PostgreSQL owns application state; Redis brokers Celery
extraction jobs. Uploaded files and backups live in operator-selected directories.
Tenant checks, audit trails, authentication and human approval remain application
responsibilities.
Jurisdiction definitions are shared across the installation, so only configured
system admins (installation operators) can create or change them. Company admins
manage their own users, workflows and Jira integration. They cannot access
full-installation backups or change system-admin accounts. The Settings and User
Management screens distinguish these two access levels.

PDF processing runs in a bounded child process. `document_reader.py` supplies a
local reader interface, implemented with PDFium and pdfplumber. Jurisdiction adapters
interpret document structure. `rule_parser.py` holds deterministic text rules;
`ai_parser.py` orchestrates optional AI and local results. Neither the local reader
nor the deterministic parser needs an AI service.

The optional structured image adds a pinned OpenDataLoader wheel and Java runtime
for source PDFs from any jurisdiction or document category. `structured_pdf.py` owns that local process boundary;
`structured_requirements.py` maps tagged headings and table rows into reviewable
candidates with source locations. Both API and worker must select the same engine.
The selected pipeline is stored on the extraction run, so a queued job cannot
silently fall back to another parser. The optional image does not include a
hybrid service or local language model.

`ai_provider.py` implements the selected external transport behind an explicit
`ProviderConfig`. There is no cached global SDK client. Runs retain their selected
provider/model; local runs cannot start using AI merely because credentials change.
A provider change invalidates a pending cloud run instead of silently switching
vendors. Credentials are resolved at execution and are not persisted in run records.
Both OpenAI and Anthropic use this boundary for text and page images. Responses are
size/time bounded and validated before entering the requirement pipeline. Redirects
and ambient SDK/proxy endpoint overrides are not followed. Alternative compatible
endpoints/local model servers are not currently supported; add a reviewed adapter
and contract tests rather than changing a hidden machine URL.

AI is disabled by default. The extraction endpoint requires explicit per-request
consent before starting an external run. Deterministic Annex runs stay local even
when AI is configured. The user must still review extraction output.

OCR is a separate optional image target. Tesseract reads rendered scanned pages;
PDFium merges them with preserved native pages. Ghostscript and OCRmyPDF are not
required. Missing language packs or OCR failures produce an actionable warning.
The OCR binary excludes optional URL and archive readers. Its pinned source,
licence and build options remain available inside the image; see
[container dependencies](container-dependencies.md).

`GET /api/v1/capabilities` is authenticated and returns non-secret feature status.
The UI uses it to disclose external extraction and disable unavailable reminders.
`python -m app.deploy capabilities` exposes the same operator diagnostics.

Backups require `pg_dump`/`psql` in `POSTGRES_BIN_DIR` or PATH. The application never
searches Homebrew directories or discovers Docker containers. The backend image
includes native PostgreSQL client tools. A backup includes the database and upload
files; it is not a cross-version migration mechanism. Use
`python -m app.deploy restore-empty-installation` on a new, empty database and
uploads volume. Then apply migrations. Compare records and file bytes before
you send users to the new installation. Test the procedure for each release.

Email, Jira and Page Feedback are optional integrations. The bundled feedback UI
package has an MIT license; its separate service is not included and the integration
is unsupported in the first public release. No private service is required for
core workflows. Disabling an integration is not an authorization bypass; server-side
access checks remain active.

## Deployment-owned requirements

The distribution does not seed jurisdictions, authorities or regulatory text.
Operators define the jurisdictions and report headers for their installation.
Teams enter document categories as labels of up to 50 characters. Categories and
jurisdiction codes do not select a parser or imply certification support.

The review, evidence, baseline and submission workflows operate on supplied
requirements. A source PDF is optional. The same core can hold certification,
licence application and internal assessment records. It does not encode every
country's legal process or replace decisions from an authority or certification body.

Upgrades retain existing records. The generic metadata migration adds a cloud
certification name from the existing assertion and preserves the old field.
Historical pack metadata remains readable but does not select extraction code.
Pre-publication migrations no longer install country data on a fresh database.
Only databases from before jurisdiction scoping receive an `Imported records`
scope when they contain records that need a jurisdiction reference.

## Preparation before a baseline

`api/preparation.py` coordinates template and case transactions;
`services/preparation.py` owns typed answer validation, readiness and explicit reuse.
A case copies a template definition and stays in one jurisdiction. An optional
certification-project link must match both organisation and jurisdiction. Templates,
responses and the independent evidence library retain organisation scope throughout.

Preparation evidence has immutable metadata and bytes, with explicit archival.
Files live beneath the configured uploads directory and participate in normal
backups. Downloads and exports resolve that boundary and verify SHA-256 hashes.
`preparation_export.py` creates bounded portable packs without transmitting data to
an authority. Source paths are never returned by the API.

Case revisions reject stale writes. Editing or reusing an answer clears acceptance;
readiness recalculates evidence validity rather than storing a permanent green
status. Template edits do not rewrite existing cases or requirement baselines.
