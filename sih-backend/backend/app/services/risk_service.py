"""
app/services/risk_service.py — ML risk scoring service and SHAP evidence generation.

Calculates risk score, assigns risk tier, and extracts explainable evidence for wallets.
"""
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.explain import explain_wallet_risk
from app.ml.features import compute_feature_vector
from app.ml.model import map_score_to_tier, predict_risk_score
from app.schemas.common import Chain
from app.schemas.wallet import RiskResponse
from app.services.explorers.btc_explorer import BitcoinExplorer
from app.services.explorers.eth_explorer import EthereumExplorer
from app.services.tracing_service import get_or_create_wallet

logger = logging.getLogger(__name__)

btc_explorer = BitcoinExplorer()
eth_explorer = EthereumExplorer()


async def evaluate_wallet_risk(
    db: AsyncSession,
    address: str,
    chain: Chain,
) -> RiskResponse:
    """
    Evaluate on-chain ML risk score and SHAP evidence for a given wallet address.
    """
    wallet = await get_or_create_wallet(db, address, chain)

    # 1. Fetch live transactions for the wallet
    if chain == Chain.BTC:
        txs = await btc_explorer.get_transactions(address, limit=25)
    elif chain == Chain.ETH:
        txs = await eth_explorer.get_transactions(address, limit=25)
    else:
        txs = []

    # 2. Extract feature vector matching Elliptic++ 55-column schema
    feature_vector = compute_feature_vector(address, chain.value, txs)

    # 3. Model inference and tier mapping
    risk_score = round(predict_risk_score(feature_vector), 3)
    risk_tier = map_score_to_tier(risk_score)

    # 4. SHAP explainability
    evidence = explain_wallet_risk(feature_vector, top_k=5)

    # 5. Persist updated score & tier to PostgreSQL
    wallet.risk_score = risk_score
    wallet.risk_tier = risk_tier.value
    await db.commit()
    await db.refresh(wallet)

    logger.info(
        "wallet_risk_scored",
        extra={
            "address": address,
            "chain": chain.value,
            "score": risk_score,
            "tier": risk_tier.value,
        },
    )

    return RiskResponse(
        risk_score=risk_score,
        risk_tier=risk_tier,
        evidence=evidence,
    )
