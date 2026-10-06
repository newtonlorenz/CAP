"""API contracts for exact change scope, inherited privacy and pinned maintenance."""

import csv
import io
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models import (
    CertificationProject,
    CertificationProjectRequirementBaseline,
    Document,
    Requirement,
    RequirementSetVersion,
    User,
)
from app.models.access import AccessGrant
from app.models.change_management import ChangeEntry, ChangeRequirementImpact, ComponentRegister
from app.models.program import BaselineMigration, MaintenancePlan
from app.services.access import initialize_access
from app.services.auth import create_access_token


def headers(user):
    return {"Authorization": "Bearer " + create_access_token({"sub": str(user.id)})}


@pytest.fixture
async def linked_scope(db_session, default_jurisdiction):
    owner = User(
        email="linked-owner@example.test", password_hash="unused", full_name="Owner", role="manager"
    )
    other = User(
        email="linked-other@example.test", password_hash="unused", full_name="Other", role="manager"
    )
    db_session.add_all([owner, other])
    await db_session.flush()
    document = Document(
        jurisdiction_id=default_jurisdiction.id,
        uploaded_by=owner.id,
        name="Controls",
        document_type="generic",
        status="approved",
    )
    db_session.add(document)
    await db_session.flush()
    old = RequirementSetVersion(
        document_id=document.id, version_number=1, status="approved", created_by=owner.id
    )
    current = RequirementSetVersion(
        document_id=document.id,
        version_number=2,
        status="approved",
        is_current=True,
        created_by=owner.id,
    )
    project = CertificationProject(
        jurisdiction_id=default_jurisdiction.id, name="Private certification", created_by=owner.id
    )
    register = ComponentRegister(
        jurisdiction_id=default_jurisdiction.id, name="Register", created_by=owner.id
    )
    db_session.add_all([old, current, project, register])
    await db_session.flush()
    policy = await initialize_access(
        db_session, "certification_project", project.id, owner, "secret"
    )
    requirements = [
        Requirement(
            jurisdiction_id=default_jurisdiction.id,
            document_id=document.id,
            requirement_set_version_id=version.id,
            reference_id=ref,
            text=ref,
        )
        for version, ref in [(old, "1"), (old, "2"), (current, "3")]
    ]
    change = ChangeEntry(register_id=register.id, title="Platform change", proposed_by=owner.id)
    db_session.add_all(
        requirements
        + [
            change,
            CertificationProjectRequirementBaseline(
                project_id=project.id, document_id=document.id, requirement_set_version_id=old.id
            ),
        ]
    )
    await db_session.commit()
    return owner, other, document, old, current, project, change, requirements, policy


