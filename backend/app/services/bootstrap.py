import re
from dataclasses import dataclass

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models.jurisdiction import Jurisdiction
from app.models.organization import Organization
from app.models.user import User
from app.services.audit import log_action
from app.services.auth import hash_password
from app.services.operator_authority import is_installation_operator
from app.services.setup_example import add_setup_example


@dataclass(frozen=True)
class SetupResult:
    email: str
    jurisdiction_code: str
    created_user: bool
    created_jurisdiction: bool
    created_example: bool


async def setup_installation(
    db: AsyncSession,
    *,
    email: str,
    name: str | None,
    password: str | None,
    jurisdiction_code: str,
    jurisdiction_name: str,
    existing_admin: bool = False,
    example: bool = False,
) -> SetupResult:
    """Install an operator and first scope atomically from a local trusted process.

    An HTTP tenant admin cannot call this service. The CLI is the sole setup entry point.
    Repeating a successful command does not reset credentials or change existing data.
    """
    try:
        email = validate_email(
            email.strip(),
            check_deliverability=False,
            test_environment=settings.app_env.lower() == "test",
        ).normalized.lower()
    except EmailNotValidError as exc:
        raise ValueError("Provide a valid operator email address.") from exc
    code = jurisdiction_code.strip().lower()
    jurisdiction_name = jurisdiction_name.strip()
    name = name.strip() if name else None
    if len(email) > 255:
        raise ValueError("Provide a valid operator email address.")
    if not re.fullmatch(r"[a-z0-9_-]{2,20}", code):
        raise ValueError("Jurisdiction code must contain 2-20 lowercase letters, digits, _ or -.")
    if not jurisdiction_name or len(jurisdiction_name) > 255:
        raise ValueError("Jurisdiction name must contain 1-255 characters.")
    if example and settings.app_env.lower() not in {"development", "test"}:
        raise ValueError("--example is available only in development or test installations.")
    if example and code == "example":
        raise ValueError("Choose a real jurisdiction code other than 'example' for --example.")
    if existing_admin:
        if password is not None:
            raise ValueError("Do not supply a password when using an existing admin.")
    elif not name or len(name) > 255 or not password or not 8 <= len(password.encode()) <= 72:
        raise ValueError("Provide a name and password of 8-72 UTF-8 bytes for a new admin.")

    async with db.begin():
        user = (
            await db.execute(select(User).where(func.lower(User.email) == email))
        ).scalar_one_or_none()
        created_user = False
        if existing_admin:
            if user is None or not user.active or user.role != "admin":
                raise ValueError("The selected account must be an active existing admin.")
            if user.organization_id is None:
                raise ValueError("The selected admin has no organization. Assign one before setup.")
        elif user is not None:
            if not is_installation_operator(user):
                raise ValueError("Account exists. Use --existing-admin to designate it explicitly.")
            if user.full_name != name:
                raise ValueError(
                    "The existing operator has a different name; setup changed nothing."
                )
        else:
            any_user = (await db.execute(select(User.id).limit(1))).first()
            if any_user:
                raise ValueError(
                    "Accounts already exist. Use --existing-admin for an active admin."
                )
            organization = (
                await db.execute(select(Organization).where(Organization.code == "default"))
            ).scalar_one_or_none()
            if organization is None:
                organization = Organization(
                    code="default", name="Default Organization", active=True
                )
                db.add(organization)
                await db.flush()
            user = User(
                organization_id=organization.id,
                email=email,
                full_name=name,
                password_hash=hash_password(password),
                role="admin",
                active=True,
                operator_trusted=True,
            )
            db.add(user)
            created_user = True

        # Only an explicit local command can designate an existing tenant admin.
        was_designated = False if created_user else bool(user.operator_trusted)
        user.operator_trusted = True
        if not created_user and not was_designated:
            user.auth_version += 1
        await db.flush()
        if not was_designated:
            await log_action(
                db,
                user,
                "designate",
                "installation_operator",
                str(user.id),
                new_value={"trusted": True, "source": "local_setup"},
            )
        jurisdiction = (
            await db.execute(select(Jurisdiction).where(Jurisdiction.code == code))
        ).scalar_one_or_none()
        created_jurisdiction = jurisdiction is None
        if jurisdiction is None:
            jurisdiction = Jurisdiction(code=code, name=jurisdiction_name, active=True)
            db.add(jurisdiction)
            await db.flush()
            await log_action(
                db,
                user,
                "create",
                "jurisdiction",
                str(jurisdiction.id),
                new_value={"code": code, "name": jurisdiction_name},
            )
        elif jurisdiction.name != jurisdiction_name or not jurisdiction.active:
            raise ValueError(
                "Jurisdiction code has different or inactive data; setup changed nothing."
            )
        created_example = await add_setup_example(db, user) if example else False
        if created_example:
            await log_action(
                db,
                user,
                "create",
                "setup_example",
                "example",
                new_value={"scope": "example", "status": "draft"},
            )

    return SetupResult(email, code, created_user, created_jurisdiction, created_example)


async def ensure_bootstrap_admin() -> None:
    email = settings.bootstrap_admin_email.strip()
    name = settings.bootstrap_admin_name.strip()
    password = settings.bootstrap_admin_password
    if not email or not name or not password:
        return

    async with async_session() as session:
        org_result = await session.execute(
            select(Organization).where(Organization.code == "default")
        )
        organization = org_result.scalar_one_or_none()
        if organization is None:
            existing_org_result = await session.execute(select(Organization).limit(1))
            organization = existing_org_result.scalar_one_or_none()
        if organization is None:
            organization = Organization(code="default", name="Default Organization", active=True)
            session.add(organization)
            await session.flush()

        existing = await session.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            return

        user = User(
            organization_id=organization.id,
            email=email,
            full_name=name,
            password_hash=hash_password(password),
            role="admin",
            active=True,
        )
        session.add(user)
        await session.commit()
