import base64
import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.jira import JiraIntegration
from app.models.review import ReviewCycle, ReviewItem

JIRA_ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-[0-9]+$")


class JiraServiceError(Exception):
    pass


@dataclass
class JiraIssueData:
    key: str
    issue_url: str
    status: Optional[str]
    summary: Optional[str]
    assignee: Optional[str]
    priority: Optional[str]
    updated_at: Optional[datetime]


@dataclass
class JiraSyncSummary:
    total_items: int = 0
    keyed_items: int = 0
    refreshed_items: int = 0
    skipped_fresh_items: int = 0
    failed_items: int = 0
    missing_items: int = 0
    integration_configured: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "total_items": self.total_items,
            "keyed_items": self.keyed_items,
            "refreshed_items": self.refreshed_items,
            "skipped_fresh_items": self.skipped_fresh_items,
            "failed_items": self.failed_items,
            "missing_items": self.missing_items,
            "integration_configured": self.integration_configured,
        }


def normalize_jira_base_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("Jira base URL is required")
    if "://" not in raw:
        raw = f"https://{raw}"

    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("Invalid Jira base URL")
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Jira URL must be an HTTPS origin on port 443 without credentials, path, query or fragment")
    if not (host.endswith(".atlassian.net") or host in settings.jira_allowed_hosts):
        raise ValueError(
            "Jira host must be an Atlassian Cloud site or an explicitly configured JIRA_ALLOWED_HOSTS entry"
        )
    return f"https://{host}"


def normalize_project_key(value: str) -> str:
    project_key = (value or "").strip().upper()
    if not project_key:
        raise ValueError("Jira project key is required")
    if not re.fullmatch(r"[A-Z][A-Z0-9]+", project_key):
        raise ValueError("Invalid Jira project key")
    return project_key


def normalize_issue_key(value: str) -> str:
    issue_key = (value or "").strip().upper()
    if not issue_key:
        raise ValueError("Jira issue key is required")
    if not JIRA_ISSUE_KEY_RE.fullmatch(issue_key):
        raise ValueError("Jira issue key must look like PROJ-123")
    return issue_key


def validate_issue_key(issue_key: str, project_key: Optional[str] = None) -> str:
    normalized = normalize_issue_key(issue_key)
    if project_key:
        project_normalized = normalize_project_key(project_key)
        if not normalized.startswith(f"{project_normalized}-"):
            raise ValueError(f"Jira issue key must belong to project {project_normalized}")
    return normalized


