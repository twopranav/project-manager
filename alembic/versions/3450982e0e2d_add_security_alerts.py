"""add security_alerts table

Revision ID: 3450982e0e2d
Revises: 7f01db2866d0
Create Date: 2026-08-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3450982e0e2d'
down_revision: Union[str, Sequence[str], None] = '7f01db2866d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'security_alerts',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('alert_type', sa.String(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('actor_user_id', sa.String(length=36), nullable=False),
        sa.Column('target_user_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('resolved', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('security_alerts')
