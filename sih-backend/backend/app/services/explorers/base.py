"""
app/services/explorers/base.py — Abstract base class and common models for blockchain explorers.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from app.schemas.common import Chain


class ExplorerUnavailableError(Exception):
    """Raised when an explorer provider fails on ALL endpoints (network outage /
    exhaustion), as distinct from a confirmed-empty transaction history ([])."""


@dataclass
class RawTx:
    tx_hash: str
    from_address: str
    to_address: str
    amount: float
    chain: Chain
    timestamp: datetime
    # Which asset `amount` is denominated in. REQUIRED for correct taint
    # apportionment: the haircut fraction is tainted-inflow / total-inflow, and
    # summing 100 USDT with 50 TRX into "150 units of inflow" produces a
    # meaningless denominator. The TRON explorer has always returned TRC-20
    # token amounts in the same `amount` field as native TRX, so traces of
    # token-active wallets were mixing assets before this existed.
    # `asset` is the display ticker; `asset_id` is the contract address, which
    # is what actually identifies a token (tickers are not unique — anyone can
    # deploy a contract calling itself USDT).
    asset: str = ""
    asset_id: Optional[str] = None
    vasp_tag: Optional[str] = None
    fee_native: Optional[float] = None
    gas_price_gwei: Optional[float] = None
    gas_used: Optional[float] = None
    bandwidth_used: Optional[float] = None
    energy_used: Optional[float] = None


class BlockchainExplorer(ABC):
    """Abstract interface for multi-chain blockchain data retrieval."""

    @abstractmethod
    async def get_transactions(self, address: str, limit: int = 25) -> List[RawTx]:
        """Fetch transactions associated with an on-chain address."""
        pass
