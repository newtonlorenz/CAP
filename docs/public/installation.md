# Installation and upgrades

Use the README for local development. For self-hosting, start with
`.env.production.example` and `docker-compose.prod.yml`. Configure a real database
password, strong secret key, HTTPS frontend URL, CORS origins and allowed hosts.
The production validator rejects unsafe settings. AI and SMTP may remain disabled.

Build/start explicitly with:

```sh
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

Production binds the frontend to `127.0.0.1:3000`. Provide a TLS reverse proxy that
preserves Host and the original scheme. The optional `docker-compose.edge.yml`
adds Caddy when `APP_DOMAIN` is set. Do not expose PostgreSQL, Redis or the backend
to the public internet. Review `scripts/deploy/preflight.sh` before a production
rollout. The application startup applies migrations; take a verified backup first.

## Administrator access

**Company admins** manage users, workflows and Jira settings within their own
company. **System admins** also manage shared jurisdictions and full-installation
backups, email delivery and AI configuration. System admin is the user-facing name for the existing installation
operator designation; it does not grant access to another company's Jira credentials.
Email and AI can be configured under Settings by a system admin, as described below.

To grant system-admin access to an existing company admin, use the trusted local
`--existing-admin` setup command below. This records the grant in the audit trail
and invalidates existing sessions; the user must sign in again. Company admins
cannot grant themselves system-admin access through User Management.

## Initial setup

Fresh installations contain no users, jurisdictions, or requirement sets.
Start the backend first so it applies its database migrations. Then run this
command in a terminal on the trusted installation host:

```sh
docker compose --env-file .env.production -f docker-compose.prod.yml exec backend \
  python -m app.setup --email operator@example.com --name "Local Operator" \
  --jurisdiction-code dk --jurisdiction-name "Denmark"
```

The command prompts for a password and confirms it. It creates an admin account,
designates that account as an installation operator, and creates the jurisdiction.
It does not print the password. The operator can sign in without editing a UUID
in the environment or restarting the backend. Use `python -m app.setup --help`
inside the backend container to see all options. Native installs can run the same
module from the `backend` directory after applying migrations.

If an admin account already exists, select it explicitly. This includes accounts
created with `BOOTSTRAP_ADMIN_*` or an earlier setup run:

```sh
docker compose --env-file .env.production -f docker-compose.prod.yml exec backend \
  python -m app.setup --existing-admin --email operator@example.com \
  --jurisdiction-code dk --jurisdiction-name "Denmark"
```

This form does not change the admin's password. A second run with the same details
does not duplicate the account or jurisdiction. Conflicting details stop setup
without changing them. A tenant admin does not become an installation operator
through the browser. The local command is the only way to set its stored operator
designation; the existing `INSTALLATION_OPERATOR_IDS` configuration remains valid.
Keep local console and database access restricted to trusted installation staff.

After sign-in, open the Dashboard guide. Create a manual requirement set or import
a PDF in **Requirements**. Add and check the requirements. Submit and approve the
set to establish a baseline. Create a review in **Reviews**. Approval is a human
decision; setup does not approve a baseline or review. A jurisdiction can
represent a country, an authority, or an internal assessment scope. Use your own
names, report headers, and source documents.

For a development or test installation only, add `--example` to the setup command.
It creates a separate `EXAMPLE` jurisdiction and one synthetic draft requirement
set. It does not add training text to the selected jurisdiction or approve it.
Production rejects `--example`. New versions retain existing jurisdictions,
categories, requirements, and reviews.

## Site text

The frontend reads `site-content.json` when the page loads. The default text
describes the system and sign-in. It contains no organization name.

1. Copy `frontend/public/site-content.json` to `site-content.json` in the project root.
2. Edit the JSON text fields. The `information` list can contain zero to four items.
3. Add `docker-compose.site-content.yml` after the base Compose file.
4. Refresh the browser to read the new text. Rebuild the image only when code changes.

For example:

```sh
cp frontend/public/site-content.json site-content.json
docker compose --env-file .env.production -f docker-compose.prod.yml \
  -f docker-compose.site-content.yml up -d --build
