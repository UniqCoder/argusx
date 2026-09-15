"""
app/services/risk_service.py — ML risk scoring service and SHAP evidence generation.

Calculates risk score, assigns risk tier, and extracts explainable evidence for wallets.
"""
import hashlib
import structlog
from datetime import datetime, timezone
from typing import Optional
import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.explain import explain_wallet_risk
from app.ml.features import (
    FEATURE_COLUMNS,
    FEATURE_SCHEMA_VERSION,
    GSAGE_EMBEDDING_COLUMNS,
    MODEL_FEATURE_COLUMNS,
    compute_feature_vector,
)
from app.ml.model import get_model_version, map_score_to_tier, predict_risk_score
from app.ml.relative_features import relative_reference_state
from app.models.engine import Anchor, TaintNode, Trace
from app.schemas.common import Chain, RiskTier
from app.schemas.engine import TerminalKind
from app.schemas.wallet import RiskEvidence, RiskResponse
from app.schemas.common import EvidenceDirection
from app.services import complaint_service, registry_service, sanctions_service
from app.services import osint_service
from app.services.explorers.base import ExplorerUnavailableError
from app.services.explorers.btc_explorer import BitcoinExplorer
from app.services.explorers.eth_explorer import EthereumExplorer
from app.services.explorers.tron_explorer import TronExplorer
from app.services.scenarios.definitions import is_scenario_address
from app.services.scenarios.fixture_explorer import fixture_explorer_for
from app.services.tracing_service import get_or_create_wallet

logger = structlog.get_logger(__name__)

# ── Promoted ML classification decision threshold (92f config, docs/ml.md) ──
# Locked on the combined model's validation slice to satisfy the <2% FPR policy
# cap. The original <1% FPR project target is achievable on this config with a
# stricter override at 0.85 (documented operating-point tradeoff in docs/ml.md);
# scores below this threshold are treated as NOT flagged.
RISK_FLAG_THRESHOLD = 0.70

# ── Complaint corroboration bonus ───────────────────────────────────────────
# Independent victims naming the SAME wallet is real, direct evidence the ML
# behavioral model has no way to see on its own — it only ever looks at one
# address's own transaction shape. This is additive, not a floor/override
# like sanctions: a wallet with 3 complaints AND a low behavioral score still
# only gets a moderate bump, because complaints alone (before verification)
# are real but not infallible evidence, unlike an official OFAC designation.
COMPLAINT_BONUS = {0: 0.0, 1: 0.05, 2: 0.15}
COMPLAINT_BONUS_MAX = 0.30  # 3 or more complaints

# The combined ceiling on how much the complaint + mixer + typology bonuses
# may add to ml_score TOGETHER. Each one alone is reasonable (0.05-0.30), but
# summed independently they could reach 0.80 — enough to push almost any
# ml_score to the 1.0 clamp, producing a flat, meaningless-looking 100/100
# regardless of what the model actually found. Reaching CRITICAL should still
# require either an official sanctions match or the behavioral model's own
# score contributing real weight, not corroboration bonuses alone stacking
# to the ceiling. See the scaling logic in evaluate_wallet_risk.
EXTRA_EVIDENCE_BONUS_CAP = 0.35


def complaint_corroboration_bonus(complaint_count: int) -> float:
    return COMPLAINT_BONUS.get(complaint_count, COMPLAINT_BONUS_MAX)


# 3+ independent complaints is, by itself, presumptively HIGH risk — the
# same "several victims independently converged on one address" signal the
# taint engine already calls its strongest attribution (see PRIMARY_SUSPECT
# in app/engine/taint.py). This is a floor, not a replacement for the model
# score, mirroring exactly how SANCTIONS_SCORE_FLOOR works in
# sanctions_service.py — just one tier lower, because a filed complaint is
# an unverified victim report, not an official government designation. Below
# 3 complaints there is no floor at all; only the additive bonus above
# applies, so 1-2 complaints alone never forces a tier.
COMPLAINT_HIGH_FLOOR_COUNT = 3
COMPLAINT_SCORE_FLOOR = 0.60  # aligned to map_score_to_tier's HIGH boundary


