"""
app/services/scenarios/seeder.py — Writes the seeded scenarios into Postgres
and the Redis risk registry.

What gets written, and why each row matters:

  complaints          the NCRP/SAHYOG filings themselves
  wallets             one row per address a complaint names
  complaint_wallets   THE junction table. Cross-victim correlation reads
                      exactly this; without it POST /api/v1/correlate returns
                      correlation_score 0.0 for every wallet that exists and
                      404 for every wallet that does not. Before this seeder,
                      the only writer in the entire repository was
                      scripts/generate_synthetic_ncrp.py.
  cases               one investigation case per scenario
  case_wallets        links the case to the reported wallet
  anchors             a Class-A LEGAL_COMPLAINT anchor per scenario, so the
                      trace has ground truth and a `block` decision is even
                      structurally possible (ck_block_requires_anchor)
  redis risk:*        so Deposit Watch returns a real score with a real reason

The seeder is idempotent: running it twice produces the same rows, because
every natural key (ncrp_ref, address+chain, anchor source_ref) is looked up
before insert.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case, CaseWallet
from app.models.complaint import Complaint, ComplaintWallet
from app.models.engine import Anchor
from app.models.wallet import Wallet
from app.schemas.common import CaseStatus
from app.services import registry_service
from app.services.scenarios.definitions import ALL_SCENARIOS, Scenario

logger = structlog.get_logger(__name__)

SEED_INVESTIGATOR = "investigator@i4c.gov.in"
ANCHOR_TTL_DAYS = 365


async def _get_or_create_wallet(db: AsyncSession, address: str, chain: str) -> Wallet:
    res = await db.execute(
        select(Wallet).where(Wallet.address == address, Wallet.chain == chain)
    )
    wallet = res.scalar_one_or_none()
    if wallet is None:
        wallet = Wallet(address=address, chain=chain)
        db.add(wallet)
        await db.flush()
    return wallet


async def seed_scenario(db: AsyncSession, scenario: Scenario) -> dict[str, str]:
    """Seed one scenario. Returns the ids a caller might want to print."""
    base = scenario.started_at

    # ── The case ────────────────────────────────────────────────────────────
    anchor_ref = f"scenario:{scenario.key}"
    existing_anchor = await db.execute(
        select(Anchor).where(Anchor.source_ref == anchor_ref)
    )
    anchor = existing_anchor.scalar_one_or_none()

    if anchor is not None:
        case_id = anchor.case_id
    else:
        case = Case(
            status=CaseStatus.investigating.value,
            assigned_investigator=SEED_INVESTIGATOR,
            opened_at=base + timedelta(minutes=180),
        )
        db.add(case)
        await db.flush()
        case_id = case.id

    reported_wallet = await _get_or_create_wallet(
        db, scenario.anchor_address, scenario.anchor_chain.value
    )

    link = await db.execute(
        select(CaseWallet).where(
            CaseWallet.case_id == case_id, CaseWallet.wallet_id == reported_wallet.id
        )
    )
    if link.scalar_one_or_none() is None:
        db.add(CaseWallet(case_id=case_id, wallet_id=reported_wallet.id))

    # ── The complaints, and the junction rows correlation actually reads ────
    for comp in scenario.complaints:
        found = await db.execute(
            select(Complaint).where(Complaint.ncrp_ref == comp.ncrp_ref)
        )
        complaint = found.scalar_one_or_none()
        if complaint is None:
            complaint = Complaint(
                id=uuid.uuid4(),
                ncrp_ref=comp.ncrp_ref,
                source_platform=comp.source_platform,
                narrative_text=comp.narrative,
                fraud_typology=comp.fraud_typology,
                amount_lost=comp.amount_lost_inr,
                filed_at=base + timedelta(minutes=comp.filed_minute),
                state=comp.state,
                district=comp.district,
            )
            db.add(complaint)
            await db.flush()

        named = await _get_or_create_wallet(
            db, comp.reported_address, comp.reported_chain.value
        )
        junction = await db.execute(
            select(ComplaintWallet).where(
                ComplaintWallet.complaint_id == complaint.id,
                ComplaintWallet.wallet_id == named.id,
            )
        )
        if junction.scalar_one_or_none() is None:
            db.add(
                ComplaintWallet(
                    complaint_id=complaint.id,
                    wallet_id=named.id,
                    reported_at=base + timedelta(minutes=comp.filed_minute),
                )
            )

    # ── The Class-A anchor ──────────────────────────────────────────────────
    # Class A because a filed NCRP/SAHYOG complaint is a legal attestation, not
    # an analyst's hypothesis. This is what makes a `block` decision reachable
    # at all; nothing this system computes can ever produce one of these.
    if anchor is None:
        first = scenario.complaints[0]
        db.add(
            Anchor(
                case_id=case_id,
                address=scenario.anchor_address,
                chain=scenario.anchor_chain.value,
                attestation_class="A",
                attestation_type="LEGAL_COMPLAINT",
                source_ref=anchor_ref,
                asserted_by=SEED_INVESTIGATOR,
                asserted_at=base + timedelta(minutes=first.filed_minute),
                victim_amount_inr=scenario.victim_amount_inr,
                evidence_uri=None,
                system_generated=False,
            )
        )

    await db.commit()

    logger.info(
        "scenario_seeded",
        scenario=scenario.key,
        case_id=str(case_id),
        complaints=len(scenario.complaints),
        transactions=len(scenario.txs),
    )
    return {"scenario": scenario.key, "case_id": str(case_id)}


async def seed_risk_registry(scenario: Scenario, redis_client=None) -> int:
    """
    Seed the Redis entries Deposit Watch reads.

    These are deterministic, human-written assessments tied to a filed
    complaint — never a model output. `reason` is stored alongside the score so
    the deposit verdict can say *why* instead of showing a bare number, which is
    the single biggest complaint about that screen.
    """
    for entry in scenario.risk_entries:
        await registry_service.set_risk_entry(
            redis_client=redis_client,
            chain=entry.chain.value,
            address=entry.address,
            score=entry.score,
            tier=entry.tier,
            case_ref=scenario.complaints[0].ncrp_ref,
            ttl=ANCHOR_TTL_DAYS * 24 * 3600,
            source="seeded_scenario",
            designation={"reason": entry.reason, "scenario": scenario.key},
        )
    return len(scenario.risk_entries)


async def seed_all(db: AsyncSession, redis_client=None) -> list[dict[str, str]]:
    results = []
    for scenario in ALL_SCENARIOS:
        results.append(await seed_scenario(db, scenario))
        await seed_risk_registry(scenario, redis_client=redis_client)
    return results
