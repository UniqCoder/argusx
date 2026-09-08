"""
app/services/risk_service.py — ML risk scoring service and SHAP evidence generation.

Calculates risk score, assigns risk tier, and extracts explainable evidence for wallets.
"""
import structlog
from typing import Optional
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.explain import explain_wallet_risk
from app.ml.features import (
    FEATURE_COLUMNS,
    GSAGE_EMBEDDING_COLUMNS,
    MODEL_FEATURE_COLUMNS,
    compute_feature_vector,
)
from app.ml.model import map_score_to_tier, predict_risk_score
from app.ml.relative_features import relative_reference_state
from app.schemas.common import Chain, RiskTier
from app.schemas.wallet import RiskResponse
from app.services import registry_service, sanctions_service
from app.services import osint_service
from app.services.explorers.base import ExplorerUnavailableError
from app.services.explorers.btc_explorer import BitcoinExplorer
from app.services.explorers.eth_explorer import EthereumExplorer
from app.services.explorers.tron_explorer import TronExplorer
from app.services.tracing_service import get_or_create_wallet

logger = structlog.get_logger(__name__)

# ── Promoted ML classification decision threshold (92f config, docs/ml.md) ──
# Locked on the combined model's validation slice to satisfy the <2% FPR policy
# cap. The original <1% FPR project target is achievable on this config with a
# stricter override at 0.85 (documented operating-point tradeoff in docs/ml.md);
# scores below this threshold are treated as NOT flagged.
RISK_FLAG_THRESHOLD = 0.70

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
    # Runs BEFORE any DB, explorer, graph, or ML work so a matched address is a
    # deterministic hard block (critical / score 1.0) regardless of model output.
    # The committed curated seed lookup needs no network; the Redis registry
    # consult covers operationally-seeded designations beyond that file.
    sanction = sanctions_service.lookup_sanctioned(chain, address)
    if not sanction:
        try:
            sanction = await sanctions_service.lookup_registry_designation(
                registry_service.get_redis_client(), chain, address
            )
        except Exception:  # noqa: BLE001 — registry consult must never break scoring
            sanction = None
    if sanction:
        return sanctions_service.build_sanctions_override_response(sanction)

    wallet = await get_or_create_wallet(db, address, chain)

    # 1. Fetch live transactions. Explorer outage is NOT the same as a wallet
    #    with confirmed-empty history: outages surface as "unknown", never scored.
    try:
        if chain == Chain.BTC:
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

    # 4. Model inference and tier mapping
    risk_score = round(predict_risk_score(model_vector), 3)
    risk_tier = map_score_to_tier(risk_score)
    flagged = risk_score >= RISK_FLAG_THRESHOLD

    # 5. SHAP explainability
    evidence = explain_wallet_risk(model_vector, top_k=5)

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
    )

    return RiskResponse(
        risk_score=risk_score,
        risk_tier=risk_tier,
        evidence=all_evidence,
        osint=[h.to_osint_evidence() for h in osint_hits],
    )
