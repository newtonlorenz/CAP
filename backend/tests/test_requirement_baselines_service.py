import uuid
from types import SimpleNamespace

import pytest

from app.services.requirement_baselines import (
    default_review_state_for_requirement,
    get_current_approved_version_for_document,
    load_requirements_for_versions,
)


@pytest.mark.parametrize(
    ("requirement_type", "expected"),
    [
        ("informational", ("confirmed", "Informational requirement - no action required")),
        ("not_applicable", ("confirmed", "Not applicable requirement - no action required")),
        ("mandatory", ("pending", None)),
    ],
)
def test_default_review_state_preserves_program_policy(requirement_type, expected):
    requirement = SimpleNamespace(requirement_type=requirement_type)

    assert (
        default_review_state_for_requirement(
            requirement,
            not_applicable_state=("confirmed", "Not applicable requirement - no action required"),
        )
        == expected
    )


def test_default_review_state_accepts_distinct_not_applicable_policy():
    requirement = SimpleNamespace(requirement_type="not_applicable")

    assert default_review_state_for_requirement(
        requirement,
        not_applicable_state=("pending", None),
    ) == ("pending", None)


@pytest.fixture
async def baseline_graph(db_session, default_jurisdiction):
    from app.models import Document, User
    from app.models.organization import Organization
    from app.models.program import RequirementSetVersion

    org = Organization(code="baseline-owner", name="Baseline owner")
    foreign = Organization(code="baseline-foreign", name="Foreign owner")
    db_session.add_all([org, foreign])
    await db_session.flush()
    user = User(
        email="baseline-fixture@example.test",
        full_name="Fixture",
        role="admin",
        password_hash="not-a-login",
        organization_id=org.id,
    )
    db_session.add(user)
    await db_session.flush()
    doc = Document(
        organization_id=org.id,
        jurisdiction_id=default_jurisdiction.id,
        filename="synthetic.pdf",
        file_path="/synthetic-not-read.pdf",
        document_type="standard",
        uploaded_by=user.id,
    )
    db_session.add(doc)
    await db_session.flush()
    versions = [
        RequirementSetVersion(
            document_id=doc.id,
            organization_id=org.id,
            version_number=i,
            status="approved" if i < 3 else "draft",
            is_current=i == 1,
            created_by=user.id,
        )
        for i in (1, 2, 3)
    ]
    db_session.add_all(versions)
    await db_session.commit()
    return org, foreign, doc, versions


async def test_approved_selection_prefers_current_then_latest_approved(db_session, baseline_graph):
    _, _, doc, versions = baseline_graph
    assert (await get_current_approved_version_for_document(db_session, doc.id)).id == versions[
        0
    ].id
    versions[0].is_current = False
    await db_session.commit()
    assert (await get_current_approved_version_for_document(db_session, doc.id)).id == versions[
        1
    ].id
    assert await get_current_approved_version_for_document(db_session, uuid.uuid4()) is None


async def test_requirement_loader_excludes_foreign_and_inactive_rows(
    db_session, default_jurisdiction, baseline_graph
):
    from app.models import Requirement

    org, foreign, doc, versions = baseline_graph
    rows = [
        Requirement(
            organization_id=owner,
            jurisdiction_id=default_jurisdiction.id,
            document_id=doc.id,
            requirement_set_version_id=versions[0].id,
            reference_id=f"fixture-{i}",
            text="Synthetic baseline",
            active=active,
        )
        for i, (owner, active) in enumerate(
            [(org.id, True), (foreign.id, True), (None, True), (org.id, False)]
        )
    ]
    db_session.add_all(rows)
    await db_session.commit()
    owned = await load_requirements_for_versions(
        db_session, default_jurisdiction.id, [versions[0].id], organization_id=org.id
    )
    legacy = await load_requirements_for_versions(
        db_session, default_jurisdiction.id, [versions[0].id], organization_id=None
    )
    assert [r.id for r in owned] == [rows[0].id]
    assert [r.id for r in legacy] == [rows[2].id]
    assert (
        await load_requirements_for_versions(
            db_session, default_jurisdiction.id, [], organization_id=org.id
        )
        == []
    )
