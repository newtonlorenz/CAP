#!/usr/bin/env python3
"""Create a new history-free, allowlisted snapshot. Never publishes or alters Git."""

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
SECRET = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-(?:proj-|ant-)?[A-Za-z0-9_-]{35,}"
)
DENIED = {
    ".git",
    ".env",
    ".env.production",
    ".env.local",
    "node_modules",
    "__pycache__",
    ".venv",
    "uploads",
    "backups",
    "secrets",
    "tmp",
}


def validate_tracked_manifest(files):
    """Require the Git index to contain only the reviewed distribution files."""
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True, text=True
    )
    tracked = set(result.stdout.split("\0")) - {""}
    # A repository created from an export can retain its checksum manifest.
    unexpected = sorted(tracked - files - {"SNAPSHOT.json"})
    missing = sorted(files - tracked)
    if unexpected:
        raise ValueError("Tracked files outside distribution manifest: " + ", ".join(unexpected))
    if missing:
        raise ValueError("Distribution files are not tracked: " + ", ".join(missing))


def validate_notice_manifest(files, *, draft):
    """Keep generated third-party notice paths in the explicit export allowlist."""
    inventory = json.loads((ROOT / "docs/public/third-party/inventory.json").read_text())
    missing = sorted(
        {
            notice
            for package in inventory["packages"]
            for notice in package["notices"]
            if notice not in files
        }
    )
    if missing:
        raise ValueError("Third-party notices missing from export manifest: " + ", ".join(missing))
    if not draft and inventory["review_items"]:
        raise ValueError("Third-party notice review items remain unresolved.")


def validate_entry(raw):
    path = PurePosixPath(raw)
    if (
        not raw
        or path.is_absolute()
        or ".." in path.parts
        or any(part in DENIED for part in path.parts)
    ):
        raise ValueError(f"Forbidden export path: {raw}")
    if (
        (
            path.name.startswith(".env")
            and path.name not in {".env.example", ".env.production.example"}
        )
        or path.suffix.lower() in {".sql", ".db", ".sqlite", ".capbak", ".pem", ".key"}
        or raw.startswith(("docs/releases/", "docs/reviews/", "docs/plans/"))
    ):
        raise ValueError(f"Private data or operational material is not exportable: {raw}")
    source = ROOT / path
    if any(part.is_symlink() for part in [source, *source.parents] if part != ROOT.parent):
        raise ValueError(f"Symlink is not exportable: {raw}")
    if not source.is_file() or not source.resolve().is_relative_to(ROOT):
        raise ValueError(f"Export file is missing or outside the source: {raw}")
    content = source.read_bytes()
    if SECRET.search(content):
        raise ValueError(f"Potential secret in export file: {raw}")
    if source.suffix == ".tgz":
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as archive:
            for member in archive:
                member_path = PurePosixPath(member.name)
                if (
                    member_path.is_absolute()
                    or ".." in member_path.parts
                    or member.issym()
                    or member.islnk()
                ):
                    raise ValueError(f"Unsafe archive member in: {raw}")
                if member.isfile():
                    if member.size > 10 * 1024 * 1024:
                        raise ValueError(f"Oversized archive member in: {raw}")
                    if SECRET.search(archive.extractfile(member).read()):
                        raise ValueError(f"Potential secret in archive: {raw}")
    return content, source.stat().st_mode & 0o777


def write_validated_entry(destination, name, content, mode):
    """Write precisely the bytes that passed validation and enter the checksum."""
    target = destination / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    target.chmod(mode)
    return hashlib.sha256(content).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--draft", action="store_true")
    parser.add_argument(
        "--check-tracked", action="store_true",
        help="Require the Git index to match the distribution allowlist.",
    )
    args = parser.parse_args()
    destination = args.output.absolute()
    if destination.exists():
        parser.error("Output must be a new directory; existing data is never overwritten.")
    manifest = json.loads((ROOT / "publication-manifest.json").read_text())
    files = manifest["files"]
    if len(files) != len(set(files)):
        parser.error("The manifest contains duplicate paths.")
    if args.check_tracked:
        validate_tracked_manifest(set(files))
    validate_notice_manifest(set(files), draft=args.draft)
    if not args.draft and ("LICENSE" not in files or not (ROOT / "LICENSE").is_file()):
        parser.error("Release blocked: adopt LICENSE and add it to the reviewed manifest first.")
    validated = [(name, *validate_entry(name)) for name in files]
    destination.mkdir(parents=True)
    hashes = {}
    for name, content, mode in validated:
        hashes[name] = write_validated_entry(destination, name, content, mode)
    (destination / "SNAPSHOT.json").write_text(
        json.dumps(
            {
                "draft": args.draft,
                "files": [{"path": path, "sha256": digest} for path, digest in hashes.items()],
            },
            indent=2,
        )
        + "\n"
    )
    if args.draft:
        (destination / "UNPUBLISHED_DRAFT.txt").write_text(
            "Private review snapshot. Rights and publication approval pending. Do not publish.\n"
        )
    print(
        f"Created {len(hashes)} allowlisted files at {destination}. No history copied; nothing published."
    )


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        sys.exit(str(error))
