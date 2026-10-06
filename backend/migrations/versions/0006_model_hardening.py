"""Phase 6.1 model hardening: event lineage, research acceptance links, evidence replacements, MCP approvals

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('simulation_events') as b:
        b.add_column(sa.Column('lineage', sa.JSON(), nullable=True))
    with op.batch_alter_table('candidate_evidence') as b:
        b.add_column(sa.Column('accepted_as', sa.String(length=20), nullable=True))
        b.add_column(sa.Column('reviewed_scope', sa.JSON(), nullable=True))
        b.add_column(sa.Column('links', sa.JSON(), nullable=True))
    op.create_table('evidence_replacements',
                    sa.Column('id', sa.String(length=80), primary_key=True),
                    sa.Column('episode_id', sa.String(length=80), sa.ForeignKey('episodes.id', ondelete='CASCADE'), nullable=False, index=True),
                    sa.Column('candidate_id', sa.String(length=80), nullable=False),
                    sa.Column('target_kind', sa.String(length=12), nullable=False),
                    sa.Column('target_id', sa.String(length=120), nullable=False),
                    sa.Column('message', sa.Text(), nullable=False),
                    sa.Column('status', sa.String(length=16), nullable=False),
                    sa.Column('new_snapshot_id', sa.String(length=80), nullable=True),
                    sa.Column('new_run_id', sa.String(length=80), nullable=True),
                    sa.Column('created_at', sa.String(length=40), nullable=False),
                    sa.Column('resolved_at', sa.String(length=40), nullable=True))
    op.create_table('mcp_approvals',
                    sa.Column('id', sa.String(length=80), primary_key=True),
                    sa.Column('tool', sa.String(length=60), nullable=False),
                    sa.Column('arguments', sa.JSON(), nullable=False),
                    sa.Column('status', sa.String(length=12), nullable=False),
                    sa.Column('result', sa.JSON(), nullable=True),
                    sa.Column('created_at', sa.String(length=40), nullable=False),
                    sa.Column('decided_at', sa.String(length=40), nullable=True))


def downgrade():
    op.drop_table('mcp_approvals')
    op.drop_table('evidence_replacements')
    with op.batch_alter_table('candidate_evidence') as b:
        b.drop_column('links')
        b.drop_column('reviewed_scope')
        b.drop_column('accepted_as')
    with op.batch_alter_table('simulation_events') as b:
        b.drop_column('lineage')
