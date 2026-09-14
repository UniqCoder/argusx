"""
app/engine/registries.py — Known mixer / bridge contract registries.

Deliberately small and curated, exactly like services/explorers/known_vasps.py.
An address here is a Layer-1 terminal condition: mixers hard-stop the trace
(ARGUS-ENGINE-V2.md §1.3 — "mixers are a hard stop", we do not claim to see
through them); bridges hand off to the cross-chain correlation heuristic.

Extending this list does not require touching any propagation logic — see
app/engine/taint.py::_classify_terminal.

───────────────────────────────────────────────────────────────────────────────
CURATION RULE (enforced by app/tests/test_registry_integrity.py — do not add
an entry that cannot satisfy it):

  1. The address must pass structural validation
     (app/services/explorers/address_validation.py) — EIP-55 for EVM,
     base58check for BTC/TRON.
  2. It must have been observed on-chain, and the observation recorded in the
     comment above it (contract name and/or balance, plus when it was checked).

This rule exists because an audit found the previous contents of this file were
partly fabricated and therefore dead code:

  - "Poly Bridge (ETH)" 0x8f14A9E0…D9C1 — zero balance, not a contract, no
    on-chain name. An address that has never been used. REMOVED.
  - "Multichain Router (ETH)" 0x6b7a…F413 — 41 characters, one hex digit short
    of a valid EVM address, so `classify_bridge` could never return it.
    REMOVED.
  - "Tornado Cash 1 ETH" 0x47CE0C6e…4a34 — zero balance, not a contract, while
    the three genuine Tornado pools below hold hundreds to hundreds of
    thousands of ETH. Not the real 1 ETH pool. REMOVED.

Net effect of that audit: KNOWN_BRIDGES was 100% non-functional, so bridge
detection had never once fired on live data. The replacements below are all
verified deployed bridge contracts.
"""
from typing import Optional

# Verified against eth.blockscout.com on 2026-09-12 — each entry's on-chain
# contract name and native balance are recorded as the provenance note.
KNOWN_MIXERS: dict[str, str] = {
    # Tornado Cash (ETH) — canonical fixed-denomination pool contracts.
    # on-chain name "TornadoCash_Eth_01", balance ~603 ETH
    "0x12D66f87A04A9E220743712cE6d9bB1B5616B8Fc": "Tornado Cash 0.1 ETH",
    # on-chain name "TornadoCash_eth", balance ~21,870 ETH
    "0x910Cbd523D972eb0a6f4cAe4618aD62622b39DbF": "Tornado Cash 10 ETH",
    # on-chain name "TornadoCash_eth", balance ~240,100 ETH
    "0xA160cdAB225685dA1d56aa342Ad8841c3b53f291": "Tornado Cash 100 ETH",
    # Wasabi Wallet (BTC) — CoinJoin coordinator-linked pooled outputs.
    # bech32, structurally valid; BTC-side balance not asserted here.
    "bc1qa24tsgchvuxsaccp8vrnkfd85hrcpafg20kmjw": "Wasabi Wallet CoinJoin pool",
}

# Every entry below was confirmed to be a deployed contract (is_contract=true)
# whose on-chain name corroborates the label, checked 2026-09-12.
KNOWN_BRIDGES: dict[str, str] = {
    # on-chain name "RootChainManagerProxy" — Polygon PoS bridge entry point
    "0xA0c68C638235ee32657e8f720a23ceC1bFc77C77": "Polygon PoS Bridge",
    # on-chain name "L1ChugSplashProxy" — Optimism's distinctive L1 proxy type
    "0x99C9fc46f92E8a1c0deC1b1747d010903E884bE1": "Optimism L1 Standard Bridge",
    # on-chain name "TokenBridge"
    "0x3ee18B2214AFF97000D974cf647E7C347E8fa585": "Wormhole Token Bridge",
    # on-chain name "L1_ETH_Bridge"
    "0xb8901acB165ed027E32754E0FFe830802919727f": "Hop Protocol L1 Bridge",
    # on-chain name "Router"
    "0x8731d54E9D02c286767d56ac03e8037C07e01e98": "Stargate Router",
    # on-chain name "TransparentUpgradeableProxy" — Arbitrum One Delayed Inbox.
    # The proxy name is generic, so this rests on the well-known address rather
    # than on a self-describing contract name; noted rather than overstated.
    "0x4Dbd4fc535Ac27206064B68FfCf827b0A60BAB3f": "Arbitrum One Bridge",
    # on-chain name "TransparentUpgradeableProxy" — Synapse bridge; same
    # generic-proxy caveat as Arbitrum above.
    "0x2796317b0fF8538F253012862c06787Adfb8cEb6": "Synapse Bridge",
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


# Which chains a bridge can release funds onto.
#
# Curated, and deliberately narrow. app/engine/crosschain.py only looks for a
# matching release on a chain listed here, so an entry that is wrong or too
# broad turns a value+time correlation into a search over unrelated traffic —
# which is how a heuristic quietly becomes a fabrication. A bridge absent from
# this map is still detected and still terminates the trace as BRIDGE; it is
# simply not followed across.
BRIDGE_DESTINATIONS: dict[str, tuple[str, ...]] = {
    # Polygon PoS bridge: Ethereum <-> Polygon only.
    "0xA0c68C638235ee32657e8f720a23ceC1bFc77C77": ("POLYGON",),
    # Stargate is a router across many chains; only the ones this system can
    # represent are listed, because a destination it cannot walk is not a
    # destination it should claim.
    "0x8731d54E9D02c286767d56ac03e8037C07e01e98": ("POLYGON", "BSC", "ETH"),
    # The remaining registry bridges are detected but not followed: their
    # destination chains have no explorer here, so a "match" could only ever be
    # asserted, never checked.
}


def bridge_destinations(address: str) -> tuple[str, ...]:
    """Chains this bridge is known to release onto; empty if it is not followed."""
    norm = address.strip()
    if norm in BRIDGE_DESTINATIONS:
        return BRIDGE_DESTINATIONS[norm]
    lowered = norm.lower()
    for k, v in BRIDGE_DESTINATIONS.items():
        if k.lower() == lowered:
            return v
    return ()
