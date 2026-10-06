"""The public snapshot must fail closed on accidental private-file additions."""

import hashlib
import importlib.util
import io
import subprocess
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("public_export", ROOT / "scripts/export-public.py")
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


def test_tracked_manifest_rejects_private_files_but_ignores_local_notes(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, "ROOT", tmp_path)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "source.py").write_text('print("hello")\n')
    (tmp_path / "private-notes.md").write_text("Local notes, not for distribution\n")
    subprocess.run(["git", "add", "source.py"], cwd=tmp_path, check=True)

    exporter.validate_tracked_manifest({"source.py"})
    subprocess.run(["git", "add", "private-notes.md"], cwd=tmp_path, check=True)
    with pytest.raises(ValueError, match="outside distribution manifest: private-notes.md"):
        exporter.validate_tracked_manifest({"source.py"})


def test_tracked_manifest_requires_allowlisted_files_to_be_versioned(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, "ROOT", tmp_path)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "LICENSE").write_text("Example licence\n")
    with pytest.raises(ValueError, match="Distribution files are not tracked: LICENSE"):
        exporter.validate_tracked_manifest({"LICENSE"})


def test_tracked_manifest_accepts_export_checksum_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, "ROOT", tmp_path)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "source.py").write_text('print("hello")\n')
    (tmp_path / "SNAPSHOT.json").write_text('{"files": []}\n')
    subprocess.run(["git", "add", "source.py", "SNAPSHOT.json"], cwd=tmp_path, check=True)
    exporter.validate_tracked_manifest({"source.py"})


@pytest.mark.parametrize(
    "name",
    [
        ".git/config",
        "../outside",
        "/tmp/outside",
        ".env.staging",
        "db.sql",
        "backup.capbak",
        "docs/releases/private.md",
    ],
)
def test_export_rejects_private_paths_before_reading(tmp_path, monkeypatch, name):
    monkeypatch.setattr(exporter, "ROOT", tmp_path)
    with pytest.raises(ValueError):
        exporter.validate_entry(name)


def test_export_rejects_symlinks_and_secret_material(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, "ROOT", tmp_path)
    source = tmp_path / "source.py"
    source.write_text("ordinary source")
    link = tmp_path / "link.py"
    link.symlink_to(source)
    with pytest.raises(ValueError, match="Symlink"):
        exporter.validate_entry("link.py")
    source.write_text("-----BEGIN " + "PRIVATE KEY-----")
    with pytest.raises(ValueError, match="Potential secret"):
        exporter.validate_entry("source.py")


def test_export_accepts_safe_source(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, "ROOT", tmp_path)
    (tmp_path / "source.py").write_text('print("hello")\n')
    data, _ = exporter.validate_entry("source.py")
    assert data == b'print("hello")\n'


def test_export_writes_validated_bytes_even_if_source_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, "ROOT", tmp_path)
    source = tmp_path / "source.py"
    source.write_bytes(b"approved bytes\n")
    data, mode = exporter.validate_entry("source.py")
    source.write_bytes(b"changed after validation\n")

    output = tmp_path / "snapshot"
    digest = exporter.write_validated_entry(output, "source.py", data, mode)

    assert (output / "source.py").read_bytes() == b"approved bytes\n"
    assert digest == hashlib.sha256((output / "source.py").read_bytes()).hexdigest()


def test_export_scans_the_archive_bytes_it_will_write(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, "ROOT", tmp_path)
    archive_path = tmp_path / "widget.tgz"

    def archive_bytes(body):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w:gz") as archive:
            member = tarfile.TarInfo("package/source.txt")
            member.size = len(body)
            archive.addfile(member, io.BytesIO(body))
        return stream.getvalue()

    archive_path.write_bytes(archive_bytes(b"harmless archive on disk"))
    unsafe = archive_bytes(b"-----BEGIN " + b"PRIVATE KEY-----")
    original_read_bytes = Path.read_bytes

    def read_bytes(path):
        return unsafe if path == archive_path else original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    with pytest.raises(ValueError, match="Potential secret in archive"):
        exporter.validate_entry("widget.tgz")


def test_snapshot_does_not_ship_country_parser_templates():
    import json

    files = set(json.loads((ROOT / 'publication-manifest.json').read_text())['files'])
    assert not any(path.startswith('backend/app/jurisdictions/') for path in files)
    assert 'backend/app/services/annex_a_importer.py' not in files
    assert 'backend/app/services/annex_b_importer.py' not in files
    assert 'backend/app/services/pdf_parser.py' in files
    assert 'backend/alembic/versions/g20260926_generic_parser_metadata.py' in files