```

Set `SITE_CONTENT_FILE` if the file is outside the project root. Set
`FRONTEND_BASE_PATH` to the deployed URL prefix, such as `/cap/`, when the
frontend image uses that prefix. The overlay mounts the file at that path.
The file is public. Do not put credentials or private data in it. CAP shows
each field as text. The file cannot add HTML or scripts. If the file is absent
or invalid, the frontend uses default text. Refresh the browser after you edit
the file. If you replace the file atomically, restart the frontend container.
The bind mount must point to the new file.

## Optional OCR

The OCR image is experimental for this first public-release candidate. Its current
OS-library scan findings require review before it is distributed as a supported
image. The structured OpenDataLoader image does not include OCR. To test both
local capabilities together, use `docker-compose.structured-ocr.yml` instead
of stacking the separate overlays.

```sh
docker compose -f docker-compose.yml -f docker-compose.ocr.yml up -d --build
```

Do not use the OCR image for a production installation until its OS-library
findings have been reviewed and the exact release image has been qualified.
Once qualified, use the same OCR overlay with the production Compose file.
The OCR image includes English by default. Set `OCR_LANGUAGE_PACKAGES` to the
space-separated Tesseract packages needed by your deployment, then rebuild both
API and worker images. Set `OCR_LANGUAGES` to the matching Tesseract language codes
joined by `+`. The default is `eng`. A native install needs Tesseract and those
language packs on the host. Changing `OCR_LANGUAGES` does not install a language pack.
Only the OCR image adds that executable. AI is independently optional.

## Component registers

Cloud certification names are entered as data. No certification gives a hardware
location exemption by default. If your reviewed policy permits an exemption, set
`CLOUD_LOCATION_EXEMPTION_STANDARD` to the exact certification name. The component
must also record independent checks and redundancy. These fields record operator
assertions; CAP does not verify the certification.

## Optional AI and email

System admins can configure **Settings → Email** and **Settings → AI**. Company
admins cannot read, change or test these installation-wide settings. Until the
first save for a section, CAP uses its server environment configuration. Saving
creates a database override for that section; subsequent environment changes do
not override it. Saved settings apply to new requests and jobs without restarting
the API or workers.

For Email, choose SMTP and enter the host, port, sender, connection security and
optional authentication. STARTTLS and implicit SSL/TLS are supported. Save, then
select **Send test email to me**. The recipient is the signed-in system admin's
email address. Success confirms SMTP acceptance, not inbox delivery. This
configuration is used by review reminders and comment mentions. Product-feedback
notifications are managed by the separate feedback service.

Comment mentions notify active users in the same organisation, excluding the
author. Emails include the comment and a link to its review item; set
`FRONTEND_BASE_URL` to the public CAP address, including `/cap` if used. Repeated
tags send one email per person, and edits notify only newly mentioned people.

For AI, choose OpenAI or Anthropic and enter a model available to your account and
its API key. Save, then select **Test AI connection**. The test sends only a small
synthetic request; it does not send documents, and the provider may charge for
API usage. Disabling AI preserves its saved credential until explicitly removed.
Switching providers requires a matching replacement key. New extraction jobs use
the saved model; queued jobs retain their chosen model and reject a provider
change. Local extraction remains available without AI. External extraction still
requires consent for each request (`allow_external_ai=true` for API clients).

Credentials are never returned to the browser. Leave their inputs blank to retain
them, or explicitly select removal. Changing an authenticated SMTP destination,
port, security or username requires replacement credentials or explicit removal.
Unsaved changes must be saved before testing. If another system admin changes the
settings, reload the saved version, review your retained draft and save again.

Environment defaults remain available for installation automation: `AI_PROVIDER`
(`none`, `openai`, `anthropic`; `auto` is a compatibility option), provider API key
and model; `EMAIL_MODE` (`disabled` or `smtp`), `SMTP_HOST`, `SMTP_PORT`,
`SMTP_FROM`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_USE_TLS` and `SMTP_USE_SSL`.
Implicit SSL takes precedence if both TLS options are enabled. Email `log` mode is
only for development and can log message content. Do not put credentials in Git.

Saved credentials are encrypted using the installation's `SECRET_KEY`. Database
backups include these encrypted settings. Retain the key securely outside the
backup and use the same key when restoring, or replace saved credentials after
changing it.