# A score crossing 0.85 used to read as CRITICAL on the strength of a SINGLE
# model feature swing — no independent corroboration required. That let one
# unusual-but-explainable behavioral pattern alone earn the platform's most
# severe label, which is exactly what "we need strong evidence for that"
# means an investigator can't act on with confidence. CRITICAL now requires
# either genuine corroboration (2+ independent complaints, since 1 alone is
# gated as only a partial bonus above) or a model score so extreme (>=0.93,
# not just >=0.85) that the behavioral signal is doing the corroborating
# itself. Anything else that clears 0.85 is still shown as HIGH — visible,
# actionable, but not asserted as certain.
CRITICAL_CORROBORATION_FLOOR = 0.93


def gate_tier(score: float, tier: RiskTier, corroborated: bool) -> RiskTier:
    if tier == RiskTier.critical and not corroborated and score < CRITICAL_CORROBORATION_FLOOR:
        return RiskTier.high
    return tier


# ── Mixer-exposure signal ────────────────────────────────────────────────────
# The behavioral model only ever looks at THIS address's own transaction shape
# — it has no way to know that Layer 1 (app/engine/taint.py) already traced
# this exact wallet's own outgoing funds to a named mixer contract (Tornado
# Cash and friends, app/engine/registries.py). That is real, deterministic,
# already-computed on-chain evidence sitting unused in the traces/taint_nodes
# tables: a wallet whose own money is PROVEN to reach a known laundering
# conduit is not "clean" just because its raw value/tx-count stats look like
# a normal high-volume address (see the two ETH demo wallets that showed
# 0.01-0.05/100 despite tracing straight to Tornado Cash — the model was
# never shown that fact). Additive bonus (real but heuristic terminal
# classification, not an official designation) plus a HIGH floor — same
# tier as 3+ complaints, one tier under sanctions, because "this address's
# funds reached a mixer" is on-chain fact, stronger than an unverified
# complaint but not a government designation on THIS wallet itself.
MIXER_EXPOSURE_BONUS = 0.20
MIXER_EXPOSURE_SCORE_FLOOR = 0.60


