"""
app/services/explorers/eth_explorer.py — Ethereum Blockchain Explorer Integration.

Uses Blockscout REST API (with Etherscan-compatible fallback) to fetch live EVM transactions.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import List


from app.schemas.common import Chain
from app.services.explorers import http_client
from app.services.explorers.base import BlockchainExplorer, ExplorerUnavailableError, RawTx
from app.services.explorers.known_vasps import lookup_known_vasp

logger = logging.getLogger(__name__)

BLOCKSCOUT_ETH_API = "https://eth.blockscout.com/api/v2"

# Bounded single retry for TRANSIENT failures only (transport errors /
# timeouts / 502-504). Never retries 429 (rate-limit — backing off once is
# not enough and the caller must see the outage) or 404 (a definitive
# answer, not a failure). ~1s backoff keeps the worst case bounded.
_RETRYABLE_STATUS = {500, 502, 503, 504}
_RETRY_BACKOFF_SECONDS = 1.0


class EthereumExplorer(BlockchainExplorer):
    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout

    async def get_transactions(self, address: str, limit: int = 25) -> List[RawTx]:
        """
        Fetch an EVM address's recent value movements: native ETH transactions
        AND ERC-20 token transfers, merged newest-first.

        The token half is not an enhancement, it is a correctness fix. This
        explorer used to return only `/addresses/{a}/transactions`, whose
        `value` field is *native ETH only* — so every ERC-20 movement (USDT,
        USDC, DAI …) came back as a 0-value transaction. The taint engine then
        pruned all of them as dust, which meant ARGUS could not see stablecoin
        laundering on Ethereum at all, despite "Task-Based USDT Fraud" being a
        headline use case. A real example from the wallet used as the ETH demo
        address: a 691.53 USDT outgoing transfer that the trace scored as 0.

        A token-transfer fetch failure is NOT fatal — native results are still
        returned, with the gap logged, rather than failing the whole trace.
        """
        addr = address.strip()
        # Concurrent, not sequential: adding the token half would otherwise
        # double every node's latency, and a deep trace makes one of these
        # calls per address it visits.
        native_res, token_res = await asyncio.gather(
            self._get_native_transactions(addr, limit),
            self._get_token_transfers(addr, limit),
            return_exceptions=True,
        )
        if isinstance(native_res, BaseException):
            # Native is the load-bearing half — a failure there is a real outage.
            raise native_res
        native = native_res
        if isinstance(token_res, BaseException):
            logger.warning(
                "eth_token_transfers_unavailable",
                extra={"address": addr, "error": str(token_res)},
            )
            tokens = []
        else:
            tokens = token_res
        merged = native + tokens
        merged.sort(key=lambda t: t.timestamp, reverse=True)
        return merged[:limit]

    async def _get_token_transfers(self, address: str, limit: int) -> List[RawTx]:
        """ERC-20 transfers for `address` via Blockscout v2."""
        url = f"{BLOCKSCOUT_ETH_API}/addresses/{address}/token-transfers"
        headers = {"Accept": "application/json", "User-Agent": "Argus-Forensics/1.0"}
        try:
            resp = await http_client.get(
                url, params={"type": "ERC-20"}, headers=headers, timeout=self.timeout
            )
            if resp.status_code == 200:
                return self._parse_token_transfers(resp.json().get("items", []), limit)
            if resp.status_code == 404:
                return []
            raise ExplorerUnavailableError(
                f"ETH token-transfers returned {resp.status_code} for {address}"
            )
        except ExplorerUnavailableError:
            raise
        except Exception as exc:
            raise ExplorerUnavailableError(
                f"ETH token-transfers failed for {address}: {exc}"
            ) from exc

    def _parse_token_transfers(self, items: list, limit: int) -> List[RawTx]:
        results: List[RawTx] = []
        for item in items[:limit]:
            token = item.get("token") or {}
            total = item.get("total") or {}
            symbol = (token.get("symbol") or "").strip().upper()
            contract = (token.get("address_hash") or token.get("address") or "").strip()
            # Token amounts are integer strings scaled by the token's own
            # decimals — never assume 18 (USDT/USDC are 6).
            try:
                decimals = int(total.get("decimals") or token.get("decimals") or 18)
            except (TypeError, ValueError):
                decimals = 18
            try:
                amount = float(total.get("value") or 0) / (10 ** max(0, decimals))
            except (TypeError, ValueError, OverflowError):
                continue
            if amount <= 0:
                continue

            from_addr = ((item.get("from") or {}).get("hash") or "").strip()
            to_addr = ((item.get("to") or {}).get("hash") or "").strip()
            if not from_addr or not to_addr:
                continue

            ts = self._parse_timestamp(item.get("timestamp"))
            vasp_match = lookup_known_vasp(to_addr)
            results.append(
                RawTx(
                    tx_hash=item.get("transaction_hash") or item.get("tx_hash") or "",
                    from_address=from_addr,
                    to_address=to_addr,
                    amount=amount,
                    chain=Chain.ETH,
                    timestamp=ts,
                    asset=symbol or "ERC20",
                    asset_id=contract or None,
                    vasp_tag=vasp_match[0] if vasp_match else None,
                )
            )
        return results

    @staticmethod
    def _parse_timestamp(raw) -> datetime:
        if isinstance(raw, str) and raw:
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                pass
        return datetime.now(timezone.utc)

    async def _get_native_transactions(self, address: str, limit: int = 25) -> List[RawTx]:
        """Native-ETH transactions only. See get_transactions for why this is split."""
        addr = address.strip()
        url = f"{BLOCKSCOUT_ETH_API}/addresses/{addr}/transactions"

        headers = {
            "Accept": "application/json",
            "User-Agent": "Argus-Forensics/1.0",
        }

        try:
            resp = await http_client.get(url, headers=headers, timeout=self.timeout)
            if resp.status_code == 200:
                return self._parse_blockscout_txs(addr, resp.json().get("items", []), limit)
            elif resp.status_code == 404:
                logger.info("eth_address_not_found", extra={"address": addr})
                return []
            elif resp.status_code == 429:
                logger.warning("eth_explorer_rate_limited", extra={"address": addr})
                raise ExplorerUnavailableError(f"ETH explorer rate-limited for {addr}")
            elif resp.status_code in _RETRYABLE_STATUS:
                logger.warning(
                    "eth_explorer_transient",
                    extra={"status": resp.status_code, "address": addr},
                )
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
                resp = await http_client.get(url, headers=headers, timeout=self.timeout)
                if resp.status_code == 200:
                    return self._parse_blockscout_txs(addr, resp.json().get("items", []), limit)
                if resp.status_code == 404:
                    return []
                raise ExplorerUnavailableError(f"ETH explorer returned {resp.status_code} for {addr}")
            else:
                logger.warning("eth_explorer_non_200", extra={"status": resp.status_code})
                raise ExplorerUnavailableError(f"ETH explorer returned {resp.status_code} for {addr}")
        except ExplorerUnavailableError:
            raise
        except Exception as e:
            # Transport-level failure (timeout / connection reset). One bounded
            # retry, then surface as an explorer outage.
            logger.warning("eth_explorer_request_failed", extra={"error": str(e)})
            try:
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
                resp = await http_client.get(url, headers=headers, timeout=self.timeout)
                if resp.status_code == 200:
                    return self._parse_blockscout_txs(addr, resp.json().get("items", []), limit)
                if resp.status_code == 404:
                    return []
            except Exception:
                pass
            raise ExplorerUnavailableError(f"ETH explorer failed for {addr}")

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

            try:
                gas_price_wei = float(item.get("gas_price") or 0)
                gas_used = float(item.get("gas_used") or 0)
            except (TypeError, ValueError):
                gas_price_wei = 0.0
                gas_used = 0.0

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
                        asset="ETH",
                        vasp_tag=vasp_tag,
                        fee_native=(gas_price_wei * gas_used) / 1e18 if gas_price_wei and gas_used else None,
                        gas_price_gwei=gas_price_wei / 1e9 if gas_price_wei else None,
                        gas_used=gas_used if gas_used else None,
                    )
                )

        return results
