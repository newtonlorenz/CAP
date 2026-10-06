# CAP

CAP is a self-hosted workspace for organising compliance requirements, evidence and
review decisions. It helps a team answer three practical questions: **what applies,
what evidence supports it, and what remains unresolved?**

CAP supports three jobs: preparing a licence application, organising a certification
engagement, and managing product changes. It retains approved versions and evidence
while working records evolve. CAP records internal decisions and external outcomes;
it does not issue licences or certify products.

## Choose your workflow

- **Licence Applications:** start a licence pack, review the market checklist, then
  complete its main application forms, repeated annexes and supporting documents.
  Accept answers, approve a frozen pack, record submission and respond to authority
  queries. Licence preparation can start without approved requirements.
- **Certifications:** organise a test or audit engagement, choose approved requirement
  versions before starting assessments, gather forms and evidence, record provider
  reports and prepare a controlled submission package. Setup can begin before the
  baseline is ready.
- **Change Management:** describe changes to the component register, assess regulatory
  impact, approve, implement and verify. Linked requirement assessments remain advisory.

Saved blank forms contain reusable questions. Completed forms contain private answers
and evidence. Existing forms and reusable resources remain available through contextual
links and the collapsed Resources menu. Reusing an answer requires an explicit action;
repeated blank declarations never copy personal answers or attachments.

Read the [licence pack guide](docs/public/applications.md),
[certification guide](docs/public/certification-projects.md) and
[existing forms guide](docs/public/preparation.md).

## How requirements-based reviews work

1. **Define the requirements.** An installation operator creates a jurisdiction;
   a team then creates a requirement set manually or imports a PDF. Check the
   wording, numbering and scope before submitting and approving a version. A PDF
   is optional.
2. **Plan the work.** For a certification programme, start a project and choose approved
   versions in its baseline before assessment, and track milestones and submission
   package items. A standalone requirement assessment can use approved sets without a project.
3. **Review against a fixed scope.** Start a requirement assessment, assign work, record
   applicability and assessment decisions, attach evidence, and resolve comments.
   The cycle keeps its selected baseline even if a source set later changes.
4. **Track change.** Use the component and change registers when a product change
   needs its own inventory, decision history and baseline comparison.
5. **Close and hand over.** Resolve the review's completion blockers, then export
   its assessment and evidence package. Reports help identify gaps; they do not
   replace a regulator's forms or an independent certification decision.

The in-app **Guide** explains each workspace. The
[requirement-set guide](docs/public/requirement-imports.md) covers manual creation,
PDF review, versioning and structured imports.

Comments can include stored JPG, PNG, PDF, DOCX, TXT and MD attachments.
Select up to 10 files before posting a comment. Each file uses the configured
evidence upload limit (25 MB by default). Download attachments from the comment.
Files remain available in closed reviews and carry forward with retained comments.

For daily review, **Focus on one requirement** keeps the current item visible
while you edit. Failed saves retain your draft and offer **Retry save**. Save
before moving to another item; your place is remembered for this browser session.
Outside text fields, use Alt+Left/Right to move and Alt+N for the next item needing
attention. Unsaved text is not restored after closing the page.

When a baseline changes, compare the old and new wording before migrating a
review. Choose whether to retain evidence or start again for each changed item.
Retaining evidence does not retain its assessment: changed requirements need a
fresh decision. Previous approved baselines and review history remain available.

## Try it locally

You need Docker Engine and Compose v2. The default installation needs no AI
account, SMTP account, local model server or separate feedback service.

1. Copy `.env.example` to `.env`.
2. Set `SECRET_KEY` to a fresh random value.
3. Start CAP with `docker compose up -d --build`.
4. Create your first operator and jurisdiction with the local setup command below.
5. Open <http://localhost:3000>, sign in, and follow the Dashboard's **Get started** guide.

```sh
docker compose exec backend python -m app.setup \
  --email operator@example.com --name "Local Operator" \
  --jurisdiction-code internal --jurisdiction-name "My assessment scope"
```

The command prompts for a password. Choose your own email, name and scope.
For optional training data in a development installation, add `--example`. The training set remains an
unapproved draft in a separate **EXAMPLE** jurisdiction.

For example, `python -c 'import secrets; print(secrets.token_urlsafe(48))'` generates
a secret. Keep `.env` private. The example database password is suitable only for
isolated local development; if you change it, update both `DB_PASSWORD` and
`DATABASE_URL`. Development ports bind to loopback. The backend waits for
PostgreSQL and applies migrations on startup. Use `docker compose down` to stop
CAP, without removing volumes if you want to keep its data.

