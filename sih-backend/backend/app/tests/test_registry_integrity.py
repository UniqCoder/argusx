"""
Registry integrity — structural guards that stop fabricated addresses from
re-entering the curated registries.

Background: an audit found that `known_vasps.py` and `engine/registries.py`
together contained SIX entries that could never match a real trace — three
TRON addresses failing base58check, one EVM address one hex digit too short,
and two EVM addresses that had never been used on-chain. Because lookups fail
silently (returning None just like "not a known entity"), bridge detection had
never fired even once on live data and nobody could tell.

These tests make that class of bug impossible to reintroduce unnoticed. They
are offline and deterministic — no network, no explorer calls.
"""
import pytest

from app.engine.registries import KNOWN_BRIDGES, KNOWN_MIXERS
from app.services.explorers.address_validation import (
    base58check_ok,
    keccak256,
    to_eip55,
    validate_address,
)
from app.services.explorers.known_vasps import KNOWN_VASPS


def _chain_of(address: str) -> str:
    """Infer the chain from an address's shape, for registries keyed by address only."""
    if address.startswith("0x"):
        return "ETH"
    if address.startswith("T"):
        return "TRON"
    return "BTC"


# ── the primitives must be correct before we trust them on registry data ────

@pytest.mark.parametrize(
    "data,expected",
    [
        (b"", "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"),
        (b"abc", "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45"),
        (b"testing", "5f16f4c7f149ac4f9510d9cf8cf384038ad348b3bcdc01915f95de12df9d1b02"),
    ],
)
def test_keccak256_matches_published_vectors(data: bytes, expected: str) -> None:
    """Guards the hand-rolled keccak against SHA3 padding confusion."""
    assert keccak256(data).hex() == expected


def test_to_eip55_matches_reference_vectors() -> None:
    # From the EIP-55 specification itself.
    for addr in (
        "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed",
        "0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359",
        "0xdbF03B407c01E7cD3CBea99509d93f8DDDC8C6FB",
        "0xD1220A0cf47c7B9Be7A2E6BA89F429762e7b9aDb",
    ):
        assert to_eip55(addr) == addr


def test_base58check_rejects_the_addresses_the_audit_found() -> None:
    """The three fabricated TRON 'VASP' addresses that were removed."""
    for fake in (
        "TNDpHN2zQ4Vv7o4B7fC1c6c5Z5c4v3b2a1",
        "TQn9Y2khEsLJW1ChVWFMSMeSTow5KaqWHg",
        "TKzxdSv2FupcmLddd6eJEmreznsPpRENx8",
    ):
        assert not base58check_ok(fake), f"{fake} should fail base58check"


def test_base58check_accepts_known_real_addresses() -> None:
    for real in (
        "TLa2f6VPqDgRE67v1736s7bJ8Ray5wYjU7",
        "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo",
    ):
        assert base58check_ok(real), f"{real} should pass base58check"


def test_validate_address_catches_the_short_bridge_address() -> None:
    """The Multichain entry was 41 chars — classify_bridge could never hit it."""
    reason = validate_address("0x6b7a87899490EcE95443e979cA9485CBE1DF413", "ETH")
    assert reason is not None
    assert "42 characters" in reason


# ── the registries themselves ───────────────────────────────────────────────

def test_every_known_vasp_address_is_structurally_valid() -> None:
    failures = [
        f"{addr} ({meta['name']}): {reason}"
        for addr, meta in KNOWN_VASPS.items()
        if (reason := validate_address(addr, _chain_of(addr))) is not None
    ]
    assert not failures, "invalid VASP registry addresses:\n  " + "\n  ".join(failures)


def test_every_known_mixer_address_is_structurally_valid() -> None:
    failures = [
        f"{addr} ({label}): {reason}"
        for addr, label in KNOWN_MIXERS.items()
        if (reason := validate_address(addr, _chain_of(addr))) is not None
    ]
    assert not failures, "invalid mixer registry addresses:\n  " + "\n  ".join(failures)


def test_every_known_bridge_address_is_structurally_valid() -> None:
    failures = [
        f"{addr} ({label}): {reason}"
        for addr, label in KNOWN_BRIDGES.items()
        if (reason := validate_address(addr, _chain_of(addr))) is not None
    ]
    assert not failures, "invalid bridge registry addresses:\n  " + "\n  ".join(failures)


def test_bridge_registry_is_not_empty() -> None:
    """
    Regression guard for the actual incident: every bridge entry was bogus, so
    bridge detection silently never fired. An empty/all-invalid registry must
    fail loudly rather than look like "no bridges on this path".
    """
    assert len(KNOWN_BRIDGES) >= 3


def test_registries_do_not_overlap() -> None:
    """An address classified as two different terminal kinds is a curation bug."""
    lower = lambda d: {a.lower() for a in d}  # noqa: E731
    vasps, mixers, bridges = lower(KNOWN_VASPS), lower(KNOWN_MIXERS), lower(KNOWN_BRIDGES)
    assert not (vasps & mixers), f"address in both VASP and mixer: {vasps & mixers}"
    assert not (vasps & bridges), f"address in both VASP and bridge: {vasps & bridges}"
    assert not (mixers & bridges), f"address in both mixer and bridge: {mixers & bridges}"
