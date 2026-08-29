"""
app/services/explorers/btc_explorer.py — Bitcoin Blockchain Explorer Integration.

Uses Blockstream Esplora API (with Mempool.space fallback) to fetch live UTXO transactions.
"""
from datetime import datetime, timezone
import logging
from typing import List

import httpx

from app.schemas.common import Chain
from app.services.explorers.base import BlockchainExplorer, RawTx
from app.services.explorers.known_vasps import lookup_known_vasp

logger = logging.getLogger(__name__)

PRIMARY_ESPLORA = "https://blockstream.info/api"
FALLBACK_ESPLORA = "https://mempool.space/api"


class BitcoinExplorer(BlockchainExplorer):
    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout

    async def get_transactions(self, address: str, limit: int = 25) -> List[RawTx]:
        """Fetch transactions for a BTC address via Esplora REST API."""
        addr = address.strip()
        endpoints = [PRIMARY_ESPLORA, FALLBACK_ESPLORA]

        headers = {
            "Accept": "application/json",
            "User-Agent": "Unigraph-Forensics/1.0",
        }

        for base_url in endpoints:
            url = f"{base_url}/address/{addr}/txs"
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        return self._parse_esplora_txs(addr, data, limit)
                    elif resp.status_code == 404:
                        logger.info("btc_address_not_found", extra={"address": addr})
                        return []
                    elif resp.status_code == 429:
                        logger.warning("btc_explorer_rate_limited", extra={"base_url": base_url, "address": addr})
            except Exception as e:
                logger.warning("btc_explorer_request_failed", extra={"base_url": base_url, "error": str(e)})

        logger.error("all_btc_explorers_failed", extra={"address": addr})
        return []

    def _parse_esplora_txs(self, target_address: str, tx_list: list, limit: int) -> List[RawTx]:
        results: List[RawTx] = []

        for item in tx_list[:limit]:
            txid = item.get("txid", "")
            status = item.get("status", {})
            block_time = status.get("block_time")
            if block_time:
                ts = datetime.fromtimestamp(block_time, tz=timezone.utc)
            else:
                ts = datetime.now(timezone.utc)

            # Find inputs (from_address)
            vin = item.get("vin", [])
            from_addrs = []
            for v in vin:
                prev = v.get("prevout")
                if prev and "scriptpubkey_address" in prev:
                    from_addrs.append(prev["scriptpubkey_address"])
            
            from_addr = from_addrs[0] if from_addrs else target_address

            # Find outputs (to_address)
            vout = item.get("vout", [])
            for out in vout:
                to_addr = out.get("scriptpubkey_address")
                value_sat = out.get("value", 0)
                amount_btc = round(value_sat / 1e8, 8)

                if to_addr and to_addr != from_addr and amount_btc > 0:
                    vasp_match = lookup_known_vasp(to_addr)
                    vasp_tag = vasp_match[0] if vasp_match else None

                    results.append(
                        RawTx(
                            tx_hash=txid,
                            from_address=from_addr,
                            to_address=to_addr,
                            amount=amount_btc,
                            chain=Chain.BTC,
                            timestamp=ts,
                            vasp_tag=vasp_tag,
                        )
                    )

        return results
