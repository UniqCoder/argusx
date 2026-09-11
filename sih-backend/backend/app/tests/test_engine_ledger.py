"""
app/tests/test_engine_ledger.py — Layer 5 tamper-evident ledger tests.

Verifies the hash chain both confirms integrity when untouched and detects
tampering deterministically (first broken seq is reported, not just a bare
pass/fail) — see app/engine/ledger.py.
"""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine import ledger as ledger_engine
from app.models.engine import EvidenceLedgerEntry


@pytest.mark.asyncio
async def test_empty_chain_is_intact(db_session: AsyncSession):
    result = await ledger_engine.verify_chain(db_session)
    assert result.intact is True
    assert result.entries_checked == 0


@pytest.mark.asyncio
async def test_append_and_verify_intact_chain(db_session: AsyncSession):
    case_id = uuid.uuid4()
    await ledger_engine.append_entry(
        db_session, event_type="anchor_registered", payload={"a": 1}, actor="tester", case_id=case_id,
    )
    await ledger_engine.append_entry(
        db_session, event_type="trace_completed", payload={"b": 2}, actor="tester", case_id=case_id,
    )
    await ledger_engine.append_entry(
        db_session, event_type="decision_issued", payload={"c": 3}, actor="tester", case_id=case_id,
    )

    result = await ledger_engine.verify_chain(db_session, case_id=case_id)
    assert result.intact is True
    assert result.entries_checked == 3
    assert result.merkle_root is not None
    assert result.broken_at_seq is None


@pytest.mark.asyncio
async def test_chain_links_prev_hash_correctly(db_session: AsyncSession):
    e1 = await ledger_engine.append_entry(db_session, "evt1", {"x": 1}, "tester")
    e2 = await ledger_engine.append_entry(db_session, "evt2", {"x": 2}, "tester")
    assert e1.prev_hash == ledger_engine.GENESIS_HASH
    assert e2.prev_hash == e1.entry_hash
    assert e1.entry_hash != e2.entry_hash


@pytest.mark.asyncio
async def test_tampering_a_payload_is_detected(db_session: AsyncSession):
    """
    Mutate an already-appended entry's payload directly (bypassing the
    append-only API) and confirm verify_chain() catches it and reports
    exactly which seq broke.
    """
    case_id = uuid.uuid4()
    e1 = await ledger_engine.append_entry(db_session, "evt1", {"amount": 100}, "tester", case_id=case_id)
    await ledger_engine.append_entry(db_session, "evt2", {"amount": 200}, "tester", case_id=case_id)

    row = (await db_session.execute(
        select(EvidenceLedgerEntry).where(EvidenceLedgerEntry.seq == e1.seq)
    )).scalar_one()
    row.payload = {"amount": 999999}  # tamper: attacker inflates/deflates a recorded amount
    await db_session.commit()

    result = await ledger_engine.verify_chain(db_session, case_id=case_id)
    assert result.intact is False
    assert result.broken_at_seq == e1.seq


@pytest.mark.asyncio
async def test_deleting_a_row_breaks_the_chain(db_session: AsyncSession):
    """Deleting a row breaks the surviving next row's prev_hash link."""
    case_id = uuid.uuid4()
    e1 = await ledger_engine.append_entry(db_session, "evt1", {"x": 1}, "tester", case_id=case_id)
    e2 = await ledger_engine.append_entry(db_session, "evt2", {"x": 2}, "tester", case_id=case_id)

    await db_session.delete(
        (await db_session.execute(
            select(EvidenceLedgerEntry).where(EvidenceLedgerEntry.seq == e1.seq)
        )).scalar_one()
    )
    await db_session.commit()

    result = await ledger_engine.verify_chain(db_session, case_id=case_id)
    assert result.intact is False
    assert result.broken_at_seq == e2.seq
