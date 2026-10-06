#!/usr/bin/env python3
"""Capture notices from the installed, locked runtime dependencies on this host."""

from collections import Counter
from importlib import metadata
import json
from pathlib import Path, PurePosixPath
import platform
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/public/third-party"


def canonical_name(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def licence_metadata(package):
    return (
        package.metadata.get("License-Expression")
        or package.metadata.get("License")
        or "; ".join(
            value for value in package.metadata.get_all("Classifier", [])
            if value.startswith("License ::")
        )
        or "UNSPECIFIED"
    )


def notice_file(path, declared=()):
    name = path.name.lower()
    return (
        name in declared
        or "license" in name or "licence" in name
        or name.startswith(("copying", "notice", "authors"))
        or any(part.lower() in ("licenses", "licences") for part in path.parts)
    ) and path.suffix.lower() not in (".py", ".pyc")


def capture(source, base, target, pending):
    """Read only regular files within the selected installed package."""
    if not source.is_file() or not source.resolve().is_relative_to(base.resolve()):
        return False
    if target in pending:
        raise SystemExit(f"Notice destination collision: {target}")
    pending[target] = source.read_bytes()
    return True


def python_records(pending, review_items):
    records = []
    lock = (ROOT / "backend/requirements.lock").read_text()
    for name, version in re.findall(r"^([A-Za-z0-9_.-]+)==([^\s;]+)", lock, re.M):
        try:
            package = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            records.append({"ecosystem": "python", "name": name, "version": version,
                            "licence": "UNSPECIFIED", "notices": []})
            review_items.append(f"{name}=={version} (not installed on this platform)")
            continue
        if package.version != version or canonical_name(package.metadata["Name"]) != canonical_name(name):
            raise SystemExit(f"Installed Python package differs from lock: {name}=={version}")
        base = Path(package.locate_file(""))
        declared = {Path(value).name.lower() for value in package.metadata.get_all("License-File", [])}
        notices = []
        for file in sorted(package.files or [], key=str):
            relative = PurePosixPath(str(file))
            if relative.is_absolute() or ".." in relative.parts or not notice_file(relative, declared):
                continue
            source = Path(package.locate_file(file))
            target = OUT / "python" / name / Path(*relative.parts)
            if capture(source, base, target, pending):
                notices.append(str(target.relative_to(ROOT)))
        records.append({"ecosystem": "python", "name": name, "version": version,
                        "licence": licence_metadata(package), "notices": notices})
        if not notices:
            review_items.append(f"{name}=={version} (no licence text in installed distribution)")
    return records


def readme_has_full_licence(readme):
    text = readme.read_text(errors="replace")
    return bool(re.search(r"(?im)^\s*(?:#+\s*)?licen[cs]e\s*$", text)
                and "Permission is hereby granted" in text
                and "THE SOFTWARE IS PROVIDED" in text
                and "Copyright" in text)


def npm_records(pending, review_items):
    records = []
    packages = json.loads((ROOT / "frontend/package-lock.json").read_text())["packages"]
    runtime = [(path, info) for path, info in packages.items() if path and not info.get("dev")]
    duplicates = Counter(path.split("node_modules/")[-1] for path, _ in runtime)
    for path, info in runtime:
        relative = PurePosixPath(path)
        if relative.is_absolute() or ".." in relative.parts or "node_modules" not in relative.parts:
            raise SystemExit(f"Invalid npm lock path: {path}")
        name = path.split("node_modules/")[-1]
        source = ROOT / "frontend" / Path(*relative.parts)
        target_dir = OUT / "npm" / (Path(*relative.parts) if duplicates[name] > 1 else Path(name))
        notices = []
        if source.is_dir():
            manifest = source / "package.json"
            if not manifest.is_file() or not manifest.resolve().is_relative_to(source.resolve()):
                raise SystemExit(f"Missing installed npm manifest: {path}")
            installed = json.loads(manifest.read_text())
            if installed.get("name") != name or installed.get("version") != info["version"]:
                raise SystemExit(f"Installed npm package differs from lock: {path}")
            if installed.get("license") and info.get("license") and installed["license"] != info["license"]:
                raise SystemExit(f"Installed npm licence differs from lock: {path}")
            for file in sorted(source.iterdir()):
                if file.is_file() and notice_file(PurePosixPath(file.name)):
                    target = target_dir / file.name
                    if capture(file, source, target, pending):
                        notices.append(str(target.relative_to(ROOT)))
            if not notices:
                readme = source / "README.md"
                if readme.is_file() and readme.resolve().is_relative_to(source.resolve()) and readme_has_full_licence(readme):
                    target = target_dir / readme.name
                    if capture(readme, source, target, pending):
                        notices.append(str(target.relative_to(ROOT)))
        records.append({"ecosystem": "npm", "name": name, "version": info["version"],
                        "lock_path": path, "licence": info.get("license", "UNSPECIFIED"),
                        "integrity": info.get("integrity"), "notices": notices})
        if not notices:
            review_items.append(f'{name}@{info["version"]} ({path}; no licence text in installed package)')
    return records


def main():
    pending = {}
    review_items = []
    records = python_records(pending, review_items) + npm_records(pending, review_items)
    inventory = {
        "scope": "Locked runtime Python and npm dependencies installed on this host; excludes container OS packages and optional external services",
        "platform": platform.system() + " " + platform.machine(),
        "packages": records,
        "review_items": review_items,
    }
    pending[OUT / "inventory.json"] = (json.dumps(inventory, indent=2) + "\n").encode()
    for target, content in pending.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_bytes() != content:
            target.write_bytes(content)
    print(f"Captured {len(records)} package records; {len(review_items)} notice review items.")


if __name__ == "__main__":
    main()