async def test_change_assessments_pin_selected_requirements_and_keep_project_contexts_separate(
    client,
    db_session,
    linked_scope,
):
    owner, _, doc, old, current, project, change, reqs, _ = linked_scope
    base = f"/api/v1/change-management/changes/{change.id}"
    response = await client.put(
        base + "/impacts",
        headers=headers(owner),
        json={
            "items": [
                {
                    "requirement_set_version_id": str(old.id),
                    "requirement_id": str(reqs[0].id),
                    "certification_project_id": str(project.id),
                    "rationale": "Check the affected control",
                },
                {"requirement_set_version_id": str(current.id)},
            ]
        },
    )
    assert response.status_code == 200, response.text
    impacts = response.json()["items"]
    response = await client.post(
        base + "/assessments",
        headers=headers(owner),
        json={
            "impact_ids": [item["id"] for item in impacts],
            "name": "Change assessment",
        },
    )
    assert response.status_code == 201, response.text
    cycles = response.json()["items"]
    assert len(cycles) == 2
    for cycle in cycles:
        assert cycle["change_entry_id"] == str(change.id)
        assert cycle["cycle_type"] == "change"
        detail = await client.get(f"/api/v1/review-cycles/{cycle['id']}", headers=headers(owner))
        assert detail.status_code == 200, detail.text
        expected = reqs[0] if cycle["certification_project_id"] else reqs[2]
        assert [item["requirement_id"] for item in detail.json()["items"]] == [str(expected.id)]
        assert cycle["baseline_versions"][0]["requirement_set_version_id"] == str(
            old.id if cycle["certification_project_id"] else current.id
        )
    for cycle in cycles:
        preview = await client.post(
            f"/api/v1/review-cycles/{cycle['id']}/baseline-migrations/preview",
            headers=headers(owner),
        )
        assert preview.status_code == 409
    project_cycle = next(cycle for cycle in cycles if cycle["certification_project_id"])
    migration_url = f"/api/v1/certification-projects/{project.id}/baseline-migrations"
    explicit = await client.post(
        migration_url + "/preview",
        headers=headers(owner),
        json={"from_cycle_id": project_cycle["id"]},
    )
    assert explicit.status_code == 409
    automatic = await client.post(migration_url + "/preview", headers=headers(owner), json={})
    assert automatic.status_code == 200, automatic.text
    assert automatic.json()["from_cycle_id"] is None
    # A stored preview created before this guard must also preserve the narrow assessment.
    legacy_preview = BaselineMigration(
        project_id=project.id,
        from_cycle_id=uuid.UUID(project_cycle["id"]),
        created_by=owner.id,
        preview_json=json.dumps(
            {
                "from_cycle_id": project_cycle["id"],
                "target_baselines": [
                    {"document_id": str(doc.id), "requirement_set_version_id": str(current.id)}
                ],
            }
        ),
    )
    db_session.add(legacy_preview)
    await db_session.commit()
    execution = await client.post(
        migration_url + "/execute",
        headers=headers(owner),
        json={"migration_id": str(legacy_preview.id)},
    )
    assert execution.status_code == 409
    preserved = (
        await client.get(f"/api/v1/review-cycles/{project_cycle['id']}", headers=headers(owner))
    ).json()
    assert preserved["status"] == "active"
    assert [item["requirement_id"] for item in preserved["items"]] == [str(reqs[0].id)]
    listed = await client.get(
        f"/api/v1/review-cycles?change_entry_id={change.id}", headers=headers(owner)
    )
    assert {c["id"] for c in listed.json()["items"]} == {c["id"] for c in cycles}
    change_view = (await client.get(base, headers=headers(owner))).json()
    assert {c["id"] for c in change_view["assessments"]} == {c["id"] for c in cycles}
    # A project-linked scope cannot silently adopt a different approved version.
    wrong = await client.put(
        base + "/impacts",
        headers=headers(owner),
        json={
            "items": [
                {
                    "requirement_set_version_id": str(current.id),
                    "certification_project_id": str(project.id),
                },
            ]
        },
    )
    assert wrong.status_code == 409
    mismatch = await client.put(
        base + "/impacts",
        headers=headers(owner),
        json={
            "items": [
                {"requirement_set_version_id": str(old.id), "requirement_id": str(reqs[2].id)},
            ]
        },
    )
    assert mismatch.status_code == 400
    draft = RequirementSetVersion(
        document_id=doc.id, version_number=3, status="draft", created_by=owner.id
    )
    db_session.add(draft)
    await db_session.commit()
    rejected = await client.put(
        base + "/impacts",
        headers=headers(owner),
        json={
            "items": [
                {"requirement_set_version_id": str(draft.id)},
            ]
        },
    )
    assert rejected.status_code == 409