def _normalize_email(value: str) -> str:
    email = (value or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("Valid Jira user email is required")
    return email


def _fernet() -> Fernet:
    secret = (settings.secret_key or "change-me-in-production").encode("utf-8")
    digest = hashlib.sha256(secret).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_token(raw_token: str) -> str:
    token = (raw_token or "").strip()
    if not token:
        raise ValueError("Jira API token is required")
    return _fernet().encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_token(encrypted_token: str) -> str:
    if not encrypted_token:
        raise ValueError("Stored Jira API token is missing")
    try:
        return _fernet().decrypt(encrypted_token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Stored Jira API token could not be decrypted") from exc


def _auth_header(user_email: str, api_token: str) -> str:
    token = base64.b64encode(f"{user_email}:{api_token}".encode("utf-8")).decode("utf-8")
    return f"Basic {token}"


def _jira_headers(user_email: str, api_token: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": _auth_header(user_email, api_token),
    }


def _parse_jira_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    normalized = value.strip()
    try:
        if normalized.endswith("Z"):
            return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass

    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    return None


async def get_jira_integration(
    db: AsyncSession, organization_id: Optional[uuid.UUID]
) -> Optional[JiraIntegration]:
    # NULL marks legacy/unattributed rows, never a shared tenant.
    if organization_id is None:
        return None
    result = await db.execute(
        select(JiraIntegration)
        .where(JiraIntegration.organization_id == organization_id)
        .order_by(JiraIntegration.updated_at.desc(), JiraIntegration.created_at.desc())
    )
    return result.scalars().first()


def validate_saved_token_target(integration, base_url, email, api_token):
    if not (api_token or "").strip() and (
        integration.base_url != normalize_jira_base_url(base_url)
        or integration.user_email != email.strip().lower()
    ):
        raise ValueError(
            "Enter a new API token when changing the Jira site or account. Saved credentials cannot be sent to another destination."
        )


async def upsert_jira_integration(
    db: AsyncSession,
    *,
    base_url: str,
    project_key: str,
    user_email: str,
    api_token: Optional[str],
    enabled: bool,
    updated_by: Optional[uuid.UUID],
    organization_id: Optional[uuid.UUID],
) -> JiraIntegration:
    if organization_id is None:
        raise ValueError("An organisation is required to configure Jira")
    integration = await get_jira_integration(db, organization_id)

    normalized_base_url = normalize_jira_base_url(base_url)
    normalized_project_key = normalize_project_key(project_key)
    normalized_email = _normalize_email(user_email)

    if integration is None:
        if not api_token:
            raise ValueError("Jira API token is required")
        integration = JiraIntegration(
            organization_id=organization_id,
            base_url=normalized_base_url,
            project_key=normalized_project_key,
            user_email=normalized_email,
            api_token_encrypted=encrypt_token(api_token),
            enabled=bool(enabled),
            updated_by=updated_by,
        )
        db.add(integration)
        await db.flush()
        return integration

    validate_saved_token_target(integration, normalized_base_url, normalized_email, api_token)
    integration.base_url = normalized_base_url
    integration.project_key = normalized_project_key
    integration.user_email = normalized_email
    integration.enabled = bool(enabled)
    integration.updated_by = updated_by
    integration.updated_at = datetime.now(timezone.utc)

    if api_token and api_token.strip():
        integration.api_token_encrypted = encrypt_token(api_token)

    await db.flush()
    return integration


async def test_jira_connection(
    *,
    base_url: str,
    project_key: str,
    user_email: str,
    api_token: str,
) -> tuple[bool, str]:
    normalized_base_url = normalize_jira_base_url(base_url)
    normalized_project_key = normalize_project_key(project_key)
    normalized_email = _normalize_email(user_email)
    token = (api_token or "").strip()
    if not token:
        raise ValueError("Jira API token is required for connection test")

    timeout = settings.jira_request_timeout_seconds
    url = f"{normalized_base_url}/rest/api/3/project/{normalized_project_key}"
    async with httpx.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False) as client:
        response = await client.get(url, headers=_jira_headers(normalized_email, token))

    if response.status_code == 200:
        payload = response.json()
        project_name = payload.get("name") or normalized_project_key
        return True, f"Connected to Jira project {project_name}."

    detail = response.text.strip()[:300] if response.text else "Unknown Jira error"
    return False, f"Jira connection failed ({response.status_code}): {detail}"


async def fetch_jira_issues(
    *,
    base_url: str,
    user_email: str,
    api_token: str,
    issue_keys: set[str],
) -> dict[str, JiraIssueData]:
    if not issue_keys:
        return {}

    try:
        normalized_base_url = normalize_jira_base_url(base_url)
        normalized_email = _normalize_email(user_email)
        keys_sorted = sorted(normalize_issue_key(key) for key in issue_keys)
    except ValueError as exc:
        raise JiraServiceError(f"Invalid saved Jira configuration: {exc}") from exc

    quoted_keys = ", ".join(f'"{key}"' for key in keys_sorted)
    jql = f"key in ({quoted_keys})"
    payload = {
        "jql": jql,
        "fields": ["summary", "status", "assignee", "priority", "updated"],
        "maxResults": len(keys_sorted),
    }

    timeout = settings.jira_request_timeout_seconds
    url = f"{normalized_base_url}/rest/api/3/search"
    async with httpx.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False) as client:
        response = await client.post(
            url, headers=_jira_headers(normalized_email, api_token), json=payload
        )

    if response.status_code != 200:
        detail = response.text.strip()[:300] if response.text else "Unknown Jira error"
        raise JiraServiceError(f"Jira sync failed ({response.status_code}): {detail}")

    data = response.json()
    issues: dict[str, JiraIssueData] = {}
    for issue in data.get("issues", []):
        key = issue.get("key")
        if not key:
            continue
        normalized_key = key.upper()
        fields = issue.get("fields") or {}

        status = (fields.get("status") or {}).get("name")
        summary = fields.get("summary")
        assignee = (fields.get("assignee") or {}).get("displayName")
        priority = (fields.get("priority") or {}).get("name")
        updated_at = _parse_jira_timestamp(fields.get("updated"))

        issues[normalized_key] = JiraIssueData(
            key=normalized_key,
            issue_url=f"{normalized_base_url}/browse/{normalized_key}",
            status=status,
            summary=summary,
            assignee=assignee,
            priority=priority,
            updated_at=updated_at,
        )

    return issues


