# Preparing the first public source snapshot

Do not push the private preparation repository or its history. The public repository
must start from a separately reviewed snapshot. The private repository remains intact.
The private development repository has been renamed to `newtonlorenz/cap-dev`.
The publication target is a fresh `newtonlorenz/CAP` repository containing only
the approved snapshot. Confirm the repository identities and visibility before
any push. Never make the private development repository or its history public.

`publication-manifest.json` is an explicit file allowlist. Every tracked source file
must belong to it. CI rejects tracked files outside the allowlist and entries that
are not tracked. An exported repository may also track the generated `SNAPSHOT.json`.
Keep internal reviews, deployment records and source documents outside Git.
Review additions before changing the allowlist.
`scripts/export-public.py` validates paths, rejects symlinks, checks common secret
patterns (reporting filenames only), and copies into a new directory. It never creates
Git history, commits, pushes or changes repository visibility.

```sh
python scripts/export-public.py --check-tracked --draft --output /path/to/new/private-review-folder
```

Draft exports are marked as unpublished and are for private inspection. A normal
export requires the adopted `LICENSE` in the allowlist. Even a successful export
is not publication approval: the allowlist and heuristic checks cannot prove the
absence of secrets.
Run a maintained secret scanner over the exported files and every archive, review
third-party notices, and inspect every included document/asset before publishing.

## Source publication checks

Before publishing the first source snapshot:

1. Daniel Graetzer is the first-party licensor, identified in [NOTICE](../../NOTICE).
   During preparation he confirmed that the included first-party code and assets
   are his to publish, including any relevant employer/client work. This is the
   owner's rights confirmation, not an independent chain-of-title investigation
   or legal review. Review any newly added material or unresolved restrictions;
   author names and generated code alone do not prove ownership.
   Review the [CAP Contributor Agreement](../../CONTRIBUTOR_AGREEMENT.md)
   and its explicit per-pull-request acceptance procedure. That agreement covers
   accepted contributions, not historic ownership gaps. Keep the adopted SUL-1.0
   licence text unchanged.
2. Approve the allowlist, synthetic fixture provenance, branding and all asset rights.
3. Generate dependency notices from the actual candidate environment with
   `scripts/dependency-notices.py`, review bundled licence texts and audit the
   locked Python/npm runtime dependencies. Document findings and resolutions.
4. Scan the complete exported tree, its synthetic fixtures and any proposed
   archives with a maintained secret scanner. Review each included document/asset
   and confirm that the export contains no private history or operational data.
5. Pass migrations, backend, frontend, browser and concurrency checks
   against the exact export. Test backup/restore only on disposable fixtures.
   Record the checks actually run and their limitations; older test results do
   not validate a changed file set.
6. Review the public docs against the evidence. Identify optional image/integration
   limitations and avoid claims of public container availability, supported
   architectures, production readiness or regulatory acceptance without evidence.
7. Prepare repository configuration: verify maintainer access, enable private
   vulnerability reporting and verify its route, configure the required Verify
   branch status and review policy, and require recorded contributor acceptance
   before any external work is merged. Record actual GitHub settings; a policy
   document does not configure them.
8. Produce the final `SNAPSHOT.json` with file hashes and retain the scan and check
   evidence against that file set. Obtain explicit approval for that exact snapshot
   and the fresh `newtonlorenz/CAP` target before creating/pushing the public history.

Changing source after these checks requires regenerating the export and repeating
affected checks. A separately initialised public Git repository contains its own
new initial commit; it must not share the private repository's objects, branches
or tags. After an authorised publication, verify the public file set against the
approved snapshot, the new history and visibility, and the configured security and
branch settings. Record the public commit separately from the private source revision.

## Container and optional integration qualification

Source publication does not publish images, approve deployment or clear these
additional checks. Before a container release, pin/review base-image digests,
generate OS/binary SBOMs and scan the exact runtime, structured PDF and OCR images.
Pass clean installation and upgrade/restore rehearsal, recording image digests and
target architectures. For a first release with no previously distributed image,
record that a same-candidate rehearsal does not test upgrade from a prior release.

Verify the optional structured PDF image on synthetic sources and a privately
supplied representative source before claiming suitability for that source.
Qualify optional OCR and the chosen AI model contracts independently. Real-provider
calls require suitable non-sensitive fixtures and account authorisation. Mocked
contracts and synthetic parser tests do not establish real-provider or regulatory
outcomes. Publishing an image or deploying an installation needs separate
authorisation for the target.

The `Verify` workflow checks container references and builds five image targets
from its draft export, checks the runtime user and basic executables, parses a
synthetic numbered PDF in the structured image, verifies a synthetic scanned PDF
in both OCR images (including mixed native/scanned pages and numbered requirements
with OpenDataLoader), rehearses installation and backup restoration with synthetic
data, and exports
SPDX SBOMs for `linux/amd64`. Download `public-image-sboms-linux-amd64` within
30 days of the run. Its `image-digests.json` identifies the OCI manifests built
for that evidence; it does not identify any later rebuilt or published image.
Record the workflow run, export revision, target architecture and the exact image
digests used for a release. Scan those exact images for vulnerabilities and
review the findings before publication. CI retains Grype scans of these exact image
SBOMs for review; the image publication command also scans its exact built image
archives and fails on high/critical findings. The workflow does not supply an image
signature, multi-architecture qualification or an upgrade test from a
previously distributed release. Use the [release tooling](releases.md) with
`--previous-backend-image` to rehearse that upgrade separately. The optional OCR
image is not release-cleared while its current
high/critical OS-library findings remain untriaged. Source checks 1–8 and the
additional container qualification checks require their own evidence; this workflow
does not by itself clear them.

Excluded material includes private history, database dumps, uploads, environment
files, private operational notes and regulatory source PDFs. Third-party regulatory
text is not made redistributable by CAP's own license. The optional Page Feedback
service is outside this snapshot; its vendored client retains its MIT notice.
