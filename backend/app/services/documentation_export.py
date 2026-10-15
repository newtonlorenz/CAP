"""Frozen register metadata and selected immutable evidence, with deduplicated bytes."""

import hashlib
import io
import json
import tempfile
import zipfile
from fastapi import HTTPException
from app.services.preparation_files import checked_evidence_path
from app.services.preparation_export import MAX_EXPORT_BYTES, _csv_value
import csv


def build_documentation_archive(snapshot_data, evidence):
    """Caller checks current source export rights. Returned stream belongs to caller.

    Frozen metadata retains immutable library version IDs; selected file bytes
    are copied once per content digest by freeze_evidence_files. This helper also
    accepts a frozen record when assembling a certification pack.
    """
    files = {}
    metadata = []
    for item in evidence:
        row = {
            "id": str(item.id),
            "title": item.title,
            "kind": item.kind,
            "sha256": item.sha256,
            "size_bytes": item.size_bytes,
            "body": item.body,
            "link_url": item.link_url,
            "valid_from": str(item.valid_from) if item.valid_from else None,
            "valid_until": str(item.valid_until) if item.valid_until else None,
            "content_status": "references_only" if item.kind == "link" else "included",
        }
        if item.kind == "file":
            path = getattr(item, "frozen_path", None) or checked_evidence_path(item)
            name = f"evidence/{item.sha256}"
            row["archive_path"] = name
            files.setdefault(name, (item, path))
        metadata.append(row)
    record = dict(snapshot_data, selected_evidence=metadata)
    payloads = {"documentation.json": json.dumps(record, indent=2, ensure_ascii=False).encode()}
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    if record.get("format_version", 1) >= 2:
        writer.writerow(
            [
                "Document / record required",
                "SCP reference",
                "Comment/explanation",
                "Document",
                "Section",
            ]
        )
        sections = {row["id"]: row for row in record.get("sections", [])}
        for row in record.get("expectations", []):
            section = sections.get(str(row.get("section_id")), {})
            writer.writerow(
                [
                    _csv_value(value)
                    for value in (
                        (
                            row.get("required_documentation")
                            if row.get("required_documentation") is not None
                            else row.get("title")
                        ),
                        row.get("source_reference"),
                        row.get("description"),
                        row.get("document_name"),
                        section.get("name", row.get("section_name", "")),
                    )
                ]
            )
    else:
        # Preserve the existing derivative format for historical frozen records.
        writer.writerow(
            [
                "Title",
                "Category",
                "Source reference",
                "Applicability",
                "Coverage status",
                "Review rationale",
            ]
        )
        for row in record.get("expectations", []):
            writer.writerow(
                [
                    _csv_value(row.get(key))
                    for key in (
                        "title",
                        "category",
                        "source_reference",
                        "applicability",
                        "coverage_status",
                        "review_rationale",
                    )
                ]
            )
    payloads["register.csv"] = stream.getvalue().encode("utf-8-sig")
    manifest = {
        "format_version": 1,
        "purpose": "Internal workflow handover; no submission, certification or audit opinion is recorded.",
        "files": [],
        "references_only": [
            row["id"] for row in metadata if row["content_status"] == "references_only"
        ],
    }
    output = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    total = 0

    def entry(name):
        result = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        result.compress_type = zipfile.ZIP_DEFLATED
        return result

    try:
        with zipfile.ZipFile(output, "w") as archive:
            for name, content in sorted(payloads.items()):
                total += len(content)
                if total > MAX_EXPORT_BYTES:
                    raise HTTPException(413, "Documentation pack exceeds 200 MB")
                archive.writestr(entry(name), content)
                manifest["files"].append(
                    {
                        "path": name,
                        "size_bytes": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                )
            for name, (item, path) in sorted(files.items()):
                digest = hashlib.sha256()
                size = 0
                with path.open("rb") as source, archive.open(entry(name), "w") as target:
                    while chunk := source.read(1024 * 1024):
                        size += len(chunk)
                        total += len(chunk)
                        if total > MAX_EXPORT_BYTES:
                            raise HTTPException(413, "Documentation pack exceeds 200 MB")
                        target.write(chunk)
                        digest.update(chunk)
                if digest.hexdigest() != item.sha256 or size != item.size_bytes:
                    raise HTTPException(
                        409, "Evidence integrity changed; supply a verified version"
                    )
                manifest["files"].append(
                    {"path": name, "size_bytes": size, "sha256": digest.hexdigest()}
                )
            archive.writestr(entry("manifest.json"), json.dumps(manifest, indent=2).encode())
        output.seek(0)
        return output
    except BaseException:
        output.close()
        raise


def snapshot_root(organization_id):
    from pathlib import Path
    from app.config import settings

    return (
        Path(settings.upload_dir).resolve()
        / "documentation-snapshots"
        / str(organization_id or "installation")
    )


def freeze_evidence_files(evidence, organization_id):
    """Freeze bytes by content digest; identical selected bytes share one stored copy."""
    import os
    from app.services.preparation_files import file_digest

    root = snapshot_root(organization_id)
    root.mkdir(parents=True, exist_ok=True)
    total = 0
    counted_digests = set()
    records = []
    verified_sources = set()
    verified_targets = set()
    for item in evidence:
        row = {
            "id": str(item.id),
            "title": item.title,
            "kind": item.kind,
            "body": item.body,
            "link_url": item.link_url,
            "filename": item.filename,
            "sha256": item.sha256,
            "size_bytes": item.size_bytes,
            "valid_from": str(item.valid_from) if item.valid_from else None,
            "valid_until": str(item.valid_until) if item.valid_until else None,
        }
        if item.kind == "file":
            source = getattr(item, "_verified_source_path", None) or checked_evidence_path(item)
            if item.sha256 not in counted_digests:
                total += item.size_bytes
                counted_digests.add(item.sha256)
            if total > MAX_EXPORT_BYTES:
                raise HTTPException(413, "Documentation pack exceeds 200 MB")
            target = root / item.sha256
            source_key = (str(source), item.sha256, item.size_bytes)
            created = False
            if not target.exists():
                temporary = tempfile.NamedTemporaryFile(dir=root, prefix=".freeze-", delete=False)
                try:
                    digest = hashlib.sha256()
                    size = 0
                    with temporary, source.open("rb") as reader:
                        while chunk := reader.read(1024 * 1024):
                            size += len(chunk)
                            if size > item.size_bytes:
                                raise HTTPException(
                                    409, "Evidence changed during snapshot creation"
                                )
                            digest.update(chunk)
                            temporary.write(chunk)
                    if size != item.size_bytes or digest.hexdigest() != item.sha256:
                        raise HTTPException(409, "Evidence changed during snapshot creation")
                    verified_sources.add(source_key)
                    # Atomic create preserves a concurrently frozen identical digest.
                    try:
                        os.link(temporary.name, target)
                        created = True
                    except FileExistsError:
                        pass
                finally:
                    os.unlink(temporary.name)
            elif source_key not in verified_sources:
                if source.stat().st_size != item.size_bytes or file_digest(source) != item.sha256:
                    raise HTTPException(409, "Canonical evidence bytes changed before freezing")
                verified_sources.add(source_key)
            if item.sha256 not in verified_targets:
                if (
                    target.is_symlink()
                    or target.stat().st_size != item.size_bytes
                    or (not created and file_digest(target) != item.sha256)
                ):
                    raise HTTPException(409, "Frozen evidence integrity check failed")
                verified_targets.add(item.sha256)
        records.append(row)
    return records


def frozen_evidence(records, organization_id):
    from types import SimpleNamespace
    import re

    result = []
    for row in records:
        values = dict(row)
        if values["kind"] == "file":
            if not re.fullmatch(r"[a-f0-9]{64}", values.get("sha256") or ""):
                raise HTTPException(409, "Invalid frozen evidence digest")
            path = snapshot_root(organization_id) / values["sha256"]
            if not path.is_file() or path.is_symlink():
                raise HTTPException(409, "Frozen evidence file is unavailable")
            values["frozen_path"] = path
        result.append(SimpleNamespace(**values))
    return result
