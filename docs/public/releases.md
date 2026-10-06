# Building and releasing container images

CAP release images are built from the history-free, allowlisted source produced
by `scripts/export-public.py`. The private repository history is never sent to
Docker. The images are `backend-runtime`, `backend-ocr`,
`backend-structured`, `backend-structured-ocr`, and `frontend`. Backend variants
use the corresponding Dockerfile targets; the frontend uses its production
Dockerfile.

## Local build

Use a semantic version such as `v1.2.3`. A local draft build is the default and
can exercise the image build without clearing publication gates:

```sh
.venv/bin/python scripts/release-images.py --version v1.2.3
```

The script builds and loads each image locally. It writes
`tmp/release-output/release-metadata.json` with the version, source state,
image IDs and local tags, plus per-image Buildx metadata. It also copies the
exporter's `SNAPSHOT.json` to `source-snapshot.json` and records that file's
SHA-256, so a draft built from a dirty working tree can be tied to its exact
exported file set. Dirty builds are labelled as working-tree builds and do not
claim the `HEAD` commit as their exact source revision. This output is build
evidence; it does not mean an image was published.

To require the exporter's non-draft release checks as well, add
`--release-snapshot`. A release snapshot is necessary for publishing. The
exporter still enforces its licence and notice gates; a failure must be resolved
through the project's release review, not bypassed.

## Rehearse install, upgrade and restore

Add `--lifecycle` to run
`python scripts/check-release-lifecycle.py --context desktop-linux --backend-image <candidate> [--previous-backend-image <prior>]`.
The lifecycle checker creates and removes its own Docker network, containers
and volumes. It seeds synthetic requirements, reviews, comments and files,
checks them after upgrade and backup restoration, and checks that restoring
again into populated storage is rejected. Supply `--context` to choose the
Docker context; use `--previous-backend-image` to rehearse from a distinct
prior backend release. Without that option, the candidate is used as both the
installed and upgraded image.

## Release workflow

Run the manual **Release images** workflow with a selected `vMAJOR.MINOR.PATCH`
tag. It confirms that the tag, checked-out commit and workflow event SHA match,
and that the `Verify` workflow succeeded for that same SHA. It builds the five
images from a draft snapshot by default, runs the lifecycle rehearsal, and
saves metadata as a workflow artifact. Selecting the publish input switches to
a non-draft, allowlist-checked export for that same single build-and-verify run.

The workflow's **Push versioned images to GHCR** input defaults to false. Leave
it false for build and rehearsal only. Selecting it is the explicit
authorisation for that workflow run to push. Release preparation and successful
build or lifecycle checks alone do not grant permission to publish. A push run
requires a clean checkout, matching version tag and full revision, a
non-draft allowlisted export with `--check-tracked`, and a passing lifecycle
rehearsal. Grype must be installed on PATH for `--push`. The workflow downloads
the checksum-pinned scanner. It exports each exact built image ID through the
selected Docker context, scans its Docker archive and retains `*.grype.json`
reports. All images must pass the high/critical threshold before any registry
tag or push; scan errors also stop publication. Ambient scanner ignore settings
are not accepted. See the [current security status](security-status.md) for the
findings that currently hold container distribution.
Unresolved exporter licence or notice gates still stop the run. The
CLI equivalent is `--push` with `--repository OWNER/REPOSITORY` and
`--expected-revision`.

The workflow currently builds and verifies `linux/amd64` on its native runner.
Successful arm64 builds or smokes do not establish multi-platform release
coverage; no multi-platform image is claimed here.

Each image receives versioned `vMAJOR.MINOR.PATCH` and revision
`sha-<12-character-commit>` tags; registries can move tags, so neither tag is
immutable. There is no `latest` tag. The OCI revision label and release
metadata bind a clean release build to the full VCS revision; after a push,
metadata records the local image ID separately from the immutable registry
manifest digest for each image. The OCR images also include the in-image
`ocr-build.json` component provenance in the artifact, including the source
version and checksum declared by the built image. Upstream model-loading
findings remain open pending Tesseract 5.5.4; the image uses models supplied by
the distribution, never user-uploaded models. This metadata records provenance
for the statically linked custom OCR binary and does not establish complete
security scan clearance. Deployments should pin the recorded registry digests.
This workflow builds and optionally pushes images; it does not deploy them.
