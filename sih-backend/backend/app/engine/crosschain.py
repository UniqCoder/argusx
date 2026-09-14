"""
app/engine/crosschain.py — Following money across a bridge.

THE PROBLEM
-----------
A bridge is a hard terminal: the engine classifies it, stops, and reports
BRIDGE. That is honest — the destination-chain address is genuinely not
derivable from the deposit transaction — but it means an
`ETH -> Polygon PoS -> exchange` trail is drawn as three hops ending at a
contract, and the exchange deposit at the end is never found. Following one
chain, the money simply vanishes.

WHAT THIS DOES
--------------
Matches a bridge *deposit* on the source chain to a bridge *release* on a
destination chain, by value and time:

    release.from == the same bridge contract
    release.timestamp within [deposit.timestamp, deposit.timestamp + WINDOW]
    |release.amount - deposit.amount| / deposit.amount <= TOLERANCE

WHAT THIS IS NOT
----------------
A proof. It is a correlation, and it is labelled as one everywhere it appears:
every link carries `basis="CROSS_CHAIN_HEURISTIC"` and a confidence derived
from how tight the value and time match actually were. The UI draws these edges
differently from on-chain edges for the same reason. A trace that crosses a
bridge on a heuristic and one that follows a signed transaction are not the
same kind of evidence and must never look like it.

When no match is found — the common case on a busy public bridge — the bridge
stays a terminal and the trace says BRIDGE, exactly as before. Silence is the
correct answer; a guess is not.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import structlog

from app.engine.registries import bridge_destinations
from app.services.explorers.base import RawTx

logger = structlog.get_logger(__name__)

# How long after a deposit a release can plausibly appear. Real bridges settle
# in minutes to hours; Polygon PoS checkpoints are ~30 minutes and optimistic
# bridges can take days, but a window that wide matches almost anything, which
# is how a heuristic turns into a fabrication. Six hours keeps it defensible.
MATCH_WINDOW = timedelta(hours=6)

# Bridges take a fee, so the released amount is slightly below the deposit.
# 2% covers fee plus rounding without matching an unrelated transfer of a
# different size.
VALUE_TOLERANCE = 0.02

# Below this, the value match is too weak to be worth asserting at all.
MIN_CONFIDENCE = 0.55


@dataclass(frozen=True)
class CrossChainLink:
    to_chain: str
    to_address: str
    amount: float
    tx_hash: str
    timestamp: Optional[datetime]
    confidence: float
    basis: str = "CROSS_CHAIN_HEURISTIC"
    detail: str = ""


def _score(deposit_amount: float, release: RawTx, deposit_at: datetime) -> float:
    """
    How well this release matches this deposit, in [0, 1].

    Two independent signals, weighted equally: how close the value is, and how
    soon it arrived. Both are reported in the link's `detail` so a reader can
    judge the match rather than trusting the number.
    """
    if deposit_amount <= 0:
        return 0.0
    value_delta = abs(release.amount - deposit_amount) / deposit_amount
    if value_delta > VALUE_TOLERANCE:
        return 0.0
    value_score = 1.0 - (value_delta / VALUE_TOLERANCE)

    if release.timestamp is None:
        time_score = 0.5  # unknown timing is neither corroborating nor damning
    else:
        elapsed = release.timestamp - deposit_at
        if elapsed < timedelta(0) or elapsed > MATCH_WINDOW:
            return 0.0
        time_score = 1.0 - (elapsed / MATCH_WINDOW)

    return round(0.5 * value_score + 0.5 * time_score, 4)


async def resolve_crossing(
    bridge_address: str,
    source_chain: str,
    deposit_amount: float,
    deposit_at: Optional[datetime],
    asset: str,
    fetch_transactions,
) -> Optional[CrossChainLink]:
    """
    The best destination-chain release matching this bridge deposit, or None.

    `fetch_transactions(address, chain)` is injected rather than imported so
    this module stays independent of explorer selection and is trivially
    testable with a fixed transaction list.
    """
    if deposit_at is None or deposit_amount <= 0:
        # Without a deposit timestamp the time half of the match is
        # unconstrained, which is most of what keeps this heuristic from
        # matching arbitrary traffic. Decline rather than guess.
        return None

    destinations = bridge_destinations(bridge_address)
    if not destinations:
        return None

    best: Optional[CrossChainLink] = None
    for dest_chain in destinations:
        if dest_chain == source_chain:
            continue
        try:
            candidates = await fetch_transactions(bridge_address, dest_chain)
        except Exception as exc:  # an unreachable destination is not a match
            logger.debug(
                "crosschain_fetch_failed",
                bridge=bridge_address, chain=dest_chain, error=str(exc),
            )
            continue

        for tx in candidates:
            if not tx.from_address or tx.from_address.strip().lower() != bridge_address.strip().lower():
                continue
            if asset and tx.asset and tx.asset != asset:
                continue
            confidence = _score(deposit_amount, tx, deposit_at)
            if confidence < MIN_CONFIDENCE:
                continue
            if best is not None and confidence <= best.confidence:
                continue
            elapsed_min = (
                round((tx.timestamp - deposit_at).total_seconds() / 60.0, 1)
                if tx.timestamp
                else None
            )
            value_delta_pct = round(
                abs(tx.amount - deposit_amount) / deposit_amount * 100.0, 3
            )
            best = CrossChainLink(
                to_chain=dest_chain,
                to_address=tx.to_address,
                amount=tx.amount,
                tx_hash=tx.tx_hash,
                timestamp=tx.timestamp,
                confidence=confidence,
                detail=(
                    f"Matched a release of {tx.amount:g} {tx.asset or asset} on {dest_chain} "
                    f"{elapsed_min} minutes after the deposit, "
                    f"{value_delta_pct}% below the deposited amount."
                    if elapsed_min is not None
                    else
                    f"Matched a release of {tx.amount:g} {tx.asset or asset} on {dest_chain}, "
                    f"{value_delta_pct}% below the deposited amount (release time unknown)."
                ),
            )

    if best is not None:
        logger.info(
            "crosschain_link_resolved",
            bridge=bridge_address,
            source_chain=source_chain,
            to_chain=best.to_chain,
            to_address=best.to_address,
            confidence=best.confidence,
        )
    return best
