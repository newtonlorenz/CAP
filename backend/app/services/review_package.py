"""Portable completed-assessment handover, with verified evidence bytes."""

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

from fastapi import HTTPException

from app.config import settings
from app.services.review_assurance import frozen_payload, file_digest


async def build_review_package(db, cycle, user):
    from app.services.reports import (
        get_statement_of_applicability_fields,
        READABLE_SOA_FIELDS,
        generate_review_cycle_report_pdf,
        generate_statement_of_applicability_xlsx,
        generate_gap_analysis_xlsx,
    )

    payload = await frozen_payload(db, cycle)
    if payload is None:
        raise HTTPException(
            409,
            "Complete the review before downloading its frozen evidence package. Draft reports remain available.",
        )
    root = (Path(settings.upload_dir) / "review-snapshots" / str(cycle.snapshot_id)).resolve()
    total = 0
    verified = []
    for entry in payload["files"]:
        path = (root / entry["path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise HTTPException(
                409,
                "A frozen source or evidence file is missing. Restore the original file before exporting.",
            )
        total += path.stat().st_size
        if total > 512 * 1024 * 1024:
            raise HTTPException(
                413,
                "This package exceeds 512 MB. Contact the installation operator for an offline archive.",
            )
        with path.open("rb") as handle:
            digest = file_digest(handle)
        if digest != entry["sha256"]:
            raise HTTPException(
                409, "A frozen evidence file failed its integrity check. Export stopped."
            )
        verified.append((path, entry["path"]))
    exports = {
        "readiness-review.pdf": await generate_review_cycle_report_pdf(db, cycle),
        "statement-of-applicability.xlsx": await generate_statement_of_applicability_xlsx(
            db, cycle, get_statement_of_applicability_fields(READABLE_SOA_FIELDS)
        ),
        "gap-analysis.xlsx": await generate_gap_analysis_xlsx(
            db, user, cycle.id, cycle.jurisdiction_id
        ),
        "assessment.json": json.dumps(payload, indent=2).encode(),
        "README.txt": b"CAP completed readiness assessment. This package does not issue a certification or licence.\nCheck submission and approval requirements with the receiving authority or certification body.\nSource PDFs and evidence are included with SHA-256 checksums in manifest.json.\nAll applicability decisions are retained in assessment.json and the applicability workbook.\n",
    }
    manifest = {
        "review_id": str(cycle.id),
        "snapshot_id": str(cycle.snapshot_id),
        "closed_at": cycle.closed_at.isoformat(),
        "files": payload["files"]
        + [
            {"path": name, "sha256": hashlib.sha256(content).hexdigest(), "size": len(content)}
            for name, content in exports.items()
        ],
    }
    output = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    try:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, name in verified:
                archive.write(path, name)
            for name, content in exports.items():
                archive.writestr(name, content)
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        output.seek(0)
        return output
    except BaseException:
        output.close()
        raise
