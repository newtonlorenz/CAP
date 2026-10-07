"""Concurrent answer decisions must fence the same form revision on PostgreSQL."""

import asyncio
import json
import os
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.preparation import accept_response, return_response
from app.models import AuditLog, Jurisdiction, Organization, User
from app.models.preparation import PreparationCase, PreparationResponse, PreparationReviewFeedback
from app.schemas.preparation import ReturnResponseRequest, RevisionRequest


@pytest.mark.skipif(not os.getenv("CAP_TEST_POSTGRES_URL"), reason="Isolated PostgreSQL required")
async def test_concurrent_accept_and_return_only_one_decision_commits():
    url = make_url(os.environ["CAP_TEST_POSTGRES_URL"])
    assert url.host == "127.0.0.1" and (url.port, url.database) == (25489, "cap_e2e")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    fixtures = []
    try:
        async with sessions() as db:
            key = uuid.uuid4().hex[:10]
            org = Organization(code=key, name="Disposable answer review concurrency fixture")
            market = Jurisdiction(code=key, name="Disposable market")
            db.add_all([org, market])
            await db.flush()
            manager = User(
                email=f"{key}@example.test",
                password_hash="not-a-login",
                full_name="Manager",
                role="manager",
                organization_id=org.id,
            )
            db.add(manager)
            await db.flush()
            case = PreparationCase(
                organization_id=org.id,
                jurisdiction_id=market.id,
                name="Concurrent answer",
                template_name="Private form",
                template_revision=1,
                kind="questionnaire",
                fields_json=json.dumps([{"key": "answer", "label": "Answer", "type": "text"}]),
                created_by=manager.id,
            )
            db.add(case)
            await db.flush()
            answer = PreparationResponse(
                case_id=case.id, field_key="answer", value_json=json.dumps("Exact revision")
            )
            db.add(answer)
            await db.commit()
            fixtures = [
                (PreparationReviewFeedback, PreparationReviewFeedback.response_id, answer.id),
                (AuditLog, AuditLog.organization_id, org.id),
                (PreparationResponse, PreparationResponse.id, answer.id),
                (PreparationCase, PreparationCase.id, case.id),
                (User, User.id, manager.id),
                (Jurisdiction, Jurisdiction.id, market.id),
                (Organization, Organization.id, org.id),
            ]

        async def decide(accept):
            async with sessions() as db:
                user = await db.get(User, manager.id)
                try:
                    result = await (
                        accept_response(
                            case.id, "answer", RevisionRequest(expected_revision=1), db, user
                        )
                        if accept
                        else return_response(
                            case.id,
                            "answer",
                            ReturnResponseRequest(
                                expected_revision=1, comment="Current evidence needed"
                            ),
                            db,
                            user,
                        )
                    )
                    return result.revision
                except HTTPException as error:
                    await db.rollback()
                    return error.status_code

        results = await asyncio.gather(decide(True), decide(False))
        assert sorted(results) == [2, 409]
        async with sessions() as db:
            events = (
                await db.scalars(select(AuditLog).where(AuditLog.organization_id == org.id))
            ).all()
            assert len(events) == 1
            saved = await db.get(PreparationResponse, answer.id)
            assert (saved.accepted_at is not None) == (events[0].action == "accept")
            assert (await db.get(PreparationCase, case.id)).revision == 2
    finally:
        async with sessions() as db:
            for model, column, identity in fixtures:
                await db.execute(delete(model).where(column == identity))
            await db.commit()
        await engine.dispose()
