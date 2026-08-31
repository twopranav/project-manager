"""collapse project admin rows and swap projectrole enum

Revision ID: 4f77bfe54114
Revises: 8bcf5cb7d70e
Create Date: 2026-08-31 12:16:46.228601

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f77bfe54114'
down_revision: Union[str, Sequence[str], None] = '8bcf5cb7d70e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()

    # --- Drop the two indexes from 8bcf5cb7d70e before touching the column
    # type. Both were built against the current (still-4-value) enum; safer
    # to drop and recreate them fresh against the new 3-value type than to
    # rely on Postgres correctly rebuilding a partial index's literal
    # predicate across a full type swap. ---
    op.drop_index('uq_single_project_manager', table_name='project_members', postgresql_where=sa.text("project_role = 'manager'"))
    op.drop_index('ix_project_members_project_id_user_id', table_name='project_members')

    # --- Data collapse: must run before the enum swap below, since a row
    # still holding 'admin' can't be cast into a type that no longer has
    # that value. For each project with any 'admin' row, promote the
    # earliest one to 'manager' if the project doesn't already have a
    # manager; every other admin row (and any leftover after that) becomes
    # a plain 'contributor' instead. ---
    conn.execute(sa.text("""
        WITH ranked AS (
            SELECT id, project_id,
                   row_number() OVER (PARTITION BY project_id ORDER BY joined_at) AS rn
            FROM project_members
            WHERE project_role = 'admin'
        )
        UPDATE project_members pm
        SET project_role = 'manager'
        FROM ranked r
        WHERE pm.id = r.id AND r.rn = 1
        AND NOT EXISTS (
            SELECT 1 FROM project_members m
            WHERE m.project_id = pm.project_id AND m.project_role = 'manager'
        )
    """))
    conn.execute(sa.text("""
        UPDATE project_members SET project_role = 'contributor'
        WHERE project_role = 'admin'
    """))

    # --- Enum swap: rename the old type out of the way, create the new
    # 3-value type, cast the column over, drop the old type. Safe now since
    # no row can still hold 'admin' after the collapse above. ---
    op.execute("ALTER TYPE projectrole RENAME TO projectrole_old")
    op.execute("CREATE TYPE projectrole AS ENUM ('manager', 'contributor', 'viewer')")
    op.execute(
        "ALTER TABLE project_members ALTER COLUMN project_role "
        "TYPE projectrole USING project_role::text::projectrole"
    )
    op.execute("DROP TYPE projectrole_old")

    # --- Recreate both indexes against the now-correct enum. ---
    op.create_index('ix_project_members_project_id_user_id', 'project_members', ['project_id', 'user_id'], unique=False)
    op.create_index('uq_single_project_manager', 'project_members', ['project_id'], unique=True, postgresql_where=sa.text("project_role = 'manager'"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_single_project_manager', table_name='project_members', postgresql_where=sa.text("project_role = 'manager'"))
    op.drop_index('ix_project_members_project_id_user_id', table_name='project_members')

    # Restore the schema shape only — note this cannot restore which rows
    # USED to be 'admin' before the forward migration collapsed them.
    op.execute("ALTER TYPE projectrole RENAME TO projectrole_old")
    op.execute("CREATE TYPE projectrole AS ENUM ('admin', 'manager', 'contributor', 'viewer')")
    op.execute(
        "ALTER TABLE project_members ALTER COLUMN project_role "
        "TYPE projectrole USING project_role::text::projectrole"
    )
    op.execute("DROP TYPE projectrole_old")

    op.create_index('ix_project_members_project_id_user_id', 'project_members', ['project_id', 'user_id'], unique=False)
    op.create_index('uq_single_project_manager', 'project_members', ['project_id'], unique=True, postgresql_where=sa.text("project_role = 'manager'"))