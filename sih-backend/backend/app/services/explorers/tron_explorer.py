"""
app/services/explorers/tron_explorer.py — TRON Blockchain Explorer Integration (Tronscan API).

Fetches live on-chain TRON / TRC20 transactions via Tronscan REST API.
API Key is passed securely via 'TRON-PRO-API-KEY' request header from settings.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import List, Optional


from app.core.config import get_settings
from app.schemas.common import Chain
from app.services.explorers import http_client
from app.services.explorers.base import BlockchainExplorer, ExplorerUnavailableError, RawTx
from app.services.explorers.known_vasps import lookup_known_vasp

logger = logging.getLogger(__name__)
settings = get_settings()

TRONSCAN_BASE_URL = "https://apilist.tronscanapi.com/api"

# Bounded single retry for TRANSIENT failures only (transport errors /
# timeouts / 502-504). Never retries 429 (rate-limit — the caller must see
# the outage) or 400/404 (definitive answers). ~1s backoff keeps the worst
# case bounded.
_RETRYABLE_STATUS = {500, 502, 503, 504}
_RETRY_BACKOFF_SECONDS = 1.0
# Longer than the transport retry: a 429 means slow down, not try again now.
_RATE_LIMIT_BACKOFF_SECONDS = 2.0


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
            resp = await http_client.get(url, headers=headers, timeout=self.timeout)
            if resp.status_code == 200:
                return self._parse_tronscan_txs(addr, resp.json().get("data", []), limit)
            elif resp.status_code == 400:
                logger.info("tron_invalid_address_or_no_txs", extra={"address": addr})
                return []
            elif resp.status_code == 404:
                logger.info("tron_address_not_found", extra={"address": addr})
                return []
            elif resp.status_code == 429:
                # One paced retry. 429 used to be fatal on the reasoning that
                # "backing off once is not enough" — but with the client-side
                # pacer in http_client a 429 is now the exception rather than
                # the steady state, and giving up immediately turned a
                # recoverable throttle into an EXPLORER_UNAVAILABLE dead end on
                # a majority of nodes in a live TRON trace.
                logger.warning("tron_explorer_rate_limited", extra={"address": addr})
                await asyncio.sleep(_RATE_LIMIT_BACKOFF_SECONDS)
                resp = await http_client.get(url, headers=headers, timeout=self.timeout)
                if resp.status_code == 200:
                    return self._parse_tronscan_txs(addr, resp.json().get("data", []), limit)
                if resp.status_code in (400, 404):
                    return []
                raise ExplorerUnavailableError(f"TRON explorer rate-limited for {addr}")
            elif resp.status_code in _RETRYABLE_STATUS:
                logger.warning(
                    "tron_explorer_transient",
                    extra={"status": resp.status_code, "address": addr},
                )
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
                resp = await http_client.get(url, headers=headers, timeout=self.timeout)
                if resp.status_code == 200:
                    return self._parse_tronscan_txs(addr, resp.json().get("data", []), limit)
                if resp.status_code in (400, 404):
                    return []
                raise ExplorerUnavailableError(f"TRON explorer returned {resp.status_code} for {addr}")
            else:
                logger.warning("tronscan_returned_non_200", extra={"status": resp.status_code, "text": resp.text[:200]})
                raise ExplorerUnavailableError(f"TRON explorer returned {resp.status_code} for {addr}")
        except ExplorerUnavailableError:
            raise
        except Exception as e:
            # Transport-level failure (timeout / connection reset). One bounded
            # retry, then surface as an explorer outage.
            logger.warning("tron_explorer_request_failed", extra={"error": str(e), "address": addr})
            try:
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
                resp = await http_client.get(url, headers=headers, timeout=self.timeout)
                if resp.status_code == 200:
                    return self._parse_tronscan_txs(addr, resp.json().get("data", []), limit)
                if resp.status_code in (400, 404):
                    return []
            except Exception:
                pass
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

            # Which asset is this amount actually in? Tronscan puts TRC-20
            # transfers through the same records as native TRX, so without this
            # a wallet's USDT and TRX inflows were summed into one meaningless
            # denominator by the haircut fraction. tokenAbbr/tokenName identify
            # the token; tokenId is the contract address (TRC-20) or "_" for
            # native TRX.
            token_id = str(token_info.get("tokenId") or "").strip()
            token_abbr = str(
                token_info.get("tokenAbbr") or token_info.get("tokenName") or ""
            ).strip()
            if token_id and token_id != "_" and token_abbr:
                asset = token_abbr.upper()
                asset_id = token_id
            else:
                asset = "TRX"
                asset_id = None

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
                    asset=asset,
                    asset_id=asset_id,
                    vasp_tag=vasp_name,
                        fee_native=(net_fee_sun + energy_fee_sun) / 1e6 if net_fee_sun or energy_fee_sun else None,
                        bandwidth_used=bandwidth_used if bandwidth_used else None,
                        energy_used=energy_used if energy_used else None,
                )
            )

        return results
