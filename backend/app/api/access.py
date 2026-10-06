"""Manage content access using content authority, never account-admin authority."""

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.access import AccessGrant, AccessTeam, AccessTeamMember, ResourceAccess
from app.models.user import User
from app.schemas.access import AccessUpdate, TeamCreate, TeamUpdate
from app.services.access import (
    access_details,
    get_policy,
    initialize_access,
    protect_child,
    require_access,
    tenant_clause,
)
from app.services.audit import log_action

router = APIRouter(prefix="/api/v1/access", tags=["access"])
DB = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


async def validate_members(db, ids, user):
    found = set(
        (
            await db.scalars(
                select(User.id).where(
                    User.id.in_(ids), User.active.is_(True), tenant_clause(User, user)
                )
            )
        ).all()
    )
    if found != set(ids):
        raise HTTPException(422, "Members must be active users in this organisation")


async def team_details(db, team):
    members = list(
        (
            await db.scalars(
                select(AccessTeamMember.user_id).where(AccessTeamMember.team_id == team.id)
            )
        ).all()
    )
    return {
        "id": team.id,
        "name": team.name,
        "owner_id": team.owner_id,
        "revision": team.revision,
        "member_ids": members,
    }


@router.get("/teams")
async def teams(db: DB, user: CurrentUser):
    member = select(AccessTeamMember.team_id).where(AccessTeamMember.user_id == user.id)
    rows = (
        await db.scalars(
            select(AccessTeam).where(
                tenant_clause(AccessTeam, user),
                or_(AccessTeam.owner_id == user.id, AccessTeam.id.in_(member)),
            )
        )
    ).all()
    return [await team_details(db, row) for row in rows]


@router.post("/teams", status_code=201)
async def create_team(data: TeamCreate, db: DB, user: CurrentUser):
    await validate_members(db, data.member_ids, user)
    team = AccessTeam(
        organization_id=user.organization_id, owner_id=user.id, name=data.name.strip(), revision=1
    )
    db.add(team)
    await db.flush()
    for member in set(data.member_ids) | {user.id}:
        db.add(AccessTeamMember(team_id=team.id, user_id=member))
    await log_action(db, user, "create_access_team", "access_team", str(team.id))
    await db.commit()
    return await team_details(db, team)


@router.put("/teams/{team_id}")
async def update_team(team_id: uuid.UUID, data: TeamUpdate, db: DB, user: CurrentUser):
    team = await db.scalar(
        select(AccessTeam).where(
            AccessTeam.id == team_id,
            tenant_clause(AccessTeam, user),
            AccessTeam.owner_id == user.id,
        )
    )
    if team is None:
        raise HTTPException(404, "Team not found")
    await validate_members(db, data.member_ids, user)
    changed = await db.execute(
        update(AccessTeam)
        .where(AccessTeam.id == team_id, AccessTeam.revision == data.expected_revision)
        .values(revision=AccessTeam.revision + 1, name=data.name.strip())
        .execution_options(synchronize_session=False)
    )
    if not changed.rowcount:
        raise HTTPException(409, "Team access changed. Reload before saving.")
    await db.execute(delete(AccessTeamMember).where(AccessTeamMember.team_id == team_id))
    for member in set(data.member_ids) | {team.owner_id}:
        db.add(AccessTeamMember(team_id=team.id, user_id=member))
    await log_action(
        db,
        user,
        "update_access_team",
        "access_team",
        str(team.id),
        new_value={"member_count": len(set(data.member_ids) | {team.owner_id})},
    )
    await db.commit()
    await db.refresh(team)
    return await team_details(db, team)


