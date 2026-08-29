"""
app/services/explorers/tron_explorer.py — TRON Blockchain Explorer Integration (Tronscan API).

Fetches live on-chain TRON / TRC20 transactions via Tronscan REST API.
API Key is passed securely via 'TRON-PRO-API-KEY' request header from settings.
"""
from datetime import datetime, timezone
import logging
from typing import List, Optional

import httpx

from app.core.config import get_settings
from app.schemas.common import Chain
from app.services.explorers.base import BlockchainExplorer, RawTx
from app.services.explorers.known_vasps import lookup_known_vasp

logger = logging.getLogger(__name__)
settings = get_settings()

TRONSCAN_BASE_URL = "https://apilist.tronscanapi.com/api"


class TronExplorer(BlockchainExplorer):
    def __init__(self, timeout: float = 8.0, api_key: Optional[str] = None):
        self.timeout = timeout
        raw_key = api_key or getattr(settings, "tronscan_api_key", "")
        self.api_key = raw_key.strip().strip('"').strip("'") if raw_key else ""

    async def get_transactions(self, address: str, limit: int = 25) -> List[RawTx]:
        """
        Fetch on-chain transactions for a TRON address via Tronscan REST API.
        Sends TRON-PRO-API-KEY header if key is configured in settings/env.
        """
        addr = address.strip()
        url = f"{TRONSCAN_BASE_URL}/transaction?sort=-timestamp&count=true&limit={limit}&start=0&address={addr}"

        headers = {
            "Accept": "application/json",
            "User-Agent": "Unigraph-Forensics/1.0",
        }
        if self.api_key:
            headers["TRON-PRO-API-KEY"] = self.api_key

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    tx_list = data.get("data", [])
                    return self._parse_tronscan_txs(addr, tx_list, limit)
                elif resp.status_code == 400:
                    logger.info("tron_invalid_address_or_no_txs", extra={"address": addr})
                    return []
                elif resp.status_code == 404:
                    logger.info("tron_address_not_found", extra={"address": addr})
                    return []
                elif resp.status_code == 429:
                    logger.warning("tron_explorer_rate_limited", extra={"address": addr})
                    return []
                else:
                    logger.warning("tronscan_returned_non_200", extra={"status": resp.status_code, "text": resp.text[:200]})
        except Exception as e:
            logger.warning("tron_explorer_request_failed", extra={"error": str(e), "address": addr})

        return []

    def _parse_tronscan_txs(self, target_address: str, tx_list: list, limit: int) -> List[RawTx]:
        results: List[RawTx] = []

        for item in tx_list[:limit]:
            tx_hash = item.get("hash", "")
            ts_ms = item.get("timestamp", 0)
            if ts_ms:
                ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            else:
                ts = datetime.now(timezone.utc)

            from_addr = item.get("ownerAddress", "")
            to_addr = item.get("toAddress", "")

            # If toAddress is missing, check contract/trigger_info parameter
            trigger_info = item.get("trigger_info") or {}
            params = trigger_info.get("parameter") or {}
            if not to_addr:
                to_addr = params.get("to", "")

            # Parse amount
            raw_amt = float(item.get("amount", 0) or 0)
            token_info = item.get("tokenInfo") or {}
            decimals = int(token_info.get("tokenDecimal", 6) or 6)

            if raw_amt > 0:
                amount = round(raw_amt / (10 ** decimals), 6)
            elif "value" in params:
                try:
                    param_val = float(params["value"])
                    amount = round(param_val / (10 ** decimals), 6)
                except (ValueError, TypeError):
                    amount = 0.0
            else:
                amount = 0.0

            # Known VASP attribution
            vasp_from = lookup_known_vasp(from_addr)
            vasp_to = lookup_known_vasp(to_addr)
            vasp_name = None
            if vasp_to:
                vasp_name = vasp_to[0]
            elif vasp_from:
                vasp_name = vasp_from[0]

            results.append(
                RawTx(
                    tx_hash=tx_hash,
                    from_address=from_addr,
                    to_address=to_addr,
                    amount=amount,
                    chain=Chain.TRON,
                    timestamp=ts,
                    vasp_tag=vasp_name,
                )
            )

        return results
