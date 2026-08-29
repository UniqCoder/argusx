"""
app/services/explorers/eth_explorer.py — Ethereum Blockchain Explorer Integration.

Uses Blockscout REST API (with Etherscan-compatible fallback) to fetch live EVM transactions.
"""
from datetime import datetime, timezone
import logging
from typing import List

import httpx

from app.schemas.common import Chain
from app.services.explorers.base import BlockchainExplorer, RawTx
from app.services.explorers.known_vasps import lookup_known_vasp

logger = logging.getLogger(__name__)

BLOCKSCOUT_ETH_API = "https://eth.blockscout.com/api/v2"


class EthereumExplorer(BlockchainExplorer):
    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout

    async def get_transactions(self, address: str, limit: int = 25) -> List[RawTx]:
        """Fetch transactions for an EVM address via Blockscout v2 REST API."""
        addr = address.strip()
        url = f"{BLOCKSCOUT_ETH_API}/addresses/{addr}/transactions"

        headers = {
            "Accept": "application/json",
            "User-Agent": "Unigraph-Forensics/1.0",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("items", [])
                    return self._parse_blockscout_txs(addr, items, limit)
                elif resp.status_code == 404:
                    logger.info("eth_address_not_found", extra={"address": addr})
                    return []
                elif resp.status_code == 429:
                    logger.warning("eth_explorer_rate_limited", extra={"address": addr})
                    return []
        except Exception as e:
            logger.warning("eth_explorer_request_failed", extra={"error": str(e)})

        return []

    def _parse_blockscout_txs(self, target_address: str, tx_items: list, limit: int) -> List[RawTx]:
        results: List[RawTx] = []

        for item in tx_items[:limit]:
            tx_hash = item.get("hash", "")
            raw_val = item.get("value", "0")
            try:
                amount_eth = round(float(raw_val) / 1e18, 6)
            except (ValueError, TypeError):
                amount_eth = 0.0

            from_obj = item.get("from") or {}
            to_obj = item.get("to") or {}
            from_addr = from_obj.get("hash", "")
            to_addr = to_obj.get("hash", "")

            # Parse timestamp
            raw_ts = item.get("timestamp")
            if raw_ts:
                try:
                    ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                except ValueError:
                    ts = datetime.now(timezone.utc)
            else:
                ts = datetime.now(timezone.utc)

            # Check if to_address has metadata tag from Blockscout or known VASP registry
            vasp_tag = None
            if to_obj:
                metadata = to_obj.get("metadata") or {}
                tags = metadata.get("tags") or []
                for t in tags:
                    if t.get("tagType") in ("name", "protocol", "generic"):
                        name = t.get("name")
                        if name and any(k in name.lower() for k in ["binance", "bitfinex", "coinbase", "kraken", "exchange", "hot wallet"]):
                            vasp_tag = name
                            break

            if not vasp_tag and to_addr:
                vasp_match = lookup_known_vasp(to_addr)
                if vasp_match:
                    vasp_tag = vasp_match[0]

            if from_addr and to_addr:
                results.append(
                    RawTx(
                        tx_hash=tx_hash,
                        from_address=from_addr,
                        to_address=to_addr,
                        amount=amount_eth,
                        chain=Chain.ETH,
                        timestamp=ts,
                        vasp_tag=vasp_tag,
                    )
                )

        return results
