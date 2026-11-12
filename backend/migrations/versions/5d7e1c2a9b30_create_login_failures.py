"""create login_failures

Revision ID: 5d7e1c2a9b30
Revises: 43b64866b554
Create Date: 2026-10-12 15:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d7e1c2a9b30'
down_revision: Union[str, Sequence[str], None] = '43b64866b554'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'login_failures',
        sa.Column('account_key', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_login_failures_account_key_created_at',
        'login_failures',
        ['account_key', 'created_at'],
        unique=False,
    )
    op.create_index(op.f('ix_login_failures_created_at'), 'login_failures', ['created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Only short-lived throttle counters (at most one window's worth) - no
    # user data is lost by dropping them.
    op.drop_index(op.f('ix_login_failures_created_at'), table_name='login_failures')
    op.drop_index('ix_login_failures_account_key_created_at', table_name='login_failures')
    op.drop_table('login_failures')
