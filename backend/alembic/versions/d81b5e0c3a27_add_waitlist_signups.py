"""add waitlist_signups

Emails left on the landing page's early-release form.

Revision ID: d81b5e0c3a27
Revises: c7e2a41f9b3d
Create Date: 2026-10-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd81b5e0c3a27'
down_revision: Union[str, Sequence[str], None] = 'c7e2a41f9b3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'waitlist_signups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=254), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_waitlist_signups_email'), 'waitlist_signups', ['email'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_waitlist_signups_email'), table_name='waitlist_signups')
    op.drop_table('waitlist_signups')
