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
from app.services.explorers.base import BlockchainExplorer, ExplorerUnavailableError, RawTx
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
            "User-Agent": "Argus-Forensics/1.0",
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
                    raise ExplorerUnavailableError(f"TRON explorer rate-limited for {addr}")
                else:
                    logger.warning("tronscan_returned_non_200", extra={"status": resp.status_code, "text": resp.text[:200]})
                    raise ExplorerUnavailableError(f"TRON explorer returned {resp.status_code} for {addr}")
        except ExplorerUnavailableError:
            raise
        except Exception as e:
            logger.warning("tron_explorer_request_failed", extra={"error": str(e), "address": addr})

        raise ExplorerUnavailableError(f"TRON explorer failed for {addr}")

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

            # If toAddress is missing, check contract/trigger_info parameter.
            # For a TRC20 transfer(address _to, uint256 _value) call, Tronscan
            # names the decoded ABI params with a leading underscore (_to,
            # _value) — without checking those keys too, to_addr silently
            # stayed as the CONTRACT address (the call target) rather than the
            # real recipient, making every TRC20 transfer look like a
            # zero-amount transfer to the contract itself.
            trigger_info = item.get("trigger_info") or {}
            params = trigger_info.get("parameter") or {}
            contract_data = item.get("contractData") or {}
            if params.get("_to"):
                to_addr = params["_to"]
            elif params.get("to"):
                to_addr = params["to"]
            elif contract_data.get("to_address"):
                to_addr = contract_data["to_address"]

            token_info = item.get("tokenInfo") or {}
            try:
                net_fee_sun = float(item.get("net_fee") or item.get("netFee") or 0)
                energy_fee_sun = float(item.get("energy_fee") or item.get("energyFee") or 0)
                bandwidth_used = float(item.get("net_usage") or item.get("netUsage") or 0)
                energy_used = float(item.get("energy_usage") or item.get("energyUsage") or 0)
            except (TypeError, ValueError):
                net_fee_sun = energy_fee_sun = bandwidth_used = energy_used = 0.0
            try:
                decimals = max(0, int(token_info.get("tokenDecimal", 6) or 6))
            except (ValueError, TypeError):
                decimals = 6

            # Tronscan reports contract transfers with top-level amount=0;
            # the actual value is in trigger_info.parameter._value (TRC20
            # transfer's decoded ABI param — underscore-prefixed, see above)
            # or contractData.amount.
            amount = 0.0
            for raw_amount in (
                item.get("amount"),
                contract_data.get("amount"),
                params.get("_value"),
                params.get("value"),
                params.get("amount"),
            ):
                try:
                    parsed_amount = float(raw_amount or 0)
                    if 0 < parsed_amount < 1e15:
                        amount = round(parsed_amount / (10 ** decimals), 6)
                        break
                except (ValueError, TypeError, OverflowError):
                    continue

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
                        fee_native=(net_fee_sun + energy_fee_sun) / 1e6 if net_fee_sun or energy_fee_sun else None,
                        bandwidth_used=bandwidth_used if bandwidth_used else None,
                        energy_used=energy_used if energy_used else None,
                )
            )

        return results