async def get_mixer_exposure(db: AsyncSession, address: str, chain: str) -> Optional[dict]:
    """
    The nearest MIXER_BOUNDARY terminal in this wallet's own most recent
    trace (as anchor), if any — real evidence from a real, already-persisted
    Layer 1 run, not re-computed here and never fabricated when no trace has
    been run for this wallet yet (returns None, exactly like "no complaints").
    """
    stmt = (
        select(TaintNode.entity_name, TaintNode.hop)
        .join(Trace, Trace.id == TaintNode.trace_id)
        .join(Anchor, Anchor.id == Trace.anchor_id)
        .where(
            func.lower(Anchor.address) == address.strip().lower(),
            Anchor.chain == chain,
            TaintNode.terminal_kind == TerminalKind.MIXER_BOUNDARY.value,
        )
        .order_by(Trace.started_at.desc(), TaintNode.hop.asc())
        .limit(1)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        return None
    return {"entity_name": row[0], "hop": row[1]}


# ── Laundering-pattern (typology) exposure ──────────────────────────────────
# Layer 2 (app/engine/typologies.py) already names concrete laundering
# patterns on a wallet's own trace — funds cashed out within minutes of
# arriving ("consistent with a pre-arranged cash-out", in its own words), one
# wallet fanning out to a dozen others, an entire chain moving in an
# implausible few minutes. That file's own docstring is explicit that it
# never computes a score itself (so it can never touch the decision engine's
# Class-A-anchor-required block rule — see IMPROVEMENTS_PLANNED.md's
# rejection of a fused "block" score). But nothing stops the risk score
# (Layer 4, which can only ever suggest hold_for_review, same ceiling as
# everything else here) from reading that same real, already-persisted
# narrative — which it was not doing, so wallets with a textbook rapid
# cash-out or a fan-out to a dozen mule addresses scored LOW purely because
# the ML model's own transaction-shape features didn't happen to look
# unusual. Only the higher-confidence behavioral codes count here — plain
# multi-hop layering and a bridge crossing are common in legitimate use too
# and are deliberately left out.
QUALIFYING_TYPOLOGY_CODES = {
    "RAPID_TO_EXCHANGE",
    "RAPID_MOVEMENT",
    "FAN_OUT",
    "STRUCTURING",
    "PEEL_CHAIN",
    "DORMANT_BURST",
    "CROSS_VICTIM_CONVERGENCE",
}
TYPOLOGY_BONUS_PER_CODE = 0.10
TYPOLOGY_BONUS_MAX = 0.30
# Floor kicks in once two independent patterns stack — one alone (like one
# complaint) is real but not presumptively strong enough on its own.
TYPOLOGY_FLOOR_MIN_CODES = 2
TYPOLOGY_SCORE_FLOOR = 0.60


async def get_typology_exposure(db: AsyncSession, address: str, chain: str) -> list[dict]:
    """
    The qualifying laundering-pattern codes on this wallet's own most recent
    trace, read straight from the persisted Trace.typologies JSON that
    app/engine/typologies.py already wrote — not re-detected here, and empty
    (never fabricated) when no trace has been run for this wallet yet.
    """
    stmt = (
        select(Trace.typologies)
        .join(Anchor, Anchor.id == Trace.anchor_id)
        .where(func.lower(Anchor.address) == address.strip().lower(), Anchor.chain == chain)
        .order_by(Trace.started_at.desc())
        .limit(1)
    )
    row = (await db.execute(stmt)).first()
    if row is None or not row[0]:
        return []
    return [t for t in row[0] if t.get("code") in QUALIFYING_TYPOLOGY_CODES]


btc_explorer = BitcoinExplorer()
eth_explorer = EthereumExplorer()
tron_explorer = TronExplorer()


async def evaluate_wallet_risk(
    db: AsyncSession,
    address: str,
    chain: Chain,
) -> RiskResponse:
    """
    Evaluate on-chain ML risk score and SHAP evidence for a given wallet address.
    """
    # ── Sanctions interception (USP 2) ─────────────────────────────────────────
    # Looked up BEFORE any DB/explorer/ML work (cheap, no network for the
    # committed seed) so we know up front whether this address needs the
    # sanctions floor blended in below. It no longer short-circuits: a flat
    # score=1.0 for every match discarded the actual computed ML behavior,
    # so a legitimate low-activity wallet and a high-volume mixer relay both
    # showed the exact same "100" with no real evidence behind the number.
    # The ML pipeline still runs; see the blend at the bottom of this function.
    sanction = sanctions_service.lookup_sanctioned(chain, address)
    if not sanction:
        try:
            sanction = await sanctions_service.lookup_registry_designation(
                registry_service.get_redis_client(), chain, address
            )
        except Exception:  # noqa: BLE001 — registry consult must never break scoring
            sanction = None

    wallet = await get_or_create_wallet(db, address, chain)

    # How many independent complaints name this exact wallet — real evidence
    # the behavioral model can't see. Cheap single COUNT(*), computed up
    # front so it's available for both the score blend and the tier gate
    # below, and for the corroboration evidence item.
    complaint_count = await complaint_service.complaint_count_for(db, address, chain.value)

    # Does this wallet's own already-persisted trace reach a known mixer?
    # See MIXER_EXPOSURE_BONUS above for why this matters and how it's used.
    mixer_exposure = await get_mixer_exposure(db, address, chain.value)

    # Does this wallet's own already-persisted trace exhibit a real laundering
    # pattern (rapid cash-out, fan-out, structuring, ...)? See
    # QUALIFYING_TYPOLOGY_CODES above.
    typology_exposure = await get_typology_exposure(db, address, chain.value)

    # 1. Fetch transactions. Seeded-scenario addresses (app/services/scenarios/)
    #    are answered from the same local fixture the taint engine already uses
    #    for them (app/engine/taint.py's `_explorer_for` does this exact check) —
    #    NOT the live public explorer. Before this fix, every demo wallet hit a
    #    live Etherscan/Tronscan/blockchain.info lookup for an address that has
    #    never existed on the real chain, which always came back empty
    #    (tx_events=0). An almost-all-zero feature vector isn't "no risk
    #    signal" to this model — sparse/short history is itself a common
    #    illicit-wallet pattern in the training data — so EVERY seeded demo
    #    wallet was scoring artificially high from missing data, not real
    #    evidence, regardless of which scenario it belonged to. Real (live)
    #    wallets were never affected; this only changes seeded ones.
    #    Explorer outage is NOT the same as a wallet with confirmed-empty
    #    history: outages surface as "unknown", never scored — unless the
    #    address is independently sanctioned, in which case the sanctions
    #    signal alone (no ML to blend with) still stands.
    try:
        if is_scenario_address(address, chain.value):
            fixture = fixture_explorer_for(chain.value)
            txs = await fixture.get_transactions(address, limit=25) if fixture else []
        elif chain == Chain.BTC:
            txs = await btc_explorer.get_transactions(address, limit=25)
        elif chain == Chain.ETH:
            txs = await eth_explorer.get_transactions(address, limit=25)
        elif chain == Chain.TRON:
            txs = await tron_explorer.get_transactions(address, limit=25)
        else:
            txs = []
    except ExplorerUnavailableError as exc:
        logger.error(
            "risk_fetch_failed",
            address=address,
            chain=chain.value,
            error=str(exc),
        )
        if sanction:
            return sanctions_service.build_sanctions_override_response(sanction)
        return RiskResponse(risk_score=None, risk_tier=RiskTier.unknown, evidence=[])

    # 2. Compute graph topology features from Neo4j (mode surfaced for logging)
    graph_feats: dict[str, float] | None = None
    graph_mode = "none"
    if chain in (Chain.BTC, Chain.ETH):
        try:
            from app.ml.live_graph_features import compute_live_graph_features_with_fallback
            graph_feats, graph_mode = await compute_live_graph_features_with_fallback(address, chain.value)
        except Exception:
            logger.debug("graph_features_unavailable", address=address, chain=chain.value)
            graph_feats = None
            graph_mode = "failed"

    # 3. Extract the full 92-column vector through the exact promoted feature path.
    #    Embedding mode is explicit: "full" / "fallback" (zero, legit) / "failed".
    try:
        from app.ml.embedding_store import get_live_embeddings
        embedding, embedding_mode = await get_live_embeddings(address, chain.value)
    except Exception as exc:
        embedding_mode = "failed"
        logger.error(
            "embedding_lookup_failed",
            address=address,
            chain=chain.value,
            error=str(exc),
        )
        embedding = np.zeros((len(GSAGE_EMBEDDING_COLUMNS),), dtype=np.float32)

    relative_mode = relative_reference_state()

    # 3-5. Feature extraction, model inference, SHAP evidence. The ML model
    #    artifact is lazily loaded here (get_model() even attempts a retrain
    #    from /data/processed when the joblib file is absent) — in an
    #    environment without provisioned artifacts that raised FileNotFoundError
    #    straight out of this function and surfaced as a generic HTTP 500, even
    #    though the API contract for "cannot score" is risk_score=None /
    #    risk_tier=unknown. Missing/unreadable artifacts are an environment
    #    condition, not a server fault: degrade to the unknown tier like the
    #    explorer-outage path above. NEVER fabricate a score instead.
    try:
        model_vector = compute_feature_vector(
            address, chain.value, txs, graph_features=graph_feats, embedding=embedding
        )
        assert model_vector.shape[1] == len(MODEL_FEATURE_COLUMNS), (
            f"model vector width {model_vector.shape[1]} != {len(MODEL_FEATURE_COLUMNS)}"
        )
        emb_block = model_vector[0, len(FEATURE_COLUMNS) : len(FEATURE_COLUMNS) + len(GSAGE_EMBEDDING_COLUMNS)]
        assert np.array_equal(emb_block, embedding), (
            "embedding not in [tabular, tabular+16) slots — model column-order regression"
        )

        # Snapshot identity: a content hash of the EXACT model input (the
        # literal bytes the model scored) plus the evidence that isn't part
        # of that vector (complaint count, sanction match) and the model
        # artifact's own version. Two calls with identical evidence — same
        # on-chain data, same complaint count, same model — always produce
        # the same snapshot_id and therefore the same score; new on-chain
        # activity, a new complaint, or a model promotion changes the vector
        # or one of these inputs and legitimately changes the snapshot_id
        # (and, generally, the score) along with it.
        model_version = get_model_version()
        snapshot_id = hashlib.sha256(
            model_vector.tobytes()
            + (
                f"|{complaint_count}|{bool(sanction)}|{bool(mixer_exposure)}"
                f"|{sorted(t['code'] for t in typology_exposure)}"
                f"|{model_version}|{FEATURE_SCHEMA_VERSION}"
            ).encode()
        ).hexdigest()[:16]

        # 4. Model inference. 4 decimal places, not 3 — a genuinely low-risk
        #    wallet can legitimately score e.g. 0.00033, and rounding that to
        #    3 places collapses it to a bare 0.000. The UI needs the real
        #    (small but nonzero) number to tell "the model computed a
        #    near-zero score" apart from "nothing was computed".
        ml_score = round(predict_risk_score(model_vector), 4)

        # 5. SHAP explainability. One fewer ML factor is shown per piece of
        #    non-ML evidence added below (sanctions, complaint corroboration)
        #    so the panel always tops out at 5 factors total, never 5 ML
        #    factors plus extras bolted on past that.
        extra_evidence_slots = (
            (1 if sanction else 0)
            + (1 if complaint_count > 0 else 0)
            + (1 if mixer_exposure else 0)
            + (1 if typology_exposure else 0)
        )
        evidence = explain_wallet_risk(model_vector, top_k=max(1, 5 - extra_evidence_slots))

        # ── Corroboration bonuses: complaint + mixer + typology, combined ──
        # Each of these three signals is real, but they were added to the
        # score independently, one after another, each re-clamped to 1.0 on
        # its own. Stack 3+ complaints (+0.30) with mixer exposure (+0.20)
        # and two laundering patterns (+0.20) on top of even a modest ml_score
        # and the total blows past 1.0 and clamps to a flat, suspicious-
        # looking 100/100 — exactly the kind of manufactured-looking ceiling
        # value this project has otherwise gone out of its way to avoid (see
        # the sanctions blend below, which floors at 0.95, never hardcodes
        # 1.0). Fixed by capping the COMBINED additive bonus from these three
        # non-ML signals together, then scaling each one's displayed
        # contribution by the same factor so the evidence panel's numbers
        # always sum to exactly what was actually applied — never a bigger
        # number quietly discarded by the clamp.
        raw_bonuses: dict[str, float] = {}
        if complaint_count > 0:
            raw_bonuses["complaint"] = complaint_corroboration_bonus(complaint_count)
        if mixer_exposure:
            raw_bonuses["mixer"] = MIXER_EXPOSURE_BONUS
        typo_codes: set[str] = {t["code"] for t in typology_exposure}
        if typology_exposure:
            raw_bonuses["typology"] = min(TYPOLOGY_BONUS_MAX, TYPOLOGY_BONUS_PER_CODE * len(typo_codes))

        raw_total = sum(raw_bonuses.values())
        scale = min(1.0, EXTRA_EVIDENCE_BONUS_CAP / raw_total) if raw_total > 0 else 1.0
        applied_bonuses = {k: round(v * scale, 4) for k, v in raw_bonuses.items()}

        boosted_score = round(min(1.0, ml_score + sum(applied_bonuses.values())), 4)

        # Floors are a separate, bounded statement ("this evidence alone is
        # presumptively at least HIGH") — not part of the additive stack, so
        # they're unaffected by the cap above and can't compound with it.
        if complaint_count >= COMPLAINT_HIGH_FLOOR_COUNT:
            boosted_score = round(max(boosted_score, COMPLAINT_SCORE_FLOOR), 4)
        if mixer_exposure:
            boosted_score = round(max(boosted_score, MIXER_EXPOSURE_SCORE_FLOOR), 4)
        if len(typo_codes) >= TYPOLOGY_FLOOR_MIN_CODES:
            boosted_score = round(max(boosted_score, TYPOLOGY_SCORE_FLOOR), 4)

        if "complaint" in applied_bonuses:
            evidence = [
                RiskEvidence(
                    feature_name="victim_complaint_corroboration",
                    contribution=applied_bonuses["complaint"],
                    direction=EvidenceDirection.increases_risk,
                    detail=(
                        f"{complaint_count} independent complaint"
                        f"{'s' if complaint_count != 1 else ''} "
                        f"{'name' if complaint_count != 1 else 'names'} this exact "
                        "wallet as the address funds were sent to."
                    ),
                ),
                *evidence,
            ]
        if "mixer" in applied_bonuses:
            hop = mixer_exposure["hop"]  # type: ignore[index]
            evidence = [
                RiskEvidence(
                    feature_name="mixer_exposure",
                    contribution=applied_bonuses["mixer"],
                    direction=EvidenceDirection.increases_risk,
                    detail=(
                        f"This wallet's own traced funds reach {mixer_exposure['entity_name']}, "  # type: ignore[index]
                        f"a known mixer, {hop} hop{'s' if hop != 1 else ''} downstream."
                    ),
                ),
                *evidence,
            ]
        if "typology" in applied_bonuses:
            seen: set[str] = set()
            ordered_labels = []
            for t in typology_exposure:
                if t["label"] not in seen:
                    seen.add(t["label"])
                    ordered_labels.append(t["label"])
            evidence = [
                RiskEvidence(
                    feature_name="laundering_pattern_exposure",
                    contribution=applied_bonuses["typology"],
                    direction=EvidenceDirection.increases_risk,
                    detail=(
                        "This wallet's own traced flow exhibits: "
                        f"{'; '.join(ordered_labels)}."
                    ),
                ),
                *evidence,
            ]

        corroborated = (
            complaint_count >= 2
            or bool(mixer_exposure)
            or len(typo_codes) >= TYPOLOGY_FLOOR_MIN_CODES
        )

        if sanction:
            # Blend, don't overwrite: a confirmed OFAC match is a floor on
            # severity, not a replacement for what the model (and any
            # complaint corroboration) actually found. This is why the same
            # designation can show 0.95 for a dormant wallet and 0.99+ for
            # one that's also behaviorally active or complaint-corroborated —
            # the number is still doing real work, not just echoing the match.
            risk_score = round(max(boosted_score, sanctions_service.SANCTIONS_SCORE_FLOOR), 4)
            risk_tier = RiskTier.critical  # an official designation needs no further gating
            evidence = [sanctions_service.sanctions_evidence(sanction), *evidence]
            sanctions_service.log_sanctions_interception(sanction)
            corroborated = True
        else:
            risk_score = boosted_score
            risk_tier = gate_tier(risk_score, map_score_to_tier(risk_score), corroborated)
        flagged = risk_score >= RISK_FLAG_THRESHOLD
    except Exception as exc:  # noqa: BLE001 — scoring must degrade, never 500
        logger.error(
            "ml_artifacts_missing" if isinstance(exc, FileNotFoundError) else "ml_inference_failed",
            address=address,
            chain=chain.value,
            error=str(exc),
        )
        if sanction:
            return sanctions_service.build_sanctions_override_response(sanction)
        return RiskResponse(risk_score=None, risk_tier=RiskTier.unknown, evidence=[])

    # 6. Persist updated score & tier to PostgreSQL
    wallet.risk_score = risk_score
    wallet.risk_tier = risk_tier.value
    await db.commit()
    await db.refresh(wallet)

    # 6b. Structured OSINT corroboration (USP 2) — evidence-only. Queried best
    #     effort against the Redis-cached / in-memory sources; never blocks and
    #     never changes the scored tier. Hits append to evidence + response.osint.
    osint_hits: list = []
    try:
        osint_hits = await osint_service.lookup_address(
            chain, address, redis_client=registry_service.get_redis_client()
        )
    except Exception:  # noqa: BLE001 — OSINT must never break scoring
        osint_hits = []

    # Audit OBSERVABILITY (Group 1): model path state + a compact digest of the
    # model input. The raw (92,) vector itself is left out of the log (Group 2).
    embedding_block_zero = bool(np.all(emb_block == 0))
    vector_nonzero_fraction = round(float((np.abs(model_vector) > 1e-8).sum() / model_vector.size), 4)
    shap_top5 = [
        f"{e.feature_name}:{'+' if e.direction.value == 'increases_risk' else '-'}{e.contribution}"
        for e in evidence
    ]
    shap_evidence_count = len(evidence)
    osint_evidence = [h.to_risk_evidence() for h in osint_hits]
    all_evidence = [*evidence, *osint_evidence]

    logger.info(
        "wallet_risk_scored",
        address=address,
        chain=chain.value,
        score=risk_score,
        tier=risk_tier.value,
        flag_threshold=RISK_FLAG_THRESHOLD,
        flagged=flagged,
        tx_events=len(txs),
        graph_mode=graph_mode,
        embedding_mode=embedding_mode,
        embedding_block_zero=embedding_block_zero,
        vector_nonzero_fraction=vector_nonzero_fraction,
        relative_mode=relative_mode,
        shap_evidence_count=shap_evidence_count,
        osint_hit_count=len(osint_evidence),
        shap_top5=shap_top5,
        complaint_count=complaint_count,
        mixer_exposure=mixer_exposure,
        typology_codes=sorted(typo_codes),
        corroborated=corroborated,
        model_version=model_version,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        snapshot_id=snapshot_id,
    )

    risk_source = (
        "sanctions_blended"
        if sanction
        else "corroborated"
        if complaint_count > 0 or mixer_exposure or typology_exposure
        else "ml_model"
    )

    # Write through to the Redis registry that /check-wallet (Deposit Watch)
    # reads on its hot path. Before this, that registry was its own separate
    # source of truth — hand-seeded for demo scenarios, or simply never
    # populated for a real wallet — so the SAME address could show one score
    # on Risk Intelligence and a different, stale or fabricated one on
    # Deposit Watch, with no way for an investigator to know why they
    # disagreed. This is the one and only computation that decides a
    # wallet's risk; every reader of the registry now gets what it actually
    # produced, with a `reason` string derived from the same evidence above
    # rather than a separately hand-written one that could drift out of sync.
    try:
        if complaint_count >= 2:
            reason = (
                f"{complaint_count} independent complaints name this wallet — "
                "strong corroborated evidence."
            )
        elif sanction:
            reason = f"OFAC-sanctioned entity: {sanction.get('designation', 'unknown')}."
        elif mixer_exposure:
            reason = (
                f"This wallet's own traced funds reach {mixer_exposure['entity_name']} — "
                "known mixer exposure."
            )
        elif len(typo_codes) >= TYPOLOGY_FLOOR_MIN_CODES:
            reason = (
                "This wallet's own traced flow exhibits multiple laundering patterns "
                f"({', '.join(sorted(typo_codes))})."
            )
        elif complaint_count == 1:
            reason = "1 complaint names this wallet; behavioral model score applied, awaiting further corroboration."
        else:
            reason = "Behavioral (ML) signal only — no complaint or sanctions corroboration yet."
        await registry_service.set_risk_entry(
            chain=chain.value,
            address=address,
            score=risk_score,
            tier=risk_tier,
            source="risk_service",
            designation={"reason": reason, "model_version": model_version, "snapshot_id": snapshot_id},
        )
    except Exception:  # noqa: BLE001 — the registry write must never break the response
        logger.warning("risk_registry_write_through_failed", address=address, chain=chain.value)

    return RiskResponse(
        risk_score=risk_score,
        risk_tier=risk_tier,
        risk_source=risk_source,
        evidence=all_evidence,
        osint=[h.to_osint_evidence() for h in osint_hits],
        model_version=model_version,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        snapshot_id=snapshot_id,
        calculated_at=datetime.now(timezone.utc).isoformat(),
    )