async def test_change_links_do_not_disclose_or_replace_inaccessible_project_scope(
    client,
    db_session,
    linked_scope,
):
    owner, other, _, old, _, project, change, _, policy = linked_scope
    base = f"/api/v1/change-management/changes/{change.id}"
    created = await client.put(
        base + "/impacts",
        headers=headers(owner),
        json={
            "items": [
                {
                    "requirement_set_version_id": str(old.id),
                    "certification_project_id": str(project.id),
                    "rationale": "Private context",
                },
            ]
        },
    )
    impact_id = created.json()["items"][0]["id"]
    result = await client.post(
        base + "/assessments",
        headers=headers(owner),
        json={
            "impact_ids": [impact_id],
            "name": "Confidential assessment",
        },
    )
    cycle_id = result.json()["items"][0]["id"]
    assert (await client.get(base + "/impacts", headers=headers(other))).json() == {"items": []}
    assert (await client.get(base + "/assessments", headers=headers(other))).json() == {"items": []}
    assert (await client.get(base, headers=headers(other))).json()["assessments"] == []
    assert (
        await client.get(f"/api/v1/review-cycles/{cycle_id}", headers=headers(other))
    ).status_code == 404
    assert (
        await client.get(
            f"/api/v1/review-cycles?change_entry_id={change.id}", headers=headers(other)
        )
    ).json()["items"] == []
    assert (
        await client.put(base + "/impacts", headers=headers(other), json={"items": []})
    ).status_code == 200
    assert await db_session.get(ChangeRequirementImpact, uuid.UUID(impact_id)) is not None
    blocked = await client.post(
        base + "/assessments",
        headers=headers(other),
        json={
            "impact_ids": [impact_id],
            "name": "Try to copy private requirements",
        },
    )
    assert blocked.status_code in {403, 404}
    # Read access alone also cannot remove a visible project impact.
    db_session.add(
        AccessGrant(
            policy_id=policy.id, subject_type="user", subject_id=other.id, permission="view"
        )
    )
    await db_session.commit()
    assert len((await client.get(base + "/impacts", headers=headers(other))).json()["items"]) == 1
    assert (
        await client.put(base + "/impacts", headers=headers(other), json={"items": []})
    ).status_code == 200
    assert await db_session.get(ChangeRequirementImpact, uuid.UUID(impact_id)) is not None


async def test_project_maintenance_uses_pinned_versions_predecessors_and_edit_access(
    client,
    db_session,
    linked_scope,
):
    owner, other, _, old, current, project, _, _, _ = linked_scope
    body = {
        "certification_project_id": str(project.id),
        "jurisdiction_id": str(project.jurisdiction_id),
        "name": "Private recurring assessment",
        "cadence_days": 30,
        "next_run_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
    }
    denied = await client.post("/api/v1/maintenance-plans", headers=headers(other), json=body)
    assert denied.status_code in {403, 404}
    created = await client.post("/api/v1/maintenance-plans", headers=headers(owner), json=body)
    assert created.status_code == 201, created.text
    plan_id = created.json()["id"]
    assert (await client.get("/api/v1/maintenance-plans", headers=headers(other))).json()[
        "items"
    ] == []
    global_run = await client.post("/api/v1/maintenance-plans/run-due", headers=headers(other))
    assert global_run.json()["generated_cycles"] == 0
    assert (
        await client.post(
            f"/api/v1/maintenance-plans/run-due?certification_project_id={project.id}",
            headers=headers(other),
        )
    ).status_code in {403, 404}
    cycle_ids = []
    for _ in range(3):
        plan = await db_session.get(MaintenancePlan, uuid.UUID(plan_id))
        plan.next_run_at = datetime.now(timezone.utc) - timedelta(days=1)
        await db_session.commit()
        run = await client.post(
            f"/api/v1/maintenance-plans/run-due?certification_project_id={project.id}",
            headers=headers(owner),
        )
        assert run.status_code == 200, run.text
        assert run.json()["generated_cycles"] == 1
        events = (
            await client.get(
                f"/api/v1/maintenance-events?maintenance_plan_id={plan_id}", headers=headers(owner)
            )
        ).json()["items"]
        new_ids = {event["review_cycle_id"] for event in events} - set(cycle_ids)
        assert len(new_ids) == 1
        cycle_id = new_ids.pop()
        cycle = (
            await client.get(f"/api/v1/review-cycles/{cycle_id}", headers=headers(owner))
        ).json()
        assert cycle["certification_project_id"] == str(project.id)
        assert cycle["predecessor_cycle_id"] == (cycle_ids[-1] if cycle_ids else None)
        assert cycle["baseline_versions"][0]["requirement_set_version_id"] == str(old.id)
        cycle_ids.append(cycle_id)
    assert (
        await client.get(
            f"/api/v1/maintenance-events?maintenance_plan_id={plan_id}", headers=headers(other)
        )
    ).json()["items"] == []
    maintenance_preview = await client.post(
        f"/api/v1/certification-projects/{project.id}/baseline-migrations/preview",
        headers=headers(owner),
        json={"from_cycle_id": cycle_ids[-1]},
    )
    assert maintenance_preview.status_code == 409
    # The generic migration route must also preserve the project's pinned baseline.
    migration_url = f"/api/v1/review-cycles/{cycle_ids[-1]}/baseline-migrations"
    preview = await client.post(migration_url + "/preview", headers=headers(owner))
    execution = await client.post(
        migration_url + "/execute",
        headers=headers(owner),
        json={"target_version_ids": [str(current.id)]},
    )
    assert (preview.status_code, execution.status_code) == (409, 409)
    preserved = (
        await client.get(f"/api/v1/review-cycles/{cycle_ids[-1]}", headers=headers(owner))
    ).json()
    assert preserved["status"] == "active"
    assert preserved["baseline_versions"][0]["requirement_set_version_id"] == str(old.id)
    project_cycles = (
        await client.get(
            f"/api/v1/review-cycles?certification_project_id={project.id}", headers=headers(owner)
        )
    ).json()["items"]
    assert {cycle["id"] for cycle in project_cycles} == set(cycle_ids)
    export = await client.get("/api/v1/reports/audit-trail", headers=headers(other))
    assert export.status_code == 200
    rows = list(csv.DictReader(io.StringIO(export.text)))
    assert not any(
        row["Entity Type"] == "certification_project" and row["Entity ID"] == str(project.id)
        for row in rows
    )
    # An unscoped run may be visible, but must not expose protected plan counts.
    for row in rows:
        if row["Entity Type"] == "maintenance_cycle":
            assert not row["New Value"]
    unlink = await client.patch(
        f"/api/v1/maintenance-plans/{plan_id}",
        headers=headers(owner),
        json={"certification_project_id": None},
    )
    assert unlink.status_code == 409