async def protect_sources(db, kind, resource_id, user):
    if kind == "application":
        from app.models.application import ApplicationComponent, ApplicationFollowup

        components = (
            await db.scalars(
                select(ApplicationComponent).where(
                    ApplicationComponent.application_id == resource_id
                )
            )
        ).all()
        for component in components:
            if component.case_id:
                await protect_child(
                    db, kind, resource_id, "preparation_case", component.case_id, user, force=True
                )
                await protect_sources(db, "preparation_case", component.case_id, user)
            if component.evidence_id:
                await protect_child(
                    db,
                    kind,
                    resource_id,
                    "preparation_evidence",
                    component.evidence_id,
                    user,
                    force=True,
                )
        followups = (
            await db.scalars(
                select(ApplicationFollowup).where(ApplicationFollowup.application_id == resource_id)
            )
        ).all()
        for followup in followups:
            for evidence_id in json.loads(followup.evidence_ids_json or "[]"):
                await protect_child(
                    db,
                    kind,
                    resource_id,
                    "preparation_evidence",
                    uuid.UUID(evidence_id),
                    user,
                    force=True,
                )
    elif kind == "preparation_case":
        from app.models.preparation import PreparationResponse, PreparationResponseEvidence

        ids = (
            await db.scalars(
                select(PreparationResponseEvidence.evidence_id)
                .join(
                    PreparationResponse,
                    PreparationResponse.id == PreparationResponseEvidence.response_id,
                )
                .where(PreparationResponse.case_id == resource_id)
            )
        ).all()
        for evidence_id in set(ids):
            await protect_child(
                db, kind, resource_id, "preparation_evidence", evidence_id, user, force=True
            )


@router.get("/{kind}/{resource_id}")
async def read_access(kind: str, resource_id: uuid.UUID, db: DB, user: CurrentUser):
    return await access_details(db, kind, resource_id, user)


@router.put("/{kind}/{resource_id}")
async def write_access(
    kind: str, resource_id: uuid.UUID, data: AccessUpdate, db: DB, user: CurrentUser
):
    await require_access(db, kind, resource_id, user, "manage_access")
    if not data.reason.strip():
        raise HTTPException(422, "A reason is required")
    policy = await get_policy(db, kind, resource_id)
    actual_revision = policy.revision if policy else 0
    if actual_revision != data.expected_revision:
        raise HTTPException(409, "Access changed. Reload before saving.")
    if policy is None:
        policy = await initialize_access(db, kind, resource_id, user, "organisation")
    old_visibility = policy.visibility
    if (
        policy.parent_id
        and data.visibility == "organisation"
        and policy.visibility != "organisation"
    ):
        raise HTTPException(409, "An inherited private source cannot be made organisation-wide")
    seen = set()
    for grant in data.grants:
        key = (grant.subject_type, grant.subject_id)
        if key in seen:
            raise HTTPException(422, "Duplicate grant subject")
        seen.add(key)
        if grant.subject_type == "user":
            await validate_members(db, [grant.subject_id], user)
        else:
            if data.visibility == "secret":
                raise HTTPException(422, "Secret resources require named-user grants")
            team = await db.scalar(
                select(AccessTeam).where(
                    AccessTeam.id == grant.subject_id,
                    tenant_clause(AccessTeam, user),
                    AccessTeam.owner_id == user.id,
                )
            )
            if team is None:
                raise HTTPException(422, "Only teams you own may be granted access")
    changed = await db.execute(
        update(ResourceAccess)
        .where(ResourceAccess.id == policy.id, ResourceAccess.revision == policy.revision)
        .values(revision=ResourceAccess.revision + 1)
        .execution_options(synchronize_session=False)
    )
    if not changed.rowcount:
        raise HTTPException(409, "Access changed. Reload before saving.")
    # Protect existing source records before changing audience; failure rolls back the entire request.
    if data.visibility != "organisation":
        await protect_sources(db, kind, resource_id, user)
    await db.execute(delete(AccessGrant).where(AccessGrant.policy_id == policy.id))
    for grant in data.grants:
        for permission in set(grant.permissions):
            db.add(
                AccessGrant(
                    policy_id=policy.id,
                    subject_type=grant.subject_type,
                    subject_id=grant.subject_id,
                    permission=permission,
                )
            )
    policy.visibility = data.visibility
    await log_action(
        db,
        user,
        "change_access",
        kind,
        str(resource_id),
        old_value={"visibility": old_visibility},
        new_value={
            "visibility": data.visibility,
            "reason": data.reason,
            "grant_count": len(data.grants),
        },
    )
    await db.commit()
    await db.refresh(policy)
    return await access_details(db, kind, resource_id, user)
