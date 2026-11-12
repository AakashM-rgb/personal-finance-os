"""add sessions.family_id

A refresh-token rotation chain ("family") outlives each rotating session row.
Access tokens carry the family id as `sid`, so revoking every live session in
a family (logout, logout-all, password change, reuse detection) cuts off its
access tokens immediately, while ordinary rotation - which keeps the family -
does not invalidate tokens other tabs are still using.

Revision ID: a3f9c1d2e7b4
Revises: 5d7e1c2a9b30
Create Date: 2026-11-12 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f9c1d2e7b4"
down_revision: str | Sequence[str] | None = "5d7e1c2a9b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("sessions", sa.Column("family_id", sa.UUID(), nullable=True))
    # Each pre-existing session starts its own family. Their rotation history
    # isn't recorded anywhere, so this is the only safe assignment; at worst
    # one already-rotated-out row and its live successor sit in different
    # families, which changes nothing for the live one.
    op.execute("UPDATE sessions SET family_id = id WHERE family_id IS NULL")
    op.alter_column("sessions", "family_id", nullable=False)
    op.create_index(op.f("ix_sessions_family_id"), "sessions", ["family_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drops only the grouping column; every session row (and so every live
    # refresh token) survives. Access tokens issued with a `sid` claim keep
    # decoding - code at the previous revision simply ignores the claim.
    op.drop_index(op.f("ix_sessions_family_id"), table_name="sessions")
    op.drop_column("sessions", "family_id")
