"""Execute the production audit predicate on PostgreSQL, including its planner.

SQLite privacy tests cannot detect pathological PostgreSQL query planning. Use
only the explicitly selected disposable database; fixture writes roll back.
"""

import json
import os
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models import AuditLog, Organization, PreparationEvidence, User
from app.models.access import AccessGrant
from app.models.application import Application
from app.models.jurisdiction import Jurisdiction
from app.services.access import initialize_access, protect_child
from app.services.access_audit import audit_access_clause


@pytest.mark.skipif(not os.getenv("CAP_TEST_POSTGRES_URL"), reason="Isolated PostgreSQL required")
async def test_audit_query_executes_with_postgres_planner_and_filters_private_descendants():
    url = make_url(os.environ["CAP_TEST_POSTGRES_URL"])
    assert url.host == "127.0.0.1" and (url.port, url.database) == (25489, "cap_e2e")
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                async with AsyncSession(bind=connection, expire_on_commit=False) as db:
                    await db.execute(text("SET LOCAL statement_timeout = '5s'"))
                    key = uuid.uuid4().hex[:12]
                    org = Organization(code=key, name="Disposable audit privacy test")
                    jurisdiction = Jurisdiction(code=key, name="Disposable jurisdiction")
                    db.add_all([org, jurisdiction])
                    await db.flush()
                    owner = User(
                        email=f"owner-{key}@example.test",
                        full_name="Owner",
                        password_hash="unused",
                        role="admin",
                        active=True,
                        organization_id=org.id,
                    )
                    admin = User(
                        email=f"admin-{key}@example.test",
                        full_name="Account admin",
                        password_hash="unused",
                        role="admin",
                        active=True,
                        organization_id=org.id,
                    )
                    db.add_all([owner, admin])
                    await db.flush()
                    app = Application(
                        name="Private application",
                        scope="full_pack",
                        organization_id=org.id,
                        jurisdiction_id=jurisdiction.id,
                        created_by=owner.id,
                    )
                    evidence = PreparationEvidence(
                        title="Private document",
                        kind="note",
                        body="Restricted content",
                        organization_id=org.id,
                        created_by=owner.id,
                    )
                    db.add_all([app, evidence])
                    await db.flush()
                    app_policy = await initialize_access(db, "application", app.id, owner)
                    evidence_policy = await initialize_access(
                        db, "preparation_evidence", evidence.id, owner
                    )
                    await protect_child(
                        db, "application", app.id, "preparation_evidence", evidence.id, owner
                    )
                    db.add(
                        AccessGrant(
                            policy_id=app_policy.id,
                            subject_type="user",
                            subject_id=admin.id,
                            permission="view",
                        )
                    )
                    event = AuditLog(
                        organization_id=org.id,
                        user_id=owner.id,
                        user_name=owner.full_name,
                        action="add_component",
                        entity_type="application",
                        entity_id=str(app.id),
                        new_value=json.dumps(
                            {"name": "Private document", "evidence_id": str(evidence.id)}
                        ),
                    )
                    db.add(event)
                    await db.flush()
                    query = select(AuditLog).where(
                        AuditLog.organization_id == org.id, audit_access_clause(admin)
                    )
                    assert await db.scalar(select(func.count()).select_from(query.subquery())) == 0
                    assert (
                        list(
                            (
                                await db.scalars(
                                    query.order_by(AuditLog.timestamp.desc()).limit(15)
                                )
                            ).all()
                        )
                        == []
                    )
                    db.add(
                        AccessGrant(
                            policy_id=evidence_policy.id,
                            subject_type="user",
                            subject_id=admin.id,
                            permission="view",
                        )
                    )
                    await db.flush()
                    assert list(
                        (
                            await db.scalars(query.order_by(AuditLog.timestamp.desc()).limit(15))
                        ).all()
                    ) == [event]
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