Jev is configured separately under **Settings → Jev**, using a TypeSafe API key.
It is disabled by default and works independently of the extraction provider.
Save its enabled state, model and key, then use the connection test, which sends
only synthetic text. Saved keys use the same encryption and administrator access
controls as other installation credentials. Enabling Jev makes optional source
checks available; each document import, recheck or spreadsheet enhancement still
requires consent before source text is sent externally.

For environment configuration, use `JEV_ENABLED`, `JEV_MODEL` (default
`jev-1.13.0`), `TYPESAFE_API_KEY` and `JEV_REQUEST_TIMEOUT_SECONDS` (at most 30).
Existing reviewed requirements are protected by the migration and can be checked
without being rewritten. Confidence thresholds are conservative starting values;
validate them against reviewed English and Danish examples before relying on
automatic repairs for a new document family.

## Moving data to a newer release

A `.capbak` archive contains a database dump and upload files. The admin restore
endpoint is for recovery on a compatible running version; it does not migrate an
older schema. For a version change, stop the old API and worker after taking and
verifying a backup. Restore into **new, empty, isolated** database and upload
storage before starting the new API or worker. Apply that release's Alembic
migrations, then start the matching services. Do not restore an older dump over a
database that the newer release has already initialised: `pg_dump --clean` removes
objects from the old dump but cannot remove newer tables absent from that dump.

The backend image provides `python -m app.deploy restore-empty-installation
/restore/source.capbak` for this offline step. Mount the archive read-only into
a one-off backend container after starting only its new PostgreSQL service. The
command checks that the database and uploads volume are empty, verifies archive
checksums and the database engine, then restores the snapshot. On failure, retry
only with fresh isolated storage. Run migrations before starting the API and worker.
The archive remains outside the uploads volume; retain a separate verified copy.

Rehearse the procedure with disposable storage first. Compare the actual review
items, assessment text, comments and attachment bytes as well as row and file
counts; test access through the new UI before routing users to it. Keep the old
installation and verified backup available for rollback until the cutover is
accepted. Never run old and new workers against the same database during this move.

## Upgrading an existing private installation

The new defaults disable AI, OCR and email unless explicitly enabled. Review your
configuration before upgrading; pending cloud jobs must still match the configured
provider. Cloud API clients now need explicit extraction consent.

The backend and Celery images run as UID/GID 10001. Existing upload/backup volumes
may be owned by root. Stop workers, back up data, inspect ownership and grant the
application user access before switching images. Do not recursively change ownership
of host directories without identifying the precise application volume. Fresh named
volumes inherit image directory ownership.

Migration `a20260924` adds background-job attempt, ownership, progress and dispatch
metadata. Apply it before starting the updated workers; stop old workers during
the upgrade and take a verified backup first. Existing source files are not rewritten.
PostgreSQL backup client tools must match the server's
supported version; set `POSTGRES_BIN_DIR` for native installs. Automatic host/container
discovery was removed deliberately.

The API process reconciles durable pending jobs every 60 seconds. Failed broker
publishes become eligible after 15 seconds; failed worker attempts after 60 seconds,
subject to the next reconciliation pass. A run gets at most four attempts. Worker
ownership prevents duplicate deliveries from processing a run concurrently. Lost
workers can also be recovered through stale-job reconciliation after the configured
`EXTRACTION_STUCK_TIMEOUT_SECONDS` (default 300 seconds). PostgreSQL is required for
cross-process worker ownership; SQLite locking is used only in isolated tests.

Redis is restricted to the 7.2 release line for this preparation build. The
Dockerfile bases and Compose service images use manifest digests; the public CI
checks these references in the exported snapshot. Review digest updates, OS
packages and support status for each release. `apt-get` and `apk` resolve
packages at build time, so the pins alone do not guarantee identical image bytes.

The public CI builds the exported backend, structured, OCR, combined structured/OCR,
and frontend images on
`linux/amd64` and saves SPDX package inventories as a 30-day workflow artifact.
Those inventories cover the built images; source lockfiles alone do not cover
container OS packages or binaries. A self-hosted image built later, on another
architecture or after package repositories change, needs its own SBOM and scan.
