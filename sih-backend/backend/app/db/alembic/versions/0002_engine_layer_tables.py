"""ARGUS v2 provenance engine: anchors, traces, taint_nodes, evidence_ledger, decisions

Revision ID: 0002_engine_layer_tables
Revises: 0001_phase1_tables
Create Date: 2026-09-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0002_engine_layer_tables'
down_revision: Union[str, None] = '0001_phase1_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Anchors (Layer 0) ──────────────────────────────────────────────────────
    op.create_table(
        'anchors',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('address', sa.String(), nullable=False),
        sa.Column('chain', sa.String(), nullable=False),
        sa.Column('attestation_class', sa.String(length=1), nullable=False),
        sa.Column('attestation_type', sa.String(), nullable=False),
        sa.Column('source_ref', sa.String(), nullable=False),
        sa.Column('asserted_by', sa.String(), nullable=False),
        sa.Column('asserted_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('victim_amount_inr', sa.NUMERIC(precision=14, scale=2), nullable=True),
        sa.Column('evidence_uri', sa.String(), nullable=True),
        sa.Column('system_generated', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('address', 'chain', 'source_ref', name='uq_anchor_addr_chain_source'),
        sa.CheckConstraint("attestation_class IN ('A','B','C')", name='ck_anchor_attestation_class'),
        sa.CheckConstraint("system_generated = false", name='ck_anchor_never_system_generated'),
    )

    # ── Traces (Layer 1) ───────────────────────────────────────────────────────
    op.create_table(
        'traces',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('anchor_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('method', sa.String(), server_default='haircut', nullable=False),
        sa.Column('dilution_floor', sa.NUMERIC(precision=6, scale=5), server_default='0.005', nullable=False),
        sa.Column('max_hops', sa.SmallInteger(), server_default='6', nullable=False),
        sa.Column('max_nodes', sa.SmallInteger(), server_default='200', nullable=False),
        sa.Column('started_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('node_count', sa.SmallInteger(), nullable=True),
        sa.Column('reproducible_hash', sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(['anchor_id'], ['anchors.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── Taint nodes (Layer 1 output) ───────────────────────────────────────────
    op.create_table(
        'taint_nodes',
        sa.Column('trace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('address', sa.String(), nullable=False),
        sa.Column('chain', sa.String(), nullable=False),
        sa.Column('hop', sa.SmallInteger(), nullable=False),
        sa.Column('taint_fraction', sa.NUMERIC(precision=6, scale=5), nullable=False),
        sa.Column('tainted_value', sa.NUMERIC(precision=24, scale=8), nullable=False),
        sa.Column('tainted_inr', sa.NUMERIC(precision=14, scale=2), nullable=True),
        sa.Column('terminal_kind', sa.String(), nullable=True),
        sa.Column('entity_name', sa.String(), nullable=True),
        sa.Column('entity_jurisdiction', sa.String(), nullable=True),
        sa.Column('proof_path', sa.JSON(), nullable=False),
        sa.Column('first_tainted_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['trace_id'], ['traces.id']),
        sa.PrimaryKeyConstraint('trace_id', 'address', 'chain'),
    )
    op.create_index('idx_taint_nodes_terminal', 'taint_nodes', ['terminal_kind'])

    # ── Evidence ledger (Layer 5 — tamper-evident hash chain) ─────────────────
    op.create_table(
        'evidence_ledger',
        sa.Column('seq', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('actor', sa.String(), nullable=False),
        sa.Column('occurred_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('prev_hash', sa.String(length=64), nullable=False),
        sa.Column('entry_hash', sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint('seq'),
        sa.UniqueConstraint('entry_hash'),
    )
    op.create_index('idx_evidence_ledger_case', 'evidence_ledger', ['case_id'])

    # ── Decisions (Layer 5 — three-tier action, DB-enforced block guard) ──────
    op.create_table(
        'decisions',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('address', sa.String(), nullable=False),
        sa.Column('chain', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('basis_anchor_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('basis_trace_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('ml_contributed', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('reasoning', sa.Text(), nullable=False),
        sa.Column('decided_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('released_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['basis_anchor_id'], ['anchors.id']),
        sa.ForeignKeyConstraint(['basis_trace_id'], ['traces.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("action IN ('monitor','hold_for_review','block')", name='ck_decision_action'),
        sa.CheckConstraint(
            "action <> 'block' OR (basis_anchor_id IS NOT NULL AND basis_trace_id IS NOT NULL)",
            name='ck_block_requires_anchor',
        ),
    )


def downgrade() -> None:
    op.drop_table('decisions')
    op.drop_index('idx_evidence_ledger_case', table_name='evidence_ledger')
    op.drop_table('evidence_ledger')
    op.drop_index('idx_taint_nodes_terminal', table_name='taint_nodes')
    op.drop_table('taint_nodes')
    op.drop_table('traces')
    op.drop_table('anchors')
