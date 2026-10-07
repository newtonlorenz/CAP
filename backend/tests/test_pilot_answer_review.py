"""Answer feedback lifecycle and coordination privacy boundaries."""

# ruff: noqa: F811
import uuid
from datetime import date, timedelta

from app.models.application import Application, ApplicationComponent
from app.models.preparation import PreparationCase
from app.services.access import initialize_access
from tests.test_preparation_api import actors, headers, make_case, make_template, BASE  # noqa: F401


async def saved_case(client, actors, default_jurisdiction, *, name="Answer review"):
    template = await make_template(client, actors["manager"])
    case = await make_case(
        client, actors["manager"], template["id"], default_jurisdiction.id, name=name
    )
    response = await client.put(
        f"{BASE}/cases/{case['id']}/responses/answer",
        headers=headers(actors["contributor"]),
        json={"expected_revision": case["revision"], "value": "Initial answer"},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_return_revision_resubmission_acceptance_retains_feedback(
    client, db_session, actors, default_jurisdiction
):
    case = await saved_case(client, actors, default_jurisdiction)
    url = f"{BASE}/cases/{case['id']}/responses/answer"
    for actor in ("reader", "contributor"):
        denied = await client.post(
            url + "/return",
            headers=headers(actors[actor]),
            json={"expected_revision": 2, "comment": "Fix this"},
        )
        assert denied.status_code == 403
    blank = await client.post(
        url + "/return",
        headers=headers(actors["manager"]),
        json={"expected_revision": 2, "comment": "   "},
    )
    assert blank.status_code == 422
    returned = await client.post(
        url + "/return",
        headers=headers(actors["manager"]),
        json={"expected_revision": 2, "comment": "Please attach the current policy"},
    )
    assert returned.status_code == 200, returned.text
    answer = returned.json()["responses"][0]
    assert answer["review_status"] == "changes_requested"
    assert answer["feedback"][0]["resolved_at"] is None
    assert (await client.get(f"{BASE}/review-queue", headers=headers(actors["manager"]))).json()[
        "total"
    ] == 0
    stale = await client.post(
        url + "/accept", headers=headers(actors["manager"]), json={"expected_revision": 2}
    )
    assert stale.status_code == 409
    revised = await client.put(
        url,
        headers=headers(actors["contributor"]),
        json={"expected_revision": 3, "value": "Current policy attached"},
    )
    assert revised.status_code == 200, revised.text
    assert revised.json()["responses"][0]["review_status"] == "pending_review"
    assert revised.json()["responses"][0]["feedback"][0]["resolved_at"] is None
    queue = (await client.get(f"{BASE}/review-queue", headers=headers(actors["manager"]))).json()
    assert queue["total"] == 1 and queue["items"][0]["open_feedback_count"] == 1
    accepted = await client.post(
        url + "/accept", headers=headers(actors["manager"]), json={"expected_revision": 4}
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["responses"][0]["feedback"][0]["resolved_by"] == str(
        actors["manager"].id
    )
    assert accepted.json()["responses"][0]["review_status"] == "accepted"
    assert (await client.get(f"{BASE}/review-queue", headers=headers(actors["manager"]))).json()[
        "total"
    ] == 0
    history = (await client.get(url + "/history", headers=headers(actors["manager"]))).json()[
        "items"
    ]
    assert {item["action"] for item in history} == {"update", "return_for_changes", "accept"}
    assert any(
        item["details"]["new_value"].get("comment") == "Please attach the current policy"
        for item in history
    )


async def test_assignment_never_grants_access_and_viewer_cannot_edit(
    client, db_session, actors, default_jurisdiction
):
    case = await saved_case(client, actors, default_jurisdiction)
    url = f"{BASE}/cases/{case['id']}"
    for ineligible in (actors["reader"], actors["contributor"], actors["other"]):
        result = await client.patch(
            url,
            headers=headers(actors["manager"]),
            json={"expected_revision": 2, "reviewer_id": str(ineligible.id)},
        )
        assert result.status_code == 422, result.text
    result = await client.patch(
        url,
        headers=headers(actors["manager"]),
        json={"expected_revision": 2, "reviewer_id": str(actors["manager"].id)},
    )
    assert result.status_code == 200, result.text
    assert result.json()["reviewer_name"] == "manager"
    assert result.json()["reviewer_source"] == "case"
    readonly = await client.get(f"{BASE}/review-queue", headers=headers(actors["reader"]))
    assert readonly.json()["items"][0]["can_approve"] is False
    assert (
        await client.put(
            url + "/responses/answer",
            headers=headers(actors["reader"]),
            json={"expected_revision": 3, "value": "No"},
        )
    ).status_code == 403
    record = await db_session.get(PreparationCase, uuid.UUID(case["id"]))
    record.reviewer_id = actors["other"].id
    await db_session.commit()
    assert (await client.get(url, headers=headers(actors["manager"]))).json()["reviewer_id"] is None
    assert (await client.get(url, headers=headers(actors["other"]))).status_code == 404


async def test_queues_scope_before_counts_pagination_and_excluded_optional(
    client, db_session, actors, default_jurisdiction
):
    visible = await saved_case(client, actors, default_jurisdiction)
    second = await saved_case(client, actors, default_jurisdiction, name="Second visible")
    await saved_case(
        client,
        {**actors, "manager": actors["other"], "contributor": actors["other"]},
        default_jurisdiction,
        name="Other org",
    )
    case = await db_session.get(PreparationCase, uuid.UUID(second["id"]))
    case.due_date = date.today() - timedelta(days=1)
    application = Application(
        organization_id=actors["manager"].organization_id,
        jurisdiction_id=default_jurisdiction.id,
        name="Visible pack",
        scope="new",
        created_by=actors["manager"].id,
    )
    db_session.add(application)
    await db_session.flush()
    await initialize_access(
        db_session, "application", application.id, actors["manager"], "organisation"
    )
    db_session.add(
        ApplicationComponent(
            application_id=application.id,
            name="Excluded optional form",
            kind="form",
            required=False,
            included=False,
            case_id=uuid.UUID(visible["id"]),
        )
    )
    await db_session.commit()
    response = await client.get(
        f"{BASE}/review-queue?limit=1&overdue=true&unassigned=true",
        headers=headers(actors["manager"]),
    )
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1 and response.json()["items"][0]["case_id"] == second["id"]
    explicit = await client.get(
        f"{BASE}/review-queue?limit=1&include_excluded=true", headers=headers(actors["manager"])
    )
    assert explicit.json()["total"] == 2 and len(explicit.json()["items"]) == 1
    team = await client.get(
        "/api/v1/dashboard/team-work?limit=1", headers=headers(actors["manager"])
    )
    assert team.status_code == 200, team.text
    assert team.json()["total"] == 1
    assert team.json()["counts"]["unassigned"] == 1
    assert team.json()["counts"]["overdue"] == 1
    assert team.json()["contexts"] == ["Second visible"]
    assert (
        await client.get("/api/v1/dashboard/team-work", headers=headers(actors["reader"]))
    ).status_code == 403


async def test_same_org_private_records_and_role_plus_approve_access(
    client, db_session, actors, default_jurisdiction
):
    from app.models import User
    from app.models.access import AccessGrant
    from app.services.access import get_policy

    manager = actors["manager"]
    peer = User(
        email="private-manager@example.test",
        full_name="Private manager",
        password_hash="unused",
        role="manager",
        organization_id=manager.organization_id,
        active=True,
    )
    db_session.add(peer)
    await db_session.commit()
    template = await make_template(client, peer)
    result = await client.post(
        f"{BASE}/cases",
        headers=headers(peer),
        json={
            "template_id": template["id"],
            "jurisdiction_id": str(default_jurisdiction.id),
            "name": "Hidden case",
            "visibility": "secret",
        },
    )
    assert result.status_code == 201, result.text
    case = result.json()
    url = f"{BASE}/cases/{case['id']}"
    assert (
        await client.put(
            url + "/responses/answer",
            headers=headers(peer),
            json={"expected_revision": 1, "value": "Confidential"},
        )
    ).status_code == 200
    assert (await client.get(f"{BASE}/review-queue", headers=headers(manager))).json()["total"] == 0
    team = (await client.get("/api/v1/dashboard/team-work", headers=headers(manager))).json()
    assert team["total"] == 0 and team["counts"]["total"] == 0 and team["contexts"] == []
    assert (
        await client.post(
            url + "/responses/answer/return",
            headers=headers(manager),
            json={"expected_revision": 2, "comment": "No"},
        )
    ).status_code == 404
    assert (
        await client.patch(
            url,
            headers=headers(peer),
            json={"expected_revision": 2, "reviewer_id": str(manager.id)},
        )
    ).status_code == 422
    policy = await get_policy(db_session, "preparation_case", uuid.UUID(case["id"]))
    # A manager with view but no approve permission cannot decide.
    db_session.add(
        AccessGrant(
            policy_id=policy.id, subject_type="user", subject_id=manager.id, permission="view"
        )
    )
    # A viewer explicitly granted approve still cannot bypass account-role limits.
    for permission in ("view", "edit", "approve"):
        db_session.add(
            AccessGrant(
                policy_id=policy.id,
                subject_type="user",
                subject_id=actors["reader"].id,
                permission=permission,
            )
        )
    await db_session.commit()
    assert (await client.get(f"{BASE}/review-queue", headers=headers(manager))).json()["items"][0][
        "can_approve"
    ] is False
    assert (
        await client.post(
            url + "/responses/answer/accept",
            headers=headers(manager),
            json={"expected_revision": 2},
        )
    ).status_code == 404
    assert (
        await client.post(
            url + "/responses/answer/return",
            headers=headers(actors["reader"]),
            json={"expected_revision": 2, "comment": "No"},
        )
    ).status_code == 403


async def test_team_uses_real_mixed_work_and_hides_private_project_reviews(
    client, db_session, actors, default_jurisdiction
):
    from app.models import Requirement, ReviewCycle, ReviewItem
    from app.models.application import ApplicationFollowup
    from app.models.change_management import ChangeEntry, ComponentRegister
    from app.models.program import CertificationProject

    manager = actors["manager"]
    contributor = actors["contributor"]
    org = manager.organization_id
    market = default_jurisdiction.id
    req = Requirement(
        organization_id=org,
        jurisdiction_id=market,
        reference_id="R-1",
        title="Evidence policy",
        text="Supply evidence",
    )
    application = Application(
        organization_id=org,
        jurisdiction_id=market,
        name="Actual pack",
        scope="new",
        created_by=manager.id,
    )
    register = ComponentRegister(
        organization_id=org, jurisdiction_id=market, name="Actual programme", created_by=manager.id
    )
    project = CertificationProject(
        organization_id=org,
        jurisdiction_id=market,
        name="Hidden project",
        created_by=contributor.id,
    )
    db_session.add_all([req, application, register, project])
    await db_session.flush()
    await initialize_access(db_session, "certification_project", project.id, contributor, "secret")
    cycle = ReviewCycle(
        organization_id=org, jurisdiction_id=market, name="Visible review", created_by=manager.id
    )
    private_cycle = ReviewCycle(
        organization_id=org,
        jurisdiction_id=market,
        name="Hidden review",
        certification_project_id=project.id,
        created_by=contributor.id,
    )
    db_session.add_all([cycle, private_cycle])
    await db_session.flush()
    db_session.add_all(
        [
            ReviewItem(
                review_cycle_id=cycle.id,
                requirement_id=req.id,
                assigned_reviewer_id=manager.id,
                assessment_status="evidenced",
            ),
            ReviewItem(
                review_cycle_id=private_cycle.id,
                requirement_id=req.id,
                assigned_reviewer_id=manager.id,
            ),
            ApplicationFollowup(
                application_id=application.id, question="Current policy?", owner_id=contributor.id
            ),
            ChangeEntry(register_id=register.id, title="Actual change", proposed_by=manager.id),
        ]
    )
    await db_session.commit()
    response = await client.get("/api/v1/dashboard/team-work?limit=1", headers=headers(manager))
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["total"] == 4 and len(page["items"]) == 1
    assert page["counts"]["by_kind"]["review"] == 1
    assert page["counts"]["by_kind"]["requirement"] == 1
    assert page["counts"]["by_kind"]["authority_query"] == 1
    assert page["counts"]["by_kind"]["change"] == 1
    assert "Hidden review" not in page["contexts"]
    changes = (
        await client.get(
            "/api/v1/dashboard/team-work?kind=change&context=Actual%20programme",
            headers=headers(manager),
        )
    ).json()
    assert changes["total"] == 1 and changes["items"][0]["owner_id"] is None
    assert changes["items"][0]["action_label"]


async def test_inaccessible_original_does_not_break_unrelated_queues(
    client, db_session, actors, default_jurisdiction
):
    import json
    from app.models.preparation import PreparationEvidence

    hidden = await saved_case(
        client, actors, default_jurisdiction, name="Original protected separately"
    )
    visible = await saved_case(
        client, actors, default_jurisdiction, name="Unrelated visible answer"
    )
    contributor = actors["contributor"]
    evidence = PreparationEvidence(
        organization_id=contributor.organization_id,
        title="Private original",
        kind="note",
        body="Private",
        created_by=contributor.id,
    )
    db_session.add(evidence)
    await db_session.flush()
    await initialize_access(db_session, "preparation_evidence", evidence.id, contributor, "secret")
    case = await db_session.get(PreparationCase, uuid.UUID(hidden["id"]))
    case.original_evidence_ids_json = json.dumps([str(evidence.id)])
    await db_session.commit()
    assert (
        await client.get(f"{BASE}/cases/{hidden['id']}", headers=headers(actors["manager"]))
    ).status_code == 403
    queue = await client.get(f"{BASE}/review-queue", headers=headers(actors["manager"]))
    assert queue.status_code == 200, queue.text
    assert queue.json()["total"] == 1 and queue.json()["items"][0]["case_id"] == visible["id"]
    team = await client.get("/api/v1/dashboard/team-work", headers=headers(actors["manager"]))
    assert team.status_code == 200, team.text
    assert team.json()["total"] == 1 and team.json()["items"][0]["case_id"] == visible["id"]


async def test_context_upload_uses_form_access_for_distinct_contributor_and_reviewer(
    client, db_session, actors, default_jurisdiction
):
    from app.models.access import AccessGrant
    from app.services.access import get_policy

    manager, contributor = actors["manager"], actors["contributor"]
    form = await make_template(client, manager)
    created = await client.post(
        f"{BASE}/cases",
        headers=headers(manager),
        json={
            "name": "Restricted form",
            "template_id": form["id"],
            "visibility": "secret",
            "jurisdiction_id": str(default_jurisdiction.id),
            "reviewer_id": str(manager.id),
            "owner_id": str(contributor.id),
        },
    )
    assert created.status_code == 201, created.text
    case = created.json()
    policy = await get_policy(db_session, "preparation_case", uuid.UUID(case["id"]))
    for permission in ("view", "edit", "export"):
        db_session.add(
            AccessGrant(
                policy_id=policy.id,
                subject_type="user",
                subject_id=contributor.id,
                permission=permission,
            )
        )
    await db_session.commit()
    upload = await client.post(
        f"{BASE}/evidence/upload",
        headers=headers(contributor),
        data={"title": "Contributor policy", "case_id": case["id"], "visibility": "secret"},
        files={"file": ("policy.txt", b"Policy uploaded by a distinct contributor", "text/plain")},
    )
    assert upload.status_code == 201, upload.text
    evidence = upload.json()
    # Existing case manager can see/download the new evidence; unrelated same-org reader cannot.
    assert (
        await client.get(f"{BASE}/evidence/{evidence['id']}/download", headers=headers(manager))
    ).status_code == 200
    for actor in ("reader", "other"):
        assert (
            await client.get(f"{BASE}/evidence/{evidence['id']}", headers=headers(actors[actor]))
        ).status_code == 404
    saved = await client.put(
        f"{BASE}/cases/{case['id']}/responses/answer",
        headers=headers(contributor),
        json={"expected_revision": 1, "value": "Policy revised", "evidence_ids": [evidence["id"]]},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["reviewer_id"] == str(manager.id)
    queue = await client.get(f"{BASE}/review-queue", headers=headers(manager))
    assert queue.status_code == 200 and queue.json()["total"] == 1
    accepted = await client.post(
        f"{BASE}/cases/{case['id']}/responses/answer/accept",
        headers=headers(manager),
        json={"expected_revision": 2},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["responses"][0]["accepted_by"] == str(manager.id)
    assert (await client.get(f"{BASE}/review-queue", headers=headers(actors["reader"]))).json()[
        "total"
    ] == 0


async def test_changed_evidence_filter_uses_saved_audit_revisions(
    client, actors, default_jurisdiction
):
    case = await saved_case(client, actors, default_jurisdiction)
    manager = actors["manager"]
    initial = (await client.get(f"{BASE}/review-queue", headers=headers(manager))).json()
    assert initial["items"][0]["change_kind"] == "new_answer"
    assert (
        await client.get(f"{BASE}/review-queue?changed_evidence=true", headers=headers(manager))
    ).json()["total"] == 0
    evidence = await client.post(
        f"{BASE}/evidence",
        headers=headers(manager),
        json={
            "title": "Current policy",
            "kind": "note",
            "body": "Revised evidence",
            "visibility": "organisation",
        },
    )
    assert evidence.status_code == 201, evidence.text
    updated = await client.put(
        f"{BASE}/cases/{case['id']}/responses/answer",
        headers=headers(manager),
        json={
            "expected_revision": 2,
            "value": "Initial answer",
            "evidence_ids": [evidence.json()["id"]],
        },
    )
    assert updated.status_code == 200, updated.text
    changed = (
        await client.get(
            f"{BASE}/review-queue?changed_evidence=true&limit=1", headers=headers(manager)
        )
    ).json()
    assert changed["total"] == 1 and changed["items"][0]["change_kind"] == "evidence_changed"
    await client.put(
        f"{BASE}/cases/{case['id']}/responses/answer",
        headers=headers(manager),
        json={
            "expected_revision": 3,
            "value": "Updated explanation",
            "evidence_ids": [evidence.json()["id"]],
        },
    )
    assert (
        await client.get(f"{BASE}/review-queue?changed_evidence=true", headers=headers(manager))
    ).json()["total"] == 0
    assert (await client.get(f"{BASE}/review-queue", headers=headers(manager))).json()["items"][0][
        "change_kind"
    ] == "answer_updated"


async def test_team_sorting_spans_pages_and_priority_remains_default(
    client, db_session, actors, default_jurisdiction
):
    from app.models.application import ApplicationFollowup

    manager = actors["manager"]
    for name, owner_id, days in [
        ("Zulu programme", manager.id, 1),
        ("Alpha programme", actors["contributor"].id, 3),
        ("Middle programme", None, 2),
    ]:
        pack = Application(
            organization_id=manager.organization_id,
            jurisdiction_id=default_jurisdiction.id,
            name=name,
            scope="new",
            created_by=manager.id,
        )
        db_session.add(pack)
        await db_session.flush()
        db_session.add(
            ApplicationFollowup(
                application_id=pack.id,
                question=f"Query {name}",
                owner_id=owner_id,
                due_date=date.today() + timedelta(days=days),
            )
        )
    await db_session.commit()
    base = "/api/v1/dashboard/team-work?kind=authority_query&limit=1"
    expected = {
        "priority": ["Zulu programme", "Middle programme", "Alpha programme"],
        "programme": ["Alpha programme", "Middle programme", "Zulu programme"],
        "owner": ["Alpha programme", "Zulu programme", "Middle programme"],
    }
    for sort_by, contexts in expected.items():
        for skip, context in enumerate(contexts):
            result = await client.get(
                f"{base}&sort_by={sort_by}&skip={skip}", headers=headers(manager)
            )
            assert result.status_code == 200, result.text
            assert result.json()["total"] == 3
            assert result.json()["items"][0]["context"] == context
    default = (await client.get(base, headers=headers(manager))).json()
    assert default["items"][0]["context"] == "Zulu programme"
    assert any(
        person["id"] is None and person["name"] == "Unassigned" for person in default["people"]
    )
    unassigned = (await client.get(base + "&unassigned=true", headers=headers(manager))).json()
    assert unassigned["total"] == 1 and unassigned["items"][0]["owner_id"] is None
    assert (
        await client.get(base + "&sort_by=unknown", headers=headers(manager))
    ).status_code == 422


async def test_context_upload_materialises_legacy_pack_form_policy_without_changing_owner(
    client, db_session, actors, default_jurisdiction
):
    import json
    from app.services.access import get_policy

    manager, contributor = actors["manager"], actors["contributor"]
    case = PreparationCase(
        organization_id=manager.organization_id,
        jurisdiction_id=default_jurisdiction.id,
        created_by=manager.id,
        name="Legacy pack-generated form",
        kind="questionnaire",
        template_name="Legacy",
        template_revision=1,
        fields_json=json.dumps([{"key": "answer", "label": "Answer", "type": "text"}]),
    )
    db_session.add(case)
    await db_session.commit()
    assert await get_policy(db_session, "preparation_case", case.id) is None
    upload = await client.post(
        f"{BASE}/evidence/upload",
        headers=headers(contributor),
        data={"title": "Legacy-context policy", "case_id": str(case.id)},
        files={"file": ("policy.txt", b"Legacy form contributor evidence", "text/plain")},
    )
    assert upload.status_code == 201, upload.text
    policy = await get_policy(db_session, "preparation_case", case.id)
    assert policy.owner_id == manager.id and policy.visibility == "organisation"
    evidence = upload.json()
    assert (
        await client.get(f"{BASE}/evidence/{evidence['id']}", headers=headers(manager))
    ).status_code == 200
    contributor_form = (
        await client.get(f"{BASE}/cases/{case.id}", headers=headers(contributor))
    ).json()
    assert "edit" in contributor_form["access"]["permissions"]
    assert "manage_access" not in contributor_form["access"]["permissions"]
    # Narrowing the existing form later automatically narrows the uploaded file.
    policy.visibility = "secret"
    await db_session.commit()
    assert (
        await client.get(f"{BASE}/evidence/{evidence['id']}", headers=headers(contributor))
    ).status_code == 404
    assert (
        await client.get(f"{BASE}/evidence/{evidence['id']}", headers=headers(manager))
    ).status_code == 200
