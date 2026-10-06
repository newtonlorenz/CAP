# Contributor architecture map

CAP is a modular monolith: React presents workflows, FastAPI exposes authenticated
operations, PostgreSQL stores authoritative state, and Celery runs background jobs.
Keep existing HTTP contracts stable when moving code between modules.

## Domain boundaries

| Area | Entry points | Shared policy |
| --- | --- | --- |
| Content access | `api/access.py`, `components/access/` | `services/access.py` separates explicit content authority from account roles. Apply SQL visibility before pagination, action checks before mutation/export, and inherited source restrictions. `services/access_audit.py` protects activity and export side channels. See [access controls](access-control.md). |
| Applications | `api/applications.py`, `components/applications/` | Application services own pack composition, readiness, versioned approvals, submission records and follow-up. Preparation cases remain independent source records. |
| Preparation | `api/preparation.py`, `api/preparation_evidence.py`, `components/preparation/` | `services/preparation.py` validates typed answers, case revisions, evidence validity and fresh acceptance on reuse. Templates are copied into each jurisdiction-specific case. |
| Review assessment | `backend/app/api/reviews.py` | `services/review_assessment.py` validates the resulting evidence/assessment state; `services/review_assurance.py` builds closure and export evidence. |
| Baseline migration | `api/program.py`, `components/review/ReviewBaselineMigration.tsx` | `services/review_migration.py` compares versions, validates decisions and copies evidence. Changed wording requires a fresh assessment even when evidence is retained. |
| Installation setup | `python -m app.setup` | `services/bootstrap.py` owns the setup transaction; `operator_authority.py` separates installation trust from tenant roles. HTTP account updates cannot grant that trust. |
| Requirement baselines | `api/program.py`, `api/reviews.py` | `services/requirement_baselines.py` selects approved versions and loads scoped requirements. Project and review defaults can differ intentionally. |
| Background jobs | Document extraction request and Celery worker | Durable job state, dispatch and ownership belong to the job lifecycle, independently of the parser implementation. |
| Integrations | Capability API and integration endpoints | Explicit configuration and bounded transports; domain approval rules stay outside transport code. |
| Review interface | `frontend/src/pages/ReviewCycleDetail.tsx` | Focused review components and hooks own editing, saves and workflow presentation. Server decisions remain authoritative. |

The installation PDF engine is recorded when an extraction run is queued.
Jurisdictions and document categories do not select parsing code. `services/structured_pdf.py` handles the local Java boundary;
`services/structured_requirements.py` maps source structure to candidates. Keep
source text and later reviewer edits separate, and require explicit review before
publishing a baseline. The native parser, optional OCR and external AI retain
separate configuration and failure paths.

## Transactions and organization scope

Authenticate and resolve the caller's organization at the API boundary. Shared
queries and background work must retain that scope explicitly; a matching document
fingerprint or jurisdiction does not grant access to another organization's data.

Keep a business transition and its audit record in the same database transaction.
Review mutations must take the same cycle lock as closure and re-read the state
after acquiring it. Evidence-only changes must preserve the review decision and
reviewer unless the request explicitly changes them. Removed evidence must never
be replaced implicitly by obsolete text from a second field.

Pure policy helpers validate a proposed state before mutating it. Route-level
operations own commit/rollback and HTTP error mapping. Do not add generic repository
wrappers that merely rename SQLAlchemy methods.

Treat database state and broker acknowledgement as separate facts. A committed job
must remain recoverable if queue publication fails or its acknowledgement is lost.
Repeated deliveries must not produce concurrent effective work. Cancellation,
terminal states and a newer current run must fence late writes from an older worker.

## Frontend changes

Keep queries and workflow coordination in hooks/page containers, and pass explicit
values and callbacks to focused components. Draft text, the last successful save
and the server's assessment are different states. Test failed saves, rapid edits
and navigation; do not rely on a successful slow manual edit to establish correctness.
`useReviewItemDrafts` owns write ordering and retries. `useReviewFocus` owns selected
item navigation and session-scoped resume. Store only the selected item ID in browser
storage; evidence drafts remain in memory. The Dashboard setup guide derives progress
from authorised requirement-set and review queries.

Use shared `Tooltip`, `CopyButton` and `DraftSaveStatus` controls for help, copying and save feedback. Essential instructions stay visible; tooltips supplement accessible labels and work with keyboard focus. Keep form spacing and controls consistent between Preparation and Applications.

Draft content saves after 800 ms idle and on blur. Serialize writes per resource, preserve edits made during a request, and only acknowledge the snapshot the server accepted. Errors and revision conflicts must preserve drafts and block workflow actions. Use the shared draft navigation guard, including browser Back. Acceptance, approval, submission, access changes and structural setup remain explicit. Audit meaningful server changes within their transaction; an unchanged response must not reset acceptance.

Do not move large blocks to a new file solely to reduce a line count. Extract a
behavior that can be understood and tested independently. Avoid silently changing
approval defaults while consolidating similar helpers.

## Review and ownership

Daniel Graetzer maintains the project under the Newton Lorenz name. Contributions
require explicit acceptance
of the [CAP Contributor Agreement](../../CONTRIBUTOR_AGREEMENT.md) in each pull
request, with authority and third-party provenance reviewed before merge. Domain
changes should receive review from someone familiar with the relevant invariants.
Actual GitHub maintainer access and required branch checks must be verified on the
fresh publication repository; this document does not assert they are configured.

Use the commands in `CONTRIBUTING.md`. Include a regression for the failure being
fixed and run the affected workflow checks. Test concurrency against the dedicated
disposable PostgreSQL target, rather than inferring database locking from SQLite.
Use a disposable Redis/worker pair for delivery and recovery checks. Keep fixtures
synthetic and all service addresses isolated from an existing installation.

Add new public files to `publication-manifest.json`. Source locks and notices must
follow dependency changes. Rebuild the public snapshot after code changes; an older
snapshot's hashes and test results do not validate a newer tree.
