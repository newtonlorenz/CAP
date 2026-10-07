# Contributing

CAP's first-party code uses the [Sustainable Use License 1.0](LICENSE).
Read the [CAP Contributor Agreement](CONTRIBUTOR_AGREEMENT.md) before offering
code, documentation or assets. You retain ownership and grant Daniel Graetzer
non-exclusive copyright and patent rights, including sublicensing and separate
commercial licensing. Each contributor must explicitly accept version 1.0 in
each pull request using the statement in section 6; opening a pull request or
leaving a template in place is not acceptance. Maintainers record the agreement
revision, final contribution revision and accepting accounts before merge.
Disclose third-party material, required notices, material AI assistance and
employer/client rights. The agreement does not clear rights in historic code.

Use Python 3.12 and Node 24. Install from the hashed development lock and npm lock
as shown in the README. Runtime dependency changes need regenerated locks,
third-party notices, a vulnerability review and tests for the affected boundary.
Use synthetic documents and accounts. Never commit customer evidence, database
backups, provider responses containing documents, or credentials.

## Checks

Develop new work in the public `newtonlorenz/CAP` repository. The private
`newtonlorenz/cap-dev` repository is a deprecated historical archive.
Use public feature branches and pull requests. Do not transfer private Git history
or operational records. Follow the [public source procedure](docs/public/releasing.md)
when reviewing recovered file changes or preparing a release.

See the [contributor architecture map](docs/public/contributor-architecture.md) for
domain boundaries, transaction ownership and organization-scope rules.
Use the [content style guide](docs/public/content-style.md) for UI text and public docs.
Use the [interface guidelines](docs/public/interface-guidelines.md) for layout and interaction.

Keep changes focused on a domain or integration boundary. Explain the behavior
being changed and test its failure paths as well as the successful case. Put shared
business rules in domain services; keep HTTP handling and presentation separate.
Keep organization scope explicit in background jobs and shared queries. Changes
to approvals, evidence, extraction, authentication or migrations need regression
tests for the affected invariant.

All tracked files must be listed in `publication-manifest.json`; maintainers review
that allowlist before export. Keep internal notes and real source documents outside
Git. CI checks the tracked tree against the allowlist. A passing test suite does
not by itself approve a license change, release or deployment.

```sh
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python -m unittest discover -s scripts/tests -p 'test_*.py'
npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run build
```

For database concurrency and browser tests, create a **disposable** PostgreSQL
instance bound to `127.0.0.1:25489` with database `cap_e2e`. It must contain no real
application data. Set `E2E_DATABASE_URL` to its asyncpg URL, a random `SECRET_KEY`
and a disposable `E2E_ADMIN_PASSWORD`. No test seed password is defaulted.

```sh
# Apply migrations to the explicitly selected disposable database first.
cd backend
DATABASE_URL="$E2E_DATABASE_URL" ../.venv/bin/python -m alembic upgrade head
cd ..
CAP_TEST_POSTGRES_URL="$E2E_DATABASE_URL" .venv/bin/python -m pytest backend/tests/test_review_postgres_locking.py -q
cd frontend
npx playwright install chromium
cd ..
.venv/bin/python scripts/run-e2e.py
```

The runner validates the target, uses isolated uploads, starts its own backend on
18000 and a frontend on 15173, and stops its backend afterwards. Playwright stops
its own frontend. Existing servers are never reused. Stop/remove only the disposable
database you created once testing is complete. The CI service is disposable by design.
The default browser suite runs in batches of four spec files. Each batch invokes
the guarded synthetic seed, clearing only disposable login-throttle state while
production sign-in limits stay unchanged. Explicit Playwright selectors and options
run as supplied.

The browser runner uses the dedicated Redis address `127.0.0.1:25490/0`; provide
that disposable service when testing queue-dependent behavior. Browser assertions
currently exercise source editing and review workflows; queued extraction needs a
separate Celery worker and integration check. No in-memory broker is substituted.
Optional OCR tests run when Tesseract is installed; cloud contracts use mocked HTTP.

With the dedicated PostgreSQL and Redis services running, test actual queue delivery,
duplicate messages, retry recovery, worker loss and cancellation with:

```sh
CAP_TEST_JOB_SERVICES=1 CAP_TEST_POSTGRES_URL="$E2E_DATABASE_URL" \
  E2E_REDIS_URL=redis://127.0.0.1:25490/0 \
  .venv/bin/python -m pytest backend/tests/test_extraction_delivery.py -q
```

This check starts and stops its own Celery worker on a unique queue, with a synthetic
work body. It does not execute a PDF parser or call an AI provider. It deliberately
terminates one of its own worker children to verify redelivery. The database and
broker must be disposable; synthetic records are retained for inspection.

Report changes with evidence and limitations. Never equate successful extraction
with regulatory acceptance or successful tests with a deployed release.

For release candidates, use the [image build and lifecycle checks](docs/public/releases.md).
The lifecycle rehearsal owns its disposable Docker resources and checks stored
requirements, review decisions, comments and attachment bytes through upgrade and restore.

## Verification and deployment

Verify runs once per pull request and on main updates. Application checks and container/release checks run in parallel. The final `verify` status requires both jobs to pass; superseded runs are cancelled and dependency downloads are cached.

For scoped changes, run the affected tests and build locally, then use hosted Verify for the full gate. Avoid repeating the full local and hosted suites without a new change or unresolved failure. Prepare candidate images from the exact reviewed commit while Verify runs.

Inspect the current deployment record and Compose configuration before upgrading an existing installation. Frontend-only changes can replace only the frontend. Backend/schema changes require a verified backup before migration, a data-preservation check, and backend/frontend/worker health checks before recording the active release. Retain prior images for rollback, preserve unrelated services and volumes, and recheck the active release before cutover to detect concurrent deployments.

Public image publication retains the full SBOM and installation/upgrade/restore checks. These workflow improvements remove duplicate work without reducing verification coverage.

Public source availability does not establish a supported container release.
Before accepting external contributions, complete the publisher identity, rights
and repository configuration checks in the [publication checklist](docs/public/releasing.md).
