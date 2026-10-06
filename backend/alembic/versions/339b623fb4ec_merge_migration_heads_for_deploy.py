"""merge migration heads for deploy

Revision ID: 339b623fb4ec
Revises: 9b7c5d2e1f0a, a9c3d1e4f7b2, ab12cd34ef56, b3d5e7f9a2c1, c9d8e7f6a5b4, e6b1f2a3c4d5
Create Date: 2026-02-06 21:20:00.166943

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "339b623fb4ec"
down_revision: Union[str, None] = (
    "9b7c5d2e1f0a",
    "a9c3d1e4f7b2",
    "ab12cd34ef56",
    "b3d5e7f9a2c1",
    "c9d8e7f6a5b4",
    "e6b1f2a3c4d5",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
