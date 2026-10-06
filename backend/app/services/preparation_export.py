"""Portable preparation records with bounded, checksummed evidence attachments."""

import csv
import hashlib
import io
import json
import tempfile
import zipfile
from datetime import datetime, timezone

from fastapi import HTTPException

from app.schemas.preparation_evidence import EvidenceResponse
from app.services.preparation_files import checked_evidence_path, clean_filename

MAX_EXPORT_BYTES = 200 * 1024 * 1024


def _csv_value(value) -> str:
    text = "" if value is None else (str(value).lower() if isinstance(value, bool) else str(value))
    # Prevent a spreadsheet from treating user-entered responses as formulas.
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def build_preparation_archive(
    case_data: dict, evidence: list, *, jurisdiction: str, owner: str | None
):
    """The caller owns the returned temporary stream; no storage paths are exported."""
    if (
        len(evidence) > 200
        or sum(len(item.body or "") + len(item.link_url or "") for item in evidence)
        > 10 * 1024 * 1024
    ):
        raise HTTPException(
            413, "This form export contains too much evidence. Export fewer attachments."
        )
    files = [(item, checked_evidence_path(item)) for item in evidence if item.kind == "file"]
    if sum(path.stat().st_size for _, path in files) > MAX_EXPORT_BYTES:
        raise HTTPException(
            413, "This preparation pack exceeds 200 MB. Download evidence separately."
        )
    record = {
        "format_version": 1,
        "purpose": (
            "Preparation record. This is not a regulator submission, "
            "licence, certification or audit opinion."
        ),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "jurisdiction": jurisdiction,
        "owner": owner,
        "case": case_data,
        "evidence": [
            EvidenceResponse.model_validate(item).model_dump(mode="json") for item in evidence
        ],
    }
    csv_stream = io.StringIO(newline="")
    writer = csv.writer(csv_stream)
    writer.writerow(
        [
            "Section",
            "Reference",
            "Question",
            "Required",
            "Response",
            "Not applicable reason",
            "Accepted at",
            "Evidence IDs",
            "Reused from form",
        ]
    )
    responses = {row["field_key"]: row for row in case_data["responses"]}
    for field in case_data["fields"]:
        answer = responses.get(field["key"], {})
        row = [
            field["section"],
            field["key"],
            field["label"],
            field["required"],
            answer.get("value"),
            answer.get("not_applicable_reason"),
            answer.get("accepted_at"),
            "; ".join(answer.get("evidence_ids", [])),
            answer.get("reused_from_case_id"),
        ]
        writer.writerow([_csv_value(value) for value in row])
    payloads = {
        "preparation.json": json.dumps(record, indent=2, ensure_ascii=False).encode(),
        "responses.csv": csv_stream.getvalue().encode("utf-8-sig"),
    }
    output = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    manifest = {
        "format_version": 1,
        "case_id": case_data["id"],
        "case_revision": case_data["revision"],
        "files": [],
    }
    total_bytes = sum(len(content) for content in payloads.values())
    try:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in payloads.items():
                archive.writestr(name, content)
                manifest["files"].append(
                    {
                        "path": name,
                        "size_bytes": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                )
            for item, path in files:
                name = f"evidence/{item.id}/{clean_filename(item.filename)}"
                digest = hashlib.sha256()
                size = 0
                with path.open("rb") as source, archive.open(name, "w") as target:
                    while chunk := source.read(1024 * 1024):
                        size += len(chunk)
                        total_bytes += len(chunk)
                        if total_bytes > MAX_EXPORT_BYTES:
                            raise HTTPException(
                                413,
                                "Preparation pack exceeds 200 MB. Download evidence separately.",
                            )
                        digest.update(chunk)
                        target.write(chunk)
                if digest.hexdigest() != item.sha256 or size != item.size_bytes:
                    raise HTTPException(
                        409,
                        "Evidence has changed. Upload a verified copy before exporting.",
                    )
                manifest["files"].append(
                    {
                        "path": name,
                        "evidence_id": str(item.id),
                        "size_bytes": size,
                        "sha256": digest.hexdigest(),
                    }
                )
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        output.seek(0)
        return output
    except BaseException:
        output.close()
        raise
