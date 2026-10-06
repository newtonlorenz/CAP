# Source candidate security status

Reviewed on 6 October 2026. This source candidate is available for inspection and
local evaluation. It is not a qualified production container release. CAP does
not distribute versioned container images with this first source publication.

## Application dependencies and publication assets

The locked Python runtime and optional structured-PDF Python requirements passed
pip-audit 2.10.1 without known Python-package findings. The npm runtime audit
passed with zero findings after updating DOMPurify to 3.4.16. The compatible
source-map-js build dependency was also updated to 1.2.2.

The full npm development audit still identifies Tailwind 3's braces/micromatch
build-time pattern handling and its nested selector parser. These tools process
maintainer-controlled build configuration and source files; they are not shipped
in the Nginx runtime image or called with uploaded CAP documents. Build untrusted
contributions only in disposable environments without credentials. A Tailwind 4
migration requires separate UI/build validation; no forced major update or blanket
vulnerability suppression was used here.

Gitleaks 8.30.1 scanned the allowlisted source tree and nested archives without
finding secrets. Both included PDF fixtures reproduced byte-for-byte from their
synthetic generators. The spreadsheet contains synthetic questions and
instructions; it has no hidden sheets, macros, external links or completed answers.
The font, widget and dependency notices retain their separate licences. Daniel
Graetzer confirmed authority to publish the first-party material.

## Container findings and distribution restriction

The Python base was updated to checksum-pinned Python 3.12.15. The backend build
upgrades installed Debian packages before installing its runtime tools. A rebuilt
linux/amd64 runtime scan with Trivy 0.75.0 reported no critical findings and no
high findings with an available fixed package version, but still reported 47 high
package matches. Package counts are not counts of exploitable CAP paths, and the
remaining findings have not all been qualified as inapplicable.

Important findings requiring continued image review include:

- Pillow 12.3.0's bundled libtiff 4.7.1: the upstream TIFF decoding finding
  [CVE-2026-4775](https://security-tracker.debian.org/tracker/CVE-2026-4775)
  requires wheel-specific patch/build evidence. A Debian package upgrade does not
  patch libraries bundled inside a Python wheel.
- The optional OpenDataLoader 2.5.11 Java archive includes Jackson core/databind
  2.22.2. The latest 2.5.12 wheel was also inspected and retains those versions.
  [Jackson core](https://github.com/FasterXML/jackson-core/security/advisories/GHSA-p6pp-m3f8-5c89)
  and [Jackson databind](https://github.com/FasterXML/jackson-databind/security/advisories/GHSA-cxp5-3px4-pw24)
  advisories identify fixes in 2.22.3. Structured-image distribution remains held
  pending an upstream fix or a documented, narrowly evidenced applicability review.
- The OCR scan's critical
  [CVE-2026-52490](https://security-tracker.debian.org/tracker/CVE-2026-52490)
  concerns the tiffcrop executable. Package presence alone does not establish that
  this tool is installed or invoked; check the actual image before making a
  component-specific disposition.
- [zlib CVE-2026-85091](https://security-tracker.debian.org/tracker/CVE-2026-85091)
  and remaining Debian local/conditional findings require version and call-path
  review. A distribution's `wont-fix` status is not proof that CAP is unaffected.

CI retains scans of all five exact image SBOMs for review. The image publication
command separately scans every exact built image with Grype and refuses to push
if any image has a high or critical finding, or if scanning fails. It does not
ignore unfixed vulnerabilities. Source publication does not waive this image gate.

## Verification scope

Runtime-image smoke checks and synthetic clean-install/backup-restore rehearsals
do not establish production readiness, complete regulatory extraction, real AI
provider behaviour, or an external regulator's acceptance. The source Verify
workflow covers application, migration, browser, job-delivery and image lifecycle
checks against disposable data. Record its successful commit before publication.
