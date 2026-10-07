# CAP workspace instructions

## Maintained repository

`newtonlorenz/CAP` is the maintained public source repository. Base new work,
pull requests, checks and releases on its current main branch.
`newtonlorenz/cap-dev` is a deprecated private archive for historical information.
Do not send new work or releases there.

If historical code must be recovered, review and transfer only the required files
to a public branch. Never merge, push or expose private Git history, operational
records, credentials, customer evidence or internal design artefacts.

## Implementation and checks

Follow CONTRIBUTING.md and the public content, interface and architecture guides.
Preserve unrelated work. Use synthetic fixtures and disposable services for tests.
Keep new source and notice files in publication-manifest.json. Update SNAPSHOT.json
when the reviewed public source changes. Retain dependency locks, licences and the
image vulnerability gates.

## Deployment

Inspect the actual running revision and configuration before a deployment.
Preserve deployed features when reconciling older branches. Build from the reviewed
public revision and record the exact image and source revision.
For a frontend-only change, replace only the frontend. Preserve the active backend,
worker, database, uploads, routing, other services and rollback image. For backend
or schema changes, verify backups and data preservation before a cutover.

Never print environment arrays, session tokens or credential-bearing deployment
records. Extract only the non-secret fields needed for the task. Verify authorised
routes without changing business records, and revoke temporary verification sessions.
