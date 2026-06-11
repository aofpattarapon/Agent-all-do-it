"""add_project_members

Phase 0 (Security & Isolation): per-project RBAC role assignments.

Revision ID: a1b2c3d4e5f6
Revises: 55c3dc1dbae0
Create Date: 2026-06-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '55c3dc1dbae0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'project_members',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column(
            'project_role',
            sa.String(length=50),
            server_default=sa.text("'viewer'"),
            nullable=False,
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['project_id'], ['projects.id'],
            name=op.f('project_members_project_id_fkey'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name=op.f('project_members_user_id_fkey'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('project_members_pkey')),
        sa.UniqueConstraint(
            'project_id', 'user_id', name='project_members_project_id_user_id_key'
        ),
    )
    op.create_index(
        op.f('project_members_project_id_idx'), 'project_members',
        ['project_id'], unique=False,
    )
    op.create_index(
        op.f('project_members_user_id_idx'), 'project_members',
        ['user_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('project_members_user_id_idx'), table_name='project_members')
    op.drop_index(op.f('project_members_project_id_idx'), table_name='project_members')
    op.drop_table('project_members')
