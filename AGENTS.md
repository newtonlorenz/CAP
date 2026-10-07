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

## Test value and execution

Use the `test-audit` skill when writing, changing, reviewing or auditing tests.
Apply its authoring gate, evidence requirements and retention bar using CAP's
actual test commands and CI policy. Its OpenClaw-specific runners, host workflows
and landing tools are not CAP tooling; do not introduce them into this project.

Before adding or changing a test, identify the observable behaviour or independent
contract, a credible regression, the gap in existing coverage, and whether the
test demands a production seam that no real caller needs. Prefer one primary test
at the strongest owning boundary; add another layer only for a distinct risk.
Extend existing cases and consolidate setup instead of duplicating scenarios.
Bug regression tests must demonstrably fail before the fix for the intended
reason and pass afterwards.

Avoid tests that mirror implementation, grep source without an independent
contract, assert values produced by the code under test, or use mocks that supply
the behaviour being asserted. Do not add tests for reversible, low-impact changes
when existing coverage and a focused check adequately establish the outcome.
Prioritise user workflows, permissions and tenant isolation, data integrity,
migrations, imports/exports, background jobs and recovery where affected.

Run the smallest relevant owner and sibling checks first. Complete mandatory
project/CI gates, but broaden or repeat local runs only when changes, failures or
unresolved concerns justify them. Avoid repeating an already passing full suite
on unchanged code without a specific reason. Run all container-based proof on
the remote Docker host specified below.

For test removal, inspect the full test, production owner, callers, overlapping
coverage, CI routing and relevant history first. Report candidate evidence before
editing: what failure it detects, why it exists, stronger remaining proof, any
test-only seam removed, risk and focused validation. Keep independent security,
storage, migration, API, release and architecture contracts. Slowness or a failing
baseline alone is not a reason to delete a test; investigate possible product bugs.
Keep audits scoped to coherent batches and optimise for confidence and maintenance
cost, not deletion counts. Do not edit source or tests while a test run is active
in the same checkout. Report checks actually run and any unverified boundary.

## Docker host

Use Docker only on `192.168.4.34` for this project's image builds, container tests,
disposable lifecycle rehearsals and deployments. Do not build images or run
containers on this laptop, to avoid resource contention. Use an explicit remote
Docker context (`m1-services`) or SSH to the host; never change the global context.
Verify that the chosen context targets `192.168.4.34` before using it. Override
scripts' local Docker defaults explicitly. If the remote host is unavailable,
report the blocked container checks rather than falling back to laptop Docker.
Non-container source checks may run locally. Preserve unrelated host services and
remove only disposable resources created for the task.

## Deployment

Inspect the actual running revision and configuration before a deployment.
Preserve deployed features when reconciling older branches. Build from the reviewed
public revision and record the exact image and source revision per changed service.
Classify the complete difference from the running services by its effects, not
the number of changed lines. Use the lightest applicable deployment path:

- **Frontend only:** build and replace only the frontend without restarting its
  dependencies. Preserve the backend, worker, database, uploads, routing and other
  services. Retain the previous frontend image and configuration, check health and
  the affected user journey, and roll back the frontend if verification fails.
  No fresh database/upload backup or restore rehearsal is required for this path.
- **Backend without schema or stored-data changes:** build and replace only the
  affected backend/worker services. Verify backups and data preservation before
  cutover; retain the current backend backup requirement until reliable tooling
  verifies this classification and backup availability. Check startup migrations,
  API compatibility, background jobs and rollback compatibility. Run health and
  affected-workflow checks. Do not assume that an unchanged migration directory
  alone proves a change cannot affect stored data.
- **Schema, stored-data, upload or infrastructure changes:** take a fresh verified
  backup, use appropriate migration and recovery checks, and verify data continuity
  after a controlled cutover. Rehearse restore on isolated disposable storage when
  the change affects recovery. Preserve existing volumes and unrelated services.
  Application-image rollback alone is insufficient when data is incompatible.

Build only affected images for installation updates. Avoid full-stack rebuilds,
duplicate source/image archives, full data hashing and repeated restore rehearsals
for routine frontend changes. Keep the previous working images and a small private
deployment receipt with source revisions, image IDs/digests, changed services,
checks and rollback references. Ordinary installation updates do not require a
new manually chosen semantic version; exact source and image identity is required.
Formal public image releases retain their existing publication, licence and
vulnerability gates.

Prefer one deployment entry point that detects scope, explains the chosen path,
records the receipt and supports application rollback where data compatibility
allows it. The current broad deploy script does not implement these paths: do not
treat a full-stack invocation as a frontend-only deployment.

Maintain scheduled database/upload backups with bounded retention and periodic
isolated restore checks independently of deployment. Verify that scheduling and
successful backups actually exist before relying on them; do not infer coverage
from this instruction. Never delete volumes or restore over live data as part of
a routine update. Deployments, host automation changes and destructive recovery
still require authorisation covering the action and target.

Never print environment arrays, session tokens or credential-bearing deployment
records. Extract only the non-secret fields needed for the task. Verify authorised
routes without changing business records, and revoke temporary verification sessions.
