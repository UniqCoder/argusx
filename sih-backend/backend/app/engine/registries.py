"""
app/engine/registries.py — Known mixer / bridge contract registries.

Deliberately small and curated, exactly like services/explorers/known_vasps.py.
An address here is a Layer-1 terminal condition: mixers hard-stop the trace
(ARGUS-ENGINE-V2.md §1.3 — "mixers are a hard stop", we do not claim to see
through them); bridges hand off to the cross-chain correlation heuristic.

Extending this list does not require touching any propagation logic — see
app/engine/taint.py::_classify_terminal.
"""
from typing import Optional

# Curated, provenance-noted. Not exhaustive — coverage gaps are disclosed,
# never silently assumed to be "clean" addresses.
KNOWN_MIXERS: dict[str, str] = {
    # Tornado Cash (ETH) — canonical fixed-denomination pool contracts
    "0x12D66f87A04A9E220743712cE6d9bB1B5616B8Fc": "Tornado Cash 0.1 ETH",
    "0x47CE0C6eD5B0Ee8Da45FF3E7d24C2b7D2b1A4a34": "Tornado Cash 1 ETH",
    "0x910Cbd523D972eb0a6f4cAe4618aD62622b39DbF": "Tornado Cash 10 ETH",
    "0xA160cdAB225685dA1d56aa342Ad8841c3b53f291": "Tornado Cash 100 ETH",
    # Wasabi Wallet (BTC) — CoinJoin coordinator-linked pooled outputs
    "bc1qa24tsgchvuxsaccp8vrnkfd85hrcpafg20kmjw": "Wasabi Wallet CoinJoin pool",
}

KNOWN_BRIDGES: dict[str, str] = {
    # Poly Network / Poly Bridge relay contracts (ETH side)
    "0x8f14A9E0Ac2FCDdEC846387fA79907c2f0C9D9C1": "Poly Bridge (ETH)",
    # Multichain (formerly Anyswap) router
    "0x6b7a87899490EcE95443e979cA9485CBE1DF413": "Multichain Router (ETH)",
}


def classify_mixer(address: str) -> Optional[str]:
    return _lookup_ci(KNOWN_MIXERS, address)


def classify_bridge(address: str) -> Optional[str]:
    return _lookup_ci(KNOWN_BRIDGES, address)


def _lookup_ci(registry: dict[str, str], address: str) -> Optional[str]:
    norm = address.strip()
    if norm in registry:
        return registry[norm]
    lowered = norm.lower()
    for k, v in registry.items():
        if k.lower() == lowered:
            return v
    return None
