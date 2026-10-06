"""Synthetic data and content fingerprints for the disposable image rehearsal."""

import asyncio
import hashlib
import json
import sys
from pathlib import Path

from app.config import settings
from app.database import async_session
from app.models import Jurisdiction, Requirement, ReviewCycle, ReviewItem, User
from app.models.review import ReviewItemComment, ReviewItemEvidenceFile
from sqlalchemy import select, text


async def seed():
    async with async_session() as db:
        user = (await db.execute(select(User))).scalar_one()
        jurisdiction = Jurisdiction(code="rehearsal", name="Synthetic release rehearsal")
        db.add(jurisdiction)
        await db.flush()
        requirement = Requirement(
            organization_id=user.organization_id, jurisdiction_id=jurisdiction.id,
            reference_id="1.1", text="The system shall retain synthetic audit evidence.",
        )
        cycle = ReviewCycle(
            organization_id=user.organization_id, jurisdiction_id=jurisdiction.id,
            name="Synthetic review", created_by=user.id,
        )
        db.add_all([requirement, cycle])
        await db.flush()
        item = ReviewItem(
            review_cycle_id=cycle.id, requirement_id=requirement.id,
            reviewer_id=user.id, review_status="confirmed", assessment_status="evidenced",
            review_evidence="Synthetic evidence retained through upgrade and restore.",
        )
        db.add(item)
        await db.flush()
        evidence = Path(settings.upload_dir) / "release-rehearsal.txt"
        evidence.write_text("Synthetic CAP release evidence.\n")
        db.add_all([
            ReviewItemComment(review_item_id=item.id, author_id=user.id, body="Synthetic review comment."),
            ReviewItemEvidenceFile(
                review_item_id=item.id, filename=evidence.name, file_path=str(evidence), uploaded_by=user.id,
            ),
        ])
        await db.commit()


async def fingerprint():
    tables = {}
    async with async_session() as db:
        names = (await db.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        ))).scalars()
        for name in names:
            if name == "alembic_version":
                continue
            # Names come from pg_catalog, and quote escaping protects unusual identifiers.
            quoted = '"' + name.replace('"', '""') + '"'
            result = await db.execute(text(f"SELECT * FROM {quoted}"))
            tables[name] = {
                "columns": list(result.keys()),
                "rows": [list(row) for row in result.fetchall()],
            }
    root = Path(settings.upload_dir)
    backup_root = Path(settings.backup_dir).resolve()
    uploads = {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and not path.resolve().is_relative_to(backup_root)
    }
    print(json.dumps({"tables": tables, "uploads": uploads}, default=str, sort_keys=True))


if __name__ == "__main__":
    if sys.argv[1] == "seed":
        asyncio.run(seed())
    elif sys.argv[1] == "fingerprint":
        asyncio.run(fingerprint())
    elif sys.argv[1] == "backup":
        from app.services.backups import create_backup
        print(json.dumps(create_backup(
            reason="Synthetic release rehearsal", created_by_user_id=None, created_by_user_name=None,
        )))
    else:
        raise SystemExit("Expected seed, fingerprint or backup")
