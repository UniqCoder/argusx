"""Initial schema for Unigraph: complaints, wallets, complaint_wallets, cases, case_wallets, alerts, audit_log

Revision ID: 0001_phase1_tables
Revises: 
Create Date: 2026-08-28 15:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001_phase1_tables'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Complaints table ───────────────────────────────────────────────────────
    op.create_table(
        'complaints',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('ncrp_ref', sa.String(), nullable=True),
        sa.Column('source_platform', sa.String(), nullable=False),
        sa.Column('complainant_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('narrative_text', sa.Text(), nullable=True),
        sa.Column('fraud_typology', sa.String(), nullable=True),
        sa.Column('amount_lost', sa.NUMERIC(precision=14, scale=2), nullable=True),
        sa.Column('filed_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('state', sa.String(), nullable=True),
        sa.Column('district', sa.String(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ncrp_ref')
    )

    # ── Wallets table ──────────────────────────────────────────────────────────
    op.create_table(
        'wallets',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('address', sa.String(), nullable=False),
        sa.Column('chain', sa.String(), nullable=False),
        sa.Column('first_seen', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('last_seen', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('risk_score', sa.NUMERIC(precision=4, scale=3), nullable=True),
        sa.Column('risk_tier', sa.String(), nullable=True),
        sa.Column('vasp_identified', sa.String(), nullable=True),
        sa.Column('cluster_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('address', 'chain', name='uq_wallets_address_chain')
    )
    op.create_index('idx_wallets_risk_tier', 'wallets', ['risk_tier'], unique=False)

    # ── Complaint_wallets junction (powers USP 1) ─────────────────────────────
    op.create_table(
        'complaint_wallets',
        sa.Column('complaint_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('wallet_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('reported_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['complaint_id'], ['complaints.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['wallet_id'], ['wallets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('complaint_id', 'wallet_id')
    )

    # ── Cases table ────────────────────────────────────────────────────────────
    op.create_table(
        'cases',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('status', sa.String(), server_default='new', nullable=False),
        sa.Column('assigned_investigator', sa.String(), nullable=True),
        sa.Column('opened_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('closed_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # ── Case_wallets junction ──────────────────────────────────────────────────
    op.create_table(
        'case_wallets',
        sa.Column('case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('wallet_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['wallet_id'], ['wallets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('case_id', 'wallet_id')
    )

    # ── Alerts table ───────────────────────────────────────────────────────────
    op.create_table(
        'alerts',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('wallet_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('triggered_by', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('resolved_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['wallet_id'], ['wallets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # ── Audit log table ────────────────────────────────────────────────────────
    op.create_table(
        'audit_log',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('actor', sa.String(), nullable=True),
        sa.Column('action', sa.String(), nullable=True),
        sa.Column('entity', sa.String(), nullable=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('timestamp', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('audit_log')
    op.drop_table('alerts')
    op.drop_table('case_wallets')
    op.drop_table('cases')
    op.drop_table('complaint_wallets')
    op.drop_index('idx_wallets_risk_tier', table_name='wallets')
    op.drop_table('wallets')
    op.drop_table('complaints')
