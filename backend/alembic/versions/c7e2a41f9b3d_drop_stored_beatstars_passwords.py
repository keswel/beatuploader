"""drop stored BeatStars passwords

BeatStars connections now keep only the session tokens (refresh tokens last
about a year); the password is discarded after login. Wipe the encrypted
passwords earlier versions stored in access_token_encrypted. Sessions are
untouched, so existing connections keep working.

Revision ID: c7e2a41f9b3d
Revises: a1d966c1d810
Create Date: 2026-10-02 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c7e2a41f9b3d'
down_revision: Union[str, Sequence[str], None] = 'a1d966c1d810'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE platform_connections SET access_token_encrypted = NULL "
        "WHERE provider = 'beatstars'"
    )


def downgrade() -> None:
    # The passwords are gone; nothing to restore.
    pass
