"""add_knowledge_templates

Revision ID: 55c3dc1dbae0
Revises: 9f8e7d6c5b4a
Create Date: 2026-06-03 15:16:16.439961

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '55c3dc1dbae0'
down_revision: Union[str, None] = '9f8e7d6c5b4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('knowledge_templates',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('source_key', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('subcategory', sa.String(length=100), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('popularity', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('knowledge_templates_pkey'))
    )
    op.create_index(op.f('knowledge_templates_category_idx'), 'knowledge_templates', ['category'], unique=False)
    op.create_index(op.f('knowledge_templates_source_idx'), 'knowledge_templates', ['source'], unique=False)
    op.create_index(op.f('knowledge_templates_source_key_idx'), 'knowledge_templates', ['source_key'], unique=True)
    op.create_index(op.f('knowledge_templates_subcategory_idx'), 'knowledge_templates', ['subcategory'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('knowledge_templates_subcategory_idx'), table_name='knowledge_templates')
    op.drop_index(op.f('knowledge_templates_source_key_idx'), table_name='knowledge_templates')
    op.drop_index(op.f('knowledge_templates_source_idx'), table_name='knowledge_templates')
    op.drop_index(op.f('knowledge_templates_category_idx'), table_name='knowledge_templates')
    op.drop_table('knowledge_templates')
