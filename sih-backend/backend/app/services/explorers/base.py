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
