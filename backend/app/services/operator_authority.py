from app.config import settings
from app.models.user import User


def has_operator_designation(user: User) -> bool:
    return bool(user.operator_trusted or str(user.id) in settings.installation_operator_ids)


def is_installation_operator(user: User) -> bool:
    """Installation trust is separate from a tenant admin role."""
    return bool(user.active and user.role == "admin" and has_operator_designation(user))
