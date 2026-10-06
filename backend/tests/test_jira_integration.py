import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from app.models import JiraIntegration, Organization, Requirement, ReviewCycle, ReviewItem, User
from app.models.document import Document
from app.models.program import RequirementSetVersion
from app.services.auth import create_access_token, hash_password
from app.services.jira import (
    JiraIssueData,
    JiraServiceError,
    encrypt_token,
    fetch_jira_issues,
    get_jira_integration,
    normalize_jira_base_url,
)


@pytest.fixture
async def jira_organization(db_session):
    organization = Organization(code="jira-test", name="Jira Test")
    db_session.add(organization)
    await db_session.commit()
    return organization


@pytest.fixture
async def admin_user(db_session, jira_organization):
    user = User(
        organization_id=jira_organization.id,
        email="admin@example.com",
        password_hash=hash_password("adminpass"),
        full_name="Admin User",
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def contributor_user(db_session, jira_organization):
    user = User(
        organization_id=jira_organization.id,
        email="contrib@example.com",
        password_hash=hash_password("contribpass"),
        full_name="Contributor User",
        role="contributor",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def assigned_reviewer_user(db_session, jira_organization):
    user = User(
        organization_id=jira_organization.id,
        email="reviewer@example.com",
        password_hash=hash_password("reviewerpass"),
        full_name="Assigned Reviewer",
        role="assigned_reviewer",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def admin_headers(admin_user):
    token = create_access_token({"sub": str(admin_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def contributor_headers(contributor_user):
    token = create_access_token({"sub": str(contributor_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def assigned_reviewer_headers(assigned_reviewer_user):
    token = create_access_token({"sub": str(assigned_reviewer_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def test_requirement(db_session, admin_user, default_jurisdiction):
    document = Document(
        organization_id=admin_user.organization_id,
        jurisdiction_id=default_jurisdiction.id,
        filename="jira-set.pdf",
        name="Jira set",
        document_type="scp",
        version="1",
        status="approved",
        file_path="/tmp/jira-set.pdf",
        uploaded_by=admin_user.id,
        approved_by=admin_user.id,
    )
    db_session.add(document)
    await db_session.flush()

    version = RequirementSetVersion(
        organization_id=admin_user.organization_id,
        document_id=document.id,
        version_number=1,
        status="approved",
        is_current=True,
        created_by=admin_user.id,
        approved_by=admin_user.id,
        approved_at=datetime.now(timezone.utc),
        locked_at=datetime.now(timezone.utc),
    )
    db_session.add(version)
    await db_session.flush()

    req = Requirement(
        organization_id=admin_user.organization_id,
        jurisdiction_id=default_jurisdiction.id,
        document_id=document.id,
        requirement_set_version_id=version.id,
        reference_id="REQ-001",
        text="Test requirement",
        requirement_type="mandatory",
        active=True,
        version=1,
        sort_order=0,
    )
    db_session.add(req)
    await db_session.commit()
    await db_session.refresh(req)
    return req


async def _create_cycle_and_item(client, admin_headers, default_jurisdiction, db_session):
    response = await client.post(
        "/api/v1/review-cycles",
        headers=admin_headers,
        json={
            "name": "Jira Cycle",
            "jurisdiction_id": str(default_jurisdiction.id),
            "scope": "all",
        },
    )
    assert response.status_code == 201
    cycle_id = uuid.UUID(response.json()["id"])

    result = await db_session.execute(
        select(ReviewItem).where(ReviewItem.review_cycle_id == cycle_id)
    )
    item = result.scalar_one()
    return cycle_id, item


async def test_admin_can_configure_jira_integration(client, admin_headers, db_session):
    response = await client.put(
        "/api/v1/integrations/jira",
        headers=admin_headers,
        json={
            "base_url": "https://example.atlassian.net",
            "project_key": "PROJ",
            "user_email": "jira@example.com",
            "api_token": "top-secret-token",
            "enabled": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["base_url"] == "https://example.atlassian.net"
    assert data["project_key"] == "PROJ"
    assert data["user_email"] == "jira@example.com"
    assert data["token_configured"] is True
    assert "api_token" not in data

    get_response = await client.get("/api/v1/integrations/jira", headers=admin_headers)
    assert get_response.status_code == 200
    get_data = get_response.json()
    assert get_data["configured"] is True
    assert get_data["integration"]["token_configured"] is True

    result = await db_session.execute(select(JiraIntegration))
    integration = result.scalar_one()
    assert integration.api_token_encrypted != "top-secret-token"


async def test_non_admin_cannot_configure_jira_integration(client, contributor_headers):
    response = await client.put(
        "/api/v1/integrations/jira",
        headers=contributor_headers,
        json={
            "base_url": "https://example.atlassian.net",
            "project_key": "PROJ",
            "user_email": "jira@example.com",
            "api_token": "token",
            "enabled": True,
        },
    )
    assert response.status_code == 403


async def test_non_admin_cannot_read_jira_integration(client, contributor_headers):
    response = await client.get("/api/v1/integrations/jira", headers=contributor_headers)
    assert response.status_code == 403


async def test_admin_can_test_jira_integration(client, admin_headers, monkeypatch):
    import app.api.integrations as integrations_api

    async def fake_test_jira_connection(*, base_url, project_key, user_email, api_token):
        assert base_url == "https://example.atlassian.net"
        assert project_key == "PROJ"
        assert user_email == "jira@example.com"
        assert api_token == "token"
        return True, "Connected to Jira project PROJ."

    monkeypatch.setattr(integrations_api, "test_jira_connection", fake_test_jira_connection)

    response = await client.post(
        "/api/v1/integrations/jira/test",
        headers=admin_headers,
        json={
            "base_url": "https://example.atlassian.net",
            "project_key": "PROJ",
            "user_email": "jira@example.com",
            "api_token": "token",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True, "message": "Connected to Jira project PROJ."}


async def test_non_admin_cannot_test_jira_integration(client, contributor_headers):
    response = await client.post(
        "/api/v1/integrations/jira/test",
        headers=contributor_headers,
        json={
            "base_url": "https://example.atlassian.net",
            "project_key": "PROJ",
            "user_email": "jira@example.com",
            "api_token": "token",
        },
    )
    assert response.status_code == 403


async def test_contributor_can_set_and_clear_jira_key(
    client,
    admin_headers,
    contributor_headers,
    default_jurisdiction,
    db_session,
    test_requirement,
):
    cycle_id, item = await _create_cycle_and_item(
        client, admin_headers, default_jurisdiction, db_session
    )

    set_response = await client.put(
        f"/api/v1/review-cycles/{cycle_id}/items/{item.id}/jira",
        headers=contributor_headers,
        json={"jira_issue_key": "ABC-123"},
    )
    assert set_response.status_code == 200
    assert set_response.json()["jira_issue_key"] == "ABC-123"

    clear_response = await client.put(
        f"/api/v1/review-cycles/{cycle_id}/items/{item.id}/jira",
        headers=contributor_headers,
        json={"jira_issue_key": None},
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["jira_issue_key"] is None


async def test_assigned_reviewer_cannot_set_jira_key(
    client,
    assigned_reviewer_headers,
    assigned_reviewer_user,
    db_session,
    test_requirement,
    default_jurisdiction,
):
    cycle = ReviewCycle(
        name="Assigned Reviewer Jira Restriction",
        scope="all",
        jurisdiction_id=default_jurisdiction.id,
        created_by=assigned_reviewer_user.id,
    )
    db_session.add(cycle)
    await db_session.commit()
    await db_session.refresh(cycle)

    item = ReviewItem(
        review_cycle_id=cycle.id,
        requirement_id=test_requirement.id,
        review_status="pending",
        assigned_reviewer_id=assigned_reviewer_user.id,
    )
    db_session.add(item)
    await db_session.commit()

    response = await client.put(
        f"/api/v1/review-cycles/{cycle.id}/items/{item.id}/jira",
        headers=assigned_reviewer_headers,
        json={"jira_issue_key": "PROJ-10"},
    )
    assert response.status_code == 403


async def test_jira_key_validation_and_project_scope(
    client,
    admin_headers,
    contributor_headers,
    default_jurisdiction,
    db_session,
    test_requirement,
):
    integration_response = await client.put(
        "/api/v1/integrations/jira",
        headers=admin_headers,
        json={
            "base_url": "https://example.atlassian.net",
            "project_key": "PROJ",
            "user_email": "jira@example.com",
            "api_token": "token",
            "enabled": True,
        },
    )
    assert integration_response.status_code == 200

    cycle_id, item = await _create_cycle_and_item(
        client, admin_headers, default_jurisdiction, db_session
    )

    invalid_response = await client.put(
        f"/api/v1/review-cycles/{cycle_id}/items/{item.id}/jira",
        headers=contributor_headers,
        json={"jira_issue_key": "bad-key"},
    )
    assert invalid_response.status_code == 400

    other_project_response = await client.put(
        f"/api/v1/review-cycles/{cycle_id}/items/{item.id}/jira",
        headers=contributor_headers,
        json={"jira_issue_key": "OTHER-101"},
    )
    assert other_project_response.status_code == 400


async def test_cycle_detail_is_read_only_and_manual_sync(
    client,
    admin_headers,
    default_jurisdiction,
    db_session,
    test_requirement,
    monkeypatch,
):
    import app.services.jira as jira_service

    integration_response = await client.put(
        "/api/v1/integrations/jira",
        headers=admin_headers,
        json={
            "base_url": "https://example.atlassian.net",
            "project_key": "PROJ",
            "user_email": "jira@example.com",
            "api_token": "token",
            "enabled": True,
        },
    )
    assert integration_response.status_code == 200

    cycle_id, item = await _create_cycle_and_item(
        client, admin_headers, default_jurisdiction, db_session
    )
    item.jira_issue_key = "PROJ-42"
    item.jira_synced_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.commit()

    async def fake_fetch_jira_issues(*, base_url, user_email, api_token, issue_keys):
        assert "PROJ-42" in issue_keys
        return {
            "PROJ-42": JiraIssueData(
                key="PROJ-42",
                issue_url="https://example.atlassian.net/browse/PROJ-42",
                status="In Progress",
                summary="Implement CAP Jira sync",
                assignee="Jane Doe",
                priority="High",
                updated_at=datetime.now(timezone.utc),
            )
        }

    monkeypatch.setattr(jira_service, "fetch_jira_issues", fake_fetch_jira_issues)

    before = await client.get(f"/api/v1/review-cycles/{cycle_id}", headers=admin_headers)
    assert before.status_code == 200
    assert next(i for i in before.json()["items"] if i["id"] == str(item.id))["jira_status"] is None
    manual = await client.post(f"/api/v1/review-cycles/{cycle_id}/jira-sync", headers=admin_headers, json={})
    assert manual.status_code == 200
    detail_response = await client.get(f"/api/v1/review-cycles/{cycle_id}", headers=admin_headers)
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["jira_integration_configured"] is True
    synced_item = next(i for i in detail["items"] if i["id"] == str(item.id))
    assert synced_item["jira_status"] == "In Progress"
    assert synced_item["jira_summary"] == "Implement CAP Jira sync"

    sync_response = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/jira-sync",
        headers=admin_headers,
        json={"force": True},
    )
    assert sync_response.status_code == 200
    sync_data = sync_response.json()
    assert sync_data["integration_configured"] is True
    assert sync_data["refreshed_items"] >= 1


async def test_cycle_detail_reports_jira_integration_unconfigured(
    client,
    admin_headers,
    default_jurisdiction,
    db_session,
    test_requirement,
):
    cycle_id, _item = await _create_cycle_and_item(
        client, admin_headers, default_jurisdiction, db_session
    )

    detail_response = await client.get(f"/api/v1/review-cycles/{cycle_id}", headers=admin_headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["jira_integration_configured"] is False


async def test_cycle_detail_reports_enabled_jira_integration_without_item_keys(
    client,
    admin_headers,
    default_jurisdiction,
    db_session,
    test_requirement,
):
    integration_response = await client.put(
        "/api/v1/integrations/jira",
        headers=admin_headers,
        json={
            "base_url": "https://example.atlassian.net",
            "project_key": "PROJ",
            "user_email": "jira@example.com",
            "api_token": "token",
            "enabled": True,
        },
    )
    assert integration_response.status_code == 200

    cycle_id, _item = await _create_cycle_and_item(
        client, admin_headers, default_jurisdiction, db_session
    )

    detail_response = await client.get(f"/api/v1/review-cycles/{cycle_id}", headers=admin_headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["jira_integration_configured"] is True


async def test_manual_sync_reports_enabled_integration_with_zero_keyed_items(
    client,
    admin_headers,
    default_jurisdiction,
    db_session,
    test_requirement,
):
    integration_response = await client.put(
        "/api/v1/integrations/jira",
        headers=admin_headers,
        json={
            "base_url": "https://example.atlassian.net",
            "project_key": "PROJ",
            "user_email": "jira@example.com",
            "api_token": "token",
            "enabled": True,
        },
    )
    assert integration_response.status_code == 200

    cycle_id, _item = await _create_cycle_and_item(
        client, admin_headers, default_jurisdiction, db_session
    )

    sync_response = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/jira-sync",
        headers=admin_headers,
        json={"force": True},
    )
    assert sync_response.status_code == 200
    assert sync_response.json()["integration_configured"] is True


async def test_manual_sync_reports_disabled_integration_when_disabled(
    client,
    admin_headers,
    default_jurisdiction,
    db_session,
    test_requirement,
):
    integration_response = await client.put(
        "/api/v1/integrations/jira",
        headers=admin_headers,
        json={
            "base_url": "https://example.atlassian.net",
            "project_key": "PROJ",
            "user_email": "jira@example.com",
            "api_token": "token",
            "enabled": False,
        },
    )
    assert integration_response.status_code == 200

    cycle_id, _item = await _create_cycle_and_item(
        client, admin_headers, default_jurisdiction, db_session
    )

    sync_response = await client.post(
        f"/api/v1/review-cycles/{cycle_id}/jira-sync",
        headers=admin_headers,
        json={"force": True},
    )
    assert sync_response.status_code == 200
    assert sync_response.json()["integration_configured"] is False


async def test_jira_sync_error_does_not_break_cycle_detail(
    client,
    admin_headers,
    default_jurisdiction,
    db_session,
    test_requirement,
    monkeypatch,
):
    import app.services.jira as jira_service

    integration_response = await client.put(
        "/api/v1/integrations/jira",
        headers=admin_headers,
        json={
            "base_url": "https://example.atlassian.net",
            "project_key": "PROJ",
            "user_email": "jira@example.com",
            "api_token": "token",
            "enabled": True,
        },
    )
    assert integration_response.status_code == 200

    cycle_id, item = await _create_cycle_and_item(
        client, admin_headers, default_jurisdiction, db_session
    )
    item.jira_issue_key = "PROJ-99"
    item.jira_synced_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.commit()

    async def fail_fetch_jira_issues(*, base_url, user_email, api_token, issue_keys):
        raise JiraServiceError("Mock Jira outage")

    monkeypatch.setattr(jira_service, "fetch_jira_issues", fail_fetch_jira_issues)

    manual = await client.post(f"/api/v1/review-cycles/{cycle_id}/jira-sync", headers=admin_headers, json={})
    assert manual.status_code == 200
    detail_response = await client.get(f"/api/v1/review-cycles/{cycle_id}", headers=admin_headers)
    assert detail_response.status_code == 200
    detail = detail_response.json()
    synced_item = next(i for i in detail["items"] if i["id"] == str(item.id))
    assert "Mock Jira outage" in (synced_item["jira_sync_error"] or "")


async def test_unexpected_jira_sync_exception_does_not_break_cycle_detail(
    client,
    admin_headers,
    default_jurisdiction,
    db_session,
    test_requirement,
    monkeypatch,
):
    import app.api.reviews as reviews_api

    integration_response = await client.put(
        "/api/v1/integrations/jira",
        headers=admin_headers,
        json={
            "base_url": "https://example.atlassian.net",
            "project_key": "PROJ",
            "user_email": "jira@example.com",
            "api_token": "token",
            "enabled": True,
        },
    )
    assert integration_response.status_code == 200

    cycle_id, _item = await _create_cycle_and_item(
        client, admin_headers, default_jurisdiction, db_session
    )

    async def raise_unexpected(*args, **kwargs):
        raise RuntimeError("unexpected jira sync failure")

    monkeypatch.setattr(reviews_api, "sync_review_cycle_jira_items", raise_unexpected)

    detail_response = await client.get(f"/api/v1/review-cycles/{cycle_id}", headers=admin_headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["jira_integration_configured"] is True


async def test_jira_records_are_tenant_scoped_and_unattributed_rows_are_ignored(
    client, admin_headers, admin_user, db_session
):
    saved = await client.put(
        "/api/v1/integrations/jira",
        headers=admin_headers,
        json={
            "base_url": "https://first.atlassian.net",
            "project_key": "FIRST",
            "user_email": "first@example.com",
            "api_token": "first-secret",
            "enabled": True,
        },
    )
    assert saved.status_code == 200

    legacy = JiraIntegration(
        organization_id=None,
        base_url="https://legacy.atlassian.net",
        project_key="LEGACY",
        user_email="legacy@example.com",
        api_token_encrypted=encrypt_token("legacy-secret"),
        enabled=True,
        updated_by=admin_user.id,
    )
    db_session.add(legacy)
    await db_session.commit()

    other_org = Organization(code="other-jira", name="Other Jira")
    db_session.add(other_org)
    await db_session.flush()
    other_user = User(
        organization_id=other_org.id,
        email="other-operator@example.com",
        password_hash=hash_password("otherpass"),
        full_name="Other Operator",
        role="admin",
    )
    db_session.add(other_user)
    await db_session.commit()
    other_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(other_user.id)})}"}

    other_settings = await client.get("/api/v1/integrations/jira", headers=other_headers)
    assert other_settings.status_code == 200
    assert other_settings.json()["configured"] is False
    assert await get_jira_integration(db_session, None) is None

    first_settings = await client.get("/api/v1/integrations/jira", headers=admin_headers)
    assert first_settings.json()["integration"]["base_url"] == "https://first.atlassian.net"

    other_test = await client.post(
        "/api/v1/integrations/jira/test",
        headers=other_headers,
        json={
            "base_url": "https://first.atlassian.net",
            "project_key": "FIRST",
            "user_email": "first@example.com",
        },
    )
    assert other_test.status_code == 400
    assert "token is required" in other_test.json()["detail"]


async def test_operator_without_organisation_cannot_create_shared_jira_credentials(
    client, db_session, monkeypatch
):
    from app.config import settings

    operator = User(
        email="unscoped-operator@example.com",
        password_hash=hash_password("operatorpass"),
        full_name="Unscoped Operator",
        role="admin",
    )
    db_session.add(operator)
    await db_session.commit()
    monkeypatch.setattr(settings, "installation_operator_ids", [str(operator.id)])
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(operator.id)})}"}

    response = await client.put(
        "/api/v1/integrations/jira",
        headers=headers,
        json={
            "base_url": "https://first.atlassian.net",
            "project_key": "FIRST",
            "user_email": "first@example.com",
            "api_token": "secret",
            "enabled": True,
        },
    )
    assert response.status_code == 400
    assert "organisation is required" in response.json()["detail"]


async def test_saved_token_cannot_be_tested_against_another_site_or_account(
    client, admin_headers, monkeypatch
):
    configured = await client.put(
        "/api/v1/integrations/jira",
        headers=admin_headers,
        json={
            "base_url": "https://first.atlassian.net",
            "project_key": "FIRST",
            "user_email": "first@example.com",
            "api_token": "first-secret",
            "enabled": True,
        },
    )
    assert configured.status_code == 200

    async def unexpected_network(**kwargs):
        raise AssertionError("No Jira request should be sent")

    monkeypatch.setattr("app.api.integrations.test_jira_connection", unexpected_network)
    for base_url, email in (
        ("https://second.atlassian.net", "first@example.com"),
        ("https://first.atlassian.net", "second@example.com"),
    ):
        body = {
            "base_url": base_url,
            "project_key": "FIRST",
            "user_email": email,
        }
        response = await client.post(
            "/api/v1/integrations/jira/test", headers=admin_headers, json=body
        )
        assert response.status_code == 400
        assert "new API token" in response.json()["detail"]

        update = await client.put(
            "/api/v1/integrations/jira", headers=admin_headers, json=body
        )
        assert update.status_code == 400


@pytest.mark.parametrize(
    "base_url",
    [
        "http://first.atlassian.net",
        "https://first.atlassian.net.evil.test",
        "https://127.0.0.1",
        "https://first.atlassian.net:8443",
        "https://first.atlassian.net/other",
        "https://first.atlassian.net/?next=evil",
        "https://first.atlassian.net/#section",
    ],
)
def test_jira_destination_rejects_unapproved_origins(base_url):
    with pytest.raises(ValueError):
        normalize_jira_base_url(base_url)


async def test_sync_revalidates_saved_destination_before_sending_credential(monkeypatch):
    class NoNetworkClient:
        def __init__(self, **kwargs):
            raise AssertionError("Invalid saved destination reached HTTP client")

    monkeypatch.setattr("app.services.jira.httpx.AsyncClient", NoNetworkClient)
    with pytest.raises(JiraServiceError, match="Invalid saved Jira configuration"):
        await fetch_jira_issues(
            base_url="https://127.0.0.1",
            user_email="jira@example.com",
            api_token="saved-secret",
            issue_keys={"PROJ-1"},
        )


async def test_sync_does_not_follow_redirects_with_credentials(monkeypatch):
    real_client = httpx.AsyncClient
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            302, headers={"Location": "https://elsewhere.example/rest/api/3/search"}
        )

    def client_factory(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("app.services.jira.httpx.AsyncClient", client_factory)
    with pytest.raises(JiraServiceError, match="302"):
        await fetch_jira_issues(
            base_url="https://first.atlassian.net",
            user_email="jira@example.com",
            api_token="saved-secret",
            issue_keys={"PROJ-1"},
        )
    assert len(requests) == 1
    assert requests[0].url.host == "first.atlassian.net"
