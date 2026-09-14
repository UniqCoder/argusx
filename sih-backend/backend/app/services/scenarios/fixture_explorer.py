"""
app/services/scenarios/fixture_explorer.py — Serves seeded scenario transactions
through the same interface a live blockchain explorer implements.

This is NOT a mock of the engine. It is a mock of *the internet*. Everything
above it — the taint BFS, terminal classification, dust pruning, asset
selection, the reproducible hash, risk, correlation, the PDF — runs unchanged
and unaware. Swapping a scenario address for a live one changes which explorer
answers and nothing else.

Two properties matter and are tested:
  - Determinism. The same address always returns the same transactions in the
    same order, so `reproducible_hash` is stable across runs.
  - No network. Zero I/O, which is why a seeded scenario completes in about a
    second while a live trace waits on public APIs.
"""
from __future__ import annotations

from typing import List

from app.schemas.common import Chain
from app.services.explorers.base import BlockchainExplorer, RawTx
from app.services.scenarios.definitions import (
    ALL_SCENARIOS,
    ScenarioTx,
    synth_tx_hash,
    _t,
)


def _build_tx_table() -> dict[tuple[str, str], List[RawTx]]:
    """
    (lowercased address, chain) -> the transactions that address participates in.

    Built once at import. Transaction hashes are derived from the scenario key
    and the transaction's index within that scenario, so a given transfer keeps
    the same hash forever — proof paths and evidence entries stay comparable
    across reseeds.
    """
    table: dict[tuple[str, str], List[RawTx]] = {}
    for scenario in ALL_SCENARIOS:
        for index, stx in enumerate(scenario.txs):
            raw = _to_raw(scenario.key, index, stx, scenario.started_at)
            for addr in (stx.frm, stx.to):
                table.setdefault((addr.lower(), stx.chain.value), []).append(raw)
    # Newest first, matching what the real explorers return (Blockstream,
    # Blockscout and Tronscan all sort descending by time).
    for txs in table.values():
        txs.sort(key=lambda t: t.timestamp, reverse=True)
    return table


def _to_raw(scenario_key: str, index: int, stx: ScenarioTx, base) -> RawTx:
    return RawTx(
        tx_hash=synth_tx_hash(scenario_key, index, stx.chain),
        from_address=stx.frm,
        to_address=stx.to,
        amount=stx.amount,
        chain=stx.chain,
        timestamp=_t(base, stx.minute),
        asset=stx.asset,
        asset_id=stx.asset_id,
    )


_TX_TABLE: dict[tuple[str, str], List[RawTx]] = _build_tx_table()


class FixtureExplorer(BlockchainExplorer):
    """Answers for seeded scenario addresses only."""

    def __init__(self, chain: Chain):
        self.chain = chain

    async def get_transactions(self, address: str, limit: int = 25) -> List[RawTx]:
        txs = _TX_TABLE.get((address.strip().lower(), self.chain.value), [])
        # An address a scenario places on this chain but never transacts on is a
        # confirmed-empty history ([]), never an ExplorerUnavailableError — the
        # distinction the engine relies on to tell NO_OUTFLOW from an outage.
        return txs[:limit]


_EXPLORERS: dict[str, FixtureExplorer] = {
    chain.value: FixtureExplorer(chain) for chain in Chain
}


def fixture_explorer_for(chain: str) -> FixtureExplorer | None:
    return _EXPLORERS.get(chain)


def transactions_for(address: str, chain: str) -> List[RawTx]:
    """Direct read, for the cross-chain heuristic and tests."""
    return list(_TX_TABLE.get((address.strip().lower(), chain), []))