def test_connected_assessment_migration_preserves_standalone_records(tmp_path):
    import importlib.util
    from pathlib import Path

    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path(__file__).parents[1] / "alembic/versions/p20260930_connected_assessments.py"
    spec = importlib.util.spec_from_file_location("connected_assessments_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'connected.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        for table in (
            "change_entries",
            "certification_projects",
            "requirement_set_versions",
            "requirements",
        ):
            connection.exec_driver_sql(f"CREATE TABLE {table} (id CHAR(32) PRIMARY KEY)")
        for table in ("review_cycles", "maintenance_plans"):
            connection.exec_driver_sql(
                f"CREATE TABLE {table} (id CHAR(32) PRIMARY KEY, name TEXT NOT NULL)"
            )
            connection.exec_driver_sql(f"INSERT INTO {table} VALUES ('original', 'Retained work')")
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert connection.exec_driver_sql(
            "SELECT name, change_entry_id FROM review_cycles"
        ).one() == ("Retained work", None)
        assert connection.exec_driver_sql(
            "SELECT name, certification_project_id FROM maintenance_plans"
        ).one() == ("Retained work", None)
        ids = [uuid.uuid4().hex for _ in range(4)]
        for table, ident in zip(
            (
                "change_entries",
                "certification_projects",
                "requirement_set_versions",
                "requirements",
            ),
            ids,
        ):
            connection.execute(sa.text(f"INSERT INTO {table} VALUES (:id)"), {"id": ident})
        connection.execute(
            sa.text(
                "INSERT INTO change_requirement_impacts VALUES (:id, :change, :version, :requirement, :project, 'Recorded impact')"
            ),
            {
                "id": uuid.uuid4().hex,
                "change": ids[0],
                "project": ids[1],
                "version": ids[2],
                "requirement": ids[3],
            },
        )
        migration.downgrade()
        for table in ("review_cycles", "maintenance_plans"):
            assert (
                connection.exec_driver_sql(f"SELECT name FROM {table}").scalar() == "Retained work"
            )
        migration.upgrade()
    engine.dispose()
