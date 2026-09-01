"""fixed roles and added a pooler

Revision ID: 8bcf5cb7d70e
Revises: cc87caec65c7
Create Date: 2026-08-31 12:16:46.228601

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8bcf5cb7d70e'
down_revision: Union[str, Sequence[str], None] = 'cc87caec65c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # No-op: this migration's original data-collapse + enum-swap logic had an
    # ordering bug (partial index built against the old enum type before the
    # swap). The corrected version of this work now lives entirely in
    # 4f77bfe54114, which supersedes it.
    pass


def downgrade() -> None:
    """Downgrade schema."""
    # No-op — see upgrade().
    pass