def clear_item_jira_fields(item: ReviewItem, clear_key: bool = False) -> None:
    if clear_key:
        item.jira_issue_key = None
    item.jira_issue_url = None
    item.jira_status = None
    item.jira_summary = None
    item.jira_assignee = None
    item.jira_priority = None
    item.jira_updated_at = None
    item.jira_synced_at = None
    item.jira_sync_error = None


def apply_item_jira_key(
    item: ReviewItem,
    *,
    issue_key: Optional[str],
    project_key: Optional[str],
    base_url: Optional[str],
) -> Optional[str]:
    if issue_key is None or not issue_key.strip():
        clear_item_jira_fields(item, clear_key=True)
        return None

    normalized_key = validate_issue_key(issue_key, project_key)
    item.jira_issue_key = normalized_key
    item.jira_issue_url = f"{base_url}/browse/{normalized_key}" if base_url else None
    item.jira_status = None
    item.jira_summary = None
    item.jira_assignee = None
    item.jira_priority = None
    item.jira_updated_at = None
    item.jira_synced_at = None
    item.jira_sync_error = None
    return normalized_key


def _mark_sync_error(item: ReviewItem, message: str, now: datetime) -> None:
    item.jira_sync_error = message
    item.jira_synced_at = now


def _coerce_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def sync_review_cycle_jira_items(
    db: AsyncSession,
    review_cycle_id: uuid.UUID,
    *,
    force: bool = False,
    assigned_reviewer_id: Optional[uuid.UUID] = None,
) -> JiraSyncSummary:
    summary = JiraSyncSummary()
    now = datetime.now(timezone.utc)

    query = select(ReviewItem).where(ReviewItem.review_cycle_id == review_cycle_id)
    if assigned_reviewer_id is not None:
        query = query.where(ReviewItem.assigned_reviewer_id == assigned_reviewer_id)
    result = await db.execute(query)
    all_items = result.scalars().all()
    summary.total_items = len(all_items)

    cycle = await db.get(ReviewCycle, review_cycle_id)
    if cycle is None:
        return summary
    integration = await get_jira_integration(db, cycle.organization_id)
    summary.integration_configured = bool(integration is not None and integration.enabled)

    keyed_items = [item for item in all_items if (item.jira_issue_key or "").strip()]
    summary.keyed_items = len(keyed_items)
    if not keyed_items:
        return summary

    if integration is None or not integration.enabled:
        return summary

    try:
        token = decrypt_token(integration.api_token_encrypted)
    except ValueError as exc:
        message = str(exc)
        for item in keyed_items:
            _mark_sync_error(item, message, now)
            summary.failed_items += 1
        return summary

    stale_after = now - timedelta(minutes=max(1, settings.jira_sync_ttl_minutes))
    refresh_items: list[ReviewItem] = []
    for item in keyed_items:
        if force or item.jira_synced_at is None:
            refresh_items.append(item)
            continue

        synced_at = _coerce_aware(item.jira_synced_at)
        if synced_at < stale_after:
            refresh_items.append(item)
        else:
            summary.skipped_fresh_items += 1

    if not refresh_items:
        return summary

    issue_keys: set[str] = set()
    for item in refresh_items:
        try:
            normalized = validate_issue_key(item.jira_issue_key or "", integration.project_key)
            issue_keys.add(normalized)
            item.jira_issue_key = normalized
        except ValueError as exc:
            _mark_sync_error(item, str(exc), now)
            summary.failed_items += 1

    if not issue_keys:
        return summary

    try:
        issues_by_key = await fetch_jira_issues(
            base_url=integration.base_url,
            user_email=integration.user_email,
            api_token=token,
            issue_keys=issue_keys,
        )
    except JiraServiceError as exc:
        message = str(exc)
        for item in refresh_items:
            _mark_sync_error(item, message, now)
            summary.failed_items += 1
        return summary

    for item in refresh_items:
        key = (item.jira_issue_key or "").upper()
        issue = issues_by_key.get(key)
        item.jira_synced_at = now

        if issue is None:
            item.jira_issue_url = f"{integration.base_url}/browse/{key}" if key else None
            item.jira_status = None
            item.jira_summary = None
            item.jira_assignee = None
            item.jira_priority = None
            item.jira_updated_at = None
            item.jira_sync_error = f"Jira issue {key} was not found"
            summary.failed_items += 1
            summary.missing_items += 1
            continue

        item.jira_issue_url = issue.issue_url
        item.jira_status = issue.status
        item.jira_summary = issue.summary
        item.jira_assignee = issue.assignee
        item.jira_priority = issue.priority
        item.jira_updated_at = issue.updated_at
        item.jira_sync_error = None
        summary.refreshed_items += 1

    return summary