**Set up a jurisdiction before the first review.** A fresh installation has no
preloaded countries, authorities, standards or requirement sets. Jurisdiction
creation is restricted to an installation operator. The setup command designates
that operator explicitly; ordinary administrators do not gain this authority.
If you already have an administrator, use `--existing-admin --email YOUR_EMAIL`
instead of `--name`. Setup preserves their password and existing records.
It requires no UUID lookup or backend restart. Only designate an administrator
you trust with installation-wide settings. The
[installation guide](docs/public/installation.md#initial-setup)
explains the scope of this role.

For a useful first pass, select that jurisdiction, create a small **manual**
requirement set in **Requirements**, then submit and approve it. Create a review
in **Reviews** from that set, record a decision and evidence for a few items, and
inspect the completion panel and **Reports**. This shows the core workflow without
needing a source PDF or an external integration. For a certification programme,
add a **Certification Project** and its baseline before creating a submission
review. Use representative data you are allowed to store in this installation.

## Choose the input path you need

| Path | When to use it | What to expect |
| --- | --- | --- |
| Manual requirement set | You have a small scope, an existing approved list, or no PDF | Create and edit the draft directly; submit and approve it to establish a versioned baseline. |
| Built-in local PDF extraction | You have a text PDF with numbered, English-language obligations | CAP proposes editable requirements locally. Formats and languages vary; compare every result with the source before approval. |
| Structured PDF import | You need numbered headings and parent relationships from a source PDF | Add `docker-compose.structured.yml` to the base Compose file for both API and worker. The local OpenDataLoader path is optional and requires source review. |
| OCR for scanned pages | The PDF has pages without usable text | Add the OCR image or the combined structured/OCR image. Scanned and mixed-page runtime tests cover both paths; check your documents and language packs before relying on their output. |
| External AI extraction | A supported generic import needs text or image interpretation beyond the local paths | Explicitly configure OpenAI or Anthropic and consent for that run. Document text and, when needed, page images go to that provider. |

For structured imports, use
`docker compose -f docker-compose.yml -f docker-compose.structured.yml up -d --build`.
The [import guide](docs/public/requirement-imports.md) explains the parser's scope
and review flags. Ambiguous structured imports remain editable drafts: compare the
source page, correct references, attach continuations, or exclude irrelevant rows.
Unresolved source issues block approval. The [installation guide](docs/public/installation.md#optional-ocr)
covers OCR and the combined image. The base installation does not require Java,
Tesseract, OpenDataLoader or an AI provider. AI keys alone do not enable AI.

The selected extraction engine applies across document categories; categories are
labels, not parser selectors. Neither a category nor a jurisdiction guarantees
coverage. No extraction path guarantees complete or correct regulatory wording.
Check each candidate against the source, resolve hierarchy and review flags, and
approve the baseline deliberately. Create or correct requirements manually where
extraction falls short. Regulatory source PDFs are not distributed with CAP; use
documents you have permission to process.

## Deployment and integrations

CAP's React frontend calls a FastAPI backend. PostgreSQL stores the authoritative
records; Redis and Celery handle background extraction. Uploaded files and backups
remain in operator-selected storage. The default no-AI workflow is local to the
installation. Optional AI, email, Jira and Page Feedback connections send relevant
data to the services you configure. CAP has no licence activation server or model
download step.

For a self-hosted deployment, follow the
[production installation and upgrade guide](docs/public/installation.md): it
covers environment settings, HTTPS, backups, migrations and the separate image
variants. Do not use the development `.env` or Compose file as a production
configuration. [Architecture and integration boundaries](docs/public/architecture.md)
describes the trust and process boundaries in more detail.
The [container release guide](docs/public/releases.md) covers building all image
variants and rehearsing installation, upgrades and backup restoration with
disposable data.

Email reminders and Jira are optional. Page Feedback is experimental: its MIT
widget is bundled, but the separate service is not distributed with CAP and has
no supported public installation path yet. Leave it disabled unless you maintain
a compatible service yourself.

## Development and contribution

CAP uses Python 3.12, Node 24 and `uv`. To set up a development environment:

```sh
uv venv --python 3.12
uv pip sync --require-hashes backend/requirements-dev.lock
uv pip install --no-deps -e backend
npm ci --ignore-scripts --prefix frontend
.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run build
```

The default backend suite uses disposable SQLite fixtures. PostgreSQL
concurrency and browser tests require the explicitly isolated database and Redis
service described in [Contributing](CONTRIBUTING.md); never point them at an
existing installation. Contributors can start with the
[architecture map](docs/public/contributor-architecture.md),
[content style guide](docs/public/content-style.md) and [security policy](SECURITY.md).
Contributions require explicit acceptance of the
[CAP Contributor Agreement](CONTRIBUTOR_AGREEMENT.md) in each pull request.
You keep ownership while granting Daniel Graetzer rights to sublicense your work,
including under separate commercial terms. Maintainers review provenance and
record acceptance before merge.

## Licence and release status

CAP's first-party code and documentation use the
[Sustainable Use License 1.0](LICENSE). Personal, non-commercial and your own
internal business use are permitted; selling CAP as software or providing it as
a commercial software service needs separate permission. See the
[plain-language licensing guide](docs/public/licensing-brief.md). Third-party
components keep their own terms and [notices](THIRD_PARTY_NOTICES.md). Because the
licence restricts commercial distribution, CAP is **source available**, not OSI
open source.

Daniel Graetzer is the first-party licensor and project maintainer; `newtonlorenz`
is the GitHub account. See [NOTICE](NOTICE)
for attribution and the distinction from third-party components.

The first public source candidate uses a reviewed, history-free snapshot of the
private development tree. Publication requires approval of the exact snapshot
and repository. Source publication alone does not establish a supported container
release or validate a production deployment. The
[publication checklist](docs/public/releasing.md) records rights, security,
repository configuration and verification requirements; the
[container release guide](docs/public/releases.md) records image qualifications
and remaining limitations.
