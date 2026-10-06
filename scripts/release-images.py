#!/usr/bin/env python3
"""Build CAP release images from the history-free public export.

Builds locally by default. Registry writes require the explicit --push flag.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\Z")
IMAGES = {
    "backend-runtime": ("backend", "runtime"),
    "backend-ocr": ("backend", "ocr"),
    "backend-structured": ("backend", "structured"),
    "backend-structured-ocr": ("backend", "structured_ocr"),
    "frontend": ("frontend", None),
}


def run(command, *, cwd=ROOT, capture_output=False, env=None):
    return subprocess.run(
        command, cwd=cwd, check=True, text=True, capture_output=capture_output, env=env
    )


def git_revision():
    return run(["git", "rev-parse", "--verify", "HEAD"], capture_output=True).stdout.strip()


def is_clean_worktree():
    status = run(["git", "status", "--porcelain", "--untracked-files=all"], capture_output=True).stdout
    return not status


def validate(args):
    if not VERSION.fullmatch(args.version):
        raise ValueError("Version must be a semantic release tag such as v1.2.3.")
    if args.push:
        if not args.expected_revision:
            raise ValueError("Publishing requires --expected-revision from the validated release tag.")
        if args.draft:
            raise ValueError("A draft public snapshot can never be published.")
        if not args.lifecycle:
            raise ValueError("Publishing requires the install/upgrade/restore lifecycle rehearsal.")
        if not args.repository:
            raise ValueError("Publishing requires --repository OWNER/REPOSITORY.")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
            raise ValueError("Repository must be OWNER/REPOSITORY.")
    revision = git_revision()
    if args.expected_revision and revision != args.expected_revision:
        raise ValueError("Checked-out revision does not match the expected release commit.")
    clean = is_clean_worktree()
    if args.push:
        tagged_revision = run([
            "git", "rev-parse", "--verify", "--end-of-options",
            f"refs/tags/{args.version}^{{commit}}",
        ], capture_output=True).stdout.strip()
        if tagged_revision != revision:
            raise ValueError("The requested version tag must resolve directly to checked-out HEAD.")
        if not clean:
            raise ValueError("Publishing requires a completely clean tracked and untracked checkout.")
    return revision, clean


def docker_command(args, *parts):
    return ["docker", "--context", args.context, *parts]


def require_scanner():
    scanner = shutil.which("grype")
    if not scanner:
        raise ValueError("Publishing requires Grype on PATH; no images were built or pushed.")
    return scanner


def archive_config_digest(archive):
    # Containerd-backed Docker stores can identify images by their manifest digest;
    # Grype's imageID is the config digest, verified from the exact saved archive.
    with tarfile.open(archive) as saved:
        manifest_file = saved.extractfile("manifest.json")
        if manifest_file is None:
            raise ValueError("Docker scan archive has no manifest.")
        manifest = json.load(manifest_file)
        if not isinstance(manifest, list) or len(manifest) != 1:
            raise ValueError("Docker scan archive must contain exactly one image.")
        config = saved.extractfile(manifest[0]["Config"])
        if config is None:
            raise ValueError("Docker scan archive has no image configuration.")
        return "sha256:" + hashlib.sha256(config.read()).hexdigest()


def scan_release_images(args, metadata, scanner, temporary):
    # An explicit archive source never lets Grype select a different Docker daemon.
    # Docker exports the immutable IDs from the same context used for the builds.
    config = temporary / "grype.yaml"
    config.write_text("ignore: []\nonly-fixed: false\nonly-notfixed: false\nignore-states: ''\nexclude: []\nvex-documents: []\nvex-add: []\n")
    scanner_env = {
        key: value for key, value in os.environ.items()
        if not key.startswith(("GRYPE_", "SYFT_"))
    }
    for name in IMAGES:
        image = metadata["images"][name]
        image_id = image["local_image_id"]
        archive = temporary / f"{name}.tar"
        report = args.output / f"{name}.grype.json"
        report.unlink(missing_ok=True)
        run(docker_command(args, "image", "save", "--output", str(archive), image_id))
        try:
            config_digest = archive_config_digest(archive)
            run([
                scanner, f"docker-archive:{archive}", "--config", str(config),
                "--fail-on", "high", "--output", "json", "--file", str(report),
            ], env=scanner_env)
            try:
                result = json.loads(report.read_text())
            except (OSError, json.JSONDecodeError) as error:
                raise ValueError(f"{name} has no valid Grype JSON report.") from error
            if not isinstance(result, dict) or not isinstance(result.get("matches"), list):
                raise ValueError(f"{name} has an incomplete Grype JSON report.")
            source = result.get("source")
            target = source.get("target") if isinstance(source, dict) else None
            if not isinstance(target, dict) or target.get("imageID") != config_digest:
                raise ValueError(f"{name} Grype report does not match the exported image configuration.")
            image["scanned_config_digest"] = config_digest
            image["vulnerability_report"] = report.name
        finally:
            archive.unlink(missing_ok=True)


def run_smoke_checks(args, snapshot, name, image):
    backend = name.startswith("backend-")
    provenance_path = None
    if backend:
        for flag in ("-u", "-g"):
            result = run(docker_command(args, "run", "--rm", "--network", "none", "--entrypoint", "id", image, flag), capture_output=True)
            if result.stdout.strip() != "10001":
                raise ValueError(f"{name} image must run as UID/GID 10001.")
        run(docker_command(args, "run", "--rm", "--network", "none", "--entrypoint", "python", image, "-c", "import app.main"))
    if name in {"backend-ocr", "backend-structured-ocr"}:
        run(docker_command(args, "run", "--rm", "--network", "none", "--entrypoint", "tesseract", image, "--list-langs"))
        engine = "native" if name == "backend-ocr" else "opendataloader"
        smoke = snapshot / "backend/tests/test_pdf_ocr_smoke.py"
        run(docker_command(
            args, "run", "--rm", "--network", "none", "-e", f"CAP_OCR_SMOKE_ENGINE={engine}",
            "-e", "PYTHONPATH=/app", "--entrypoint", "python", "-v", f"{smoke}:/tmp/test_pdf_ocr_smoke.py:ro",
            image, "/tmp/test_pdf_ocr_smoke.py",
        ))
        provenance_result = run(docker_command(
            args, "run", "--rm", "--network", "none", "--entrypoint", "cat", image,
            "/usr/local/share/cap/ocr-build.json",
        ), capture_output=True)
        try:
            provenance = json.loads(provenance_result.stdout)
        except json.JSONDecodeError as error:
            raise ValueError(f"{name} image has invalid OCR build provenance JSON.") from error
        if not isinstance(provenance, dict):
            raise ValueError(f"{name} OCR build provenance must be a JSON object.")
        provenance_path = args.output / f"{name}-ocr-build.json"
        provenance_path.write_text(json.dumps(provenance, indent=2) + "\n")
    if name in {"backend-structured", "backend-structured-ocr"}:
        run(docker_command(args, "run", "--rm", "--network", "none", "--entrypoint", "python", image,
                           "-c", "import opendataloader_pdf; import app.services.structured_pdf"))
        run(docker_command(args, "run", "--rm", "--network", "none", "--entrypoint", "java", image, "-version"))
        fixture = snapshot / "backend/tests/fixtures/sample_requirements.pdf"
        code = (
            "import tempfile; from app.services.structured_pdf import read_structured_pdf; "
            "from app.services.structured_requirements import parse_structured_requirements; "
            "data=read_structured_pdf('/tmp/fixture.pdf', tempfile.mkdtemp(), timeout=45); "
            "refs=[item['reference_id'] for item in parse_structured_requirements(data)]; "
            "assert data['number of pages']==1 and refs==['4.2','4.2.1','4.2.2','4.2.3','4.3','4.3.1','4.3.2'], refs"
        )
        run(docker_command(args, "run", "--rm", "--network", "none", "--entrypoint", "python", "-v",
                           f"{fixture}:/tmp/fixture.pdf:ro", image, "-c", code))
    if name == "frontend":
        run(docker_command(args, "run", "--rm", "--entrypoint", "nginx", image, "-t"))
    return provenance_path


def build(args):
    revision, clean = validate(args)
    scanner = require_scanner() if args.push else None
    registry = f"{args.registry.rstrip('/')}/{args.repository.lower()}" if args.push else None
    args.output = args.output.expanduser().resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    draft_snapshot = args.draft or not (args.release_snapshot or args.push)
    if clean:
        source_tag = args.version + ("-draft" if draft_snapshot else "")
    else:
        source_tag = args.version + "-working-tree"
    metadata = {
        "version": args.version,
        "source_revision": revision if clean else None,
        "base_revision": revision,
        "working_tree_clean": clean,
        "snapshot_draft": draft_snapshot,
        "source_snapshot": "source-snapshot.json",
        "images": {},
    }

    with tempfile.TemporaryDirectory(prefix="cap-public-release-") as temporary:
        snapshot = Path(temporary) / "source"
        run([
            sys.executable,
            str(ROOT / "scripts/export-public.py"),
            "--output", str(snapshot),
            *( ["--draft"] if draft_snapshot else [] ),
            *( ["--check-tracked"] if args.push else [] ),
        ])
        snapshot_manifest = (snapshot / "SNAPSHOT.json").read_bytes()
        (args.output / "source-snapshot.json").write_bytes(snapshot_manifest)
        metadata["source_snapshot_sha256"] = hashlib.sha256(snapshot_manifest).hexdigest()
        for name, (directory, target) in IMAGES.items():
            local_tag = f"cap-release/{name}:{source_tag}"
            metadata_file = args.output / f"{name}.build-metadata.json"
            command = docker_command(args, "buildx", "build", "--platform", args.platform)
            if target:
                command += ["--target", target]
            command += ["--build-arg", f"VCS_REF={revision if clean else 'unknown'}"]
            command += ["--tag", local_tag]
            command += ["--metadata-file", str(metadata_file)]
            command += ["--load"]
            command.append(str(snapshot / directory))
            run(command)
            build_metadata = json.loads(metadata_file.read_text()) if metadata_file.exists() else {}
            image_id = run(docker_command(args, "image", "inspect", "--format", "{{.Id}}", local_tag), capture_output=True).stdout.strip()
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
                raise ValueError(f"Docker returned no valid local image ID for {name}.")
            provenance_path = run_smoke_checks(args, snapshot, name, image_id)
            metadata["images"][name] = {
                "local_image_id": image_id,
                "local_buildx_manifest_digest": build_metadata.get("containerimage.digest"),
                "tags": [local_tag],
            }
            if provenance_path:
                metadata["images"][name]["ocr_build_provenance"] = provenance_path.name

        if args.lifecycle:
            command = [
                sys.executable, str(ROOT / "scripts/check-release-lifecycle.py"),
                "--context", args.context, "--backend-image", metadata["images"]["backend-runtime"]["local_image_id"],
            ]
            if args.previous_backend_image:
                command += ["--previous-backend-image", args.previous_backend_image]
            run(command)

        if registry:
            scan_release_images(args, metadata, scanner, Path(temporary))
            for name in IMAGES:
                tags = [
                    f"{registry}/{name}:{args.version}",
                    f"{registry}/{name}:sha-{revision[:12]}",
                ]
                image_id = metadata["images"][name]["local_image_id"]
                version_tag, revision_tag = tags
                run(docker_command(args, "tag", image_id, version_tag))
                run(docker_command(args, "tag", image_id, revision_tag))
                pushed = run(docker_command(args, "push", version_tag), capture_output=True)
                match = re.search(r"\bdigest:\s*(sha256:[0-9a-f]{64})\b", pushed.stdout + "\n" + pushed.stderr)
                if not match:
                    raise ValueError(f"Docker push did not report a registry manifest digest for {name}.")
                run(docker_command(args, "push", revision_tag))
                metadata["images"][name]["registry_manifest_digest"] = match.group(1)
                metadata["images"][name]["tags"] = tags

    destination = args.output / "release-metadata.json"
    destination.write_text(json.dumps(metadata, indent=2) + "\n")
    print(destination)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="Semantic release tag, for example v1.2.3")
    parser.add_argument("--output", type=Path, default=Path("tmp/release-output"))
    parser.add_argument("--platform", default="linux/amd64")
    parser.add_argument("--registry", default="ghcr.io")
    parser.add_argument("--repository", help="OWNER/REPOSITORY; required with --push")
    parser.add_argument("--expected-revision", help="Full VCS revision validated by the release workflow")
    parser.add_argument("--push", action="store_true", help="Push release tags to the configured registry")
    snapshot = parser.add_mutually_exclusive_group()
    snapshot.add_argument("--draft", dest="draft", action="store_true", help="Use a draft export (local verification only)")
    snapshot.add_argument("--release-snapshot", dest="release_snapshot", action="store_true", help="Require release-ready export gates")
    parser.set_defaults(draft=False, release_snapshot=False)
    parser.add_argument("--lifecycle", action="store_true", help="Run disposable install/upgrade/restore rehearsal")
    parser.add_argument("--previous-backend-image", help="Prior backend image for the upgrade rehearsal")
    parser.add_argument("--context", default="default", help="Docker context for builds, checks, scan exports and pushes")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    build(args)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, subprocess.CalledProcessError) as error:
        message = error.stderr.strip() if isinstance(error, subprocess.CalledProcessError) and error.stderr else str(error)
        sys.exit(message)
