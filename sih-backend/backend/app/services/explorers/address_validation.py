"""
app/services/explorers/address_validation.py — structural address validation.

Why this module exists (a real incident, not a hypothetical): the curated
registries in `known_vasps.py` and `app/engine/registries.py` were found to
contain **fabricated addresses** that could never match a real trace —

  - 3 TRON "known VASP" entries failed base58check (they were invented
    strings shaped like TRON addresses, e.g. "TNDpHN2zQ4Vv7o4B7fC1c6c5Z5c4v3b2a1")
  - 1 bridge entry was 41 characters long (one hex digit short of an EVM
    address), so `classify_bridge` could never return it
  - several EVM entries failed their EIP-55 case checksum, and every single
    one of those turned out to be an address that had never been used
    on-chain (zero balance, no contract, no name)

That last correlation is the useful part: an EIP-55 checksum failure is
*functionally* harmless here (registry lookups are case-insensitive), but it
proved to be a perfect predictor of a hand-invented entry. So we check it.

Everything here is pure-stdlib on purpose — the runtime image has no
`eth-hash`, `pycryptodome`, `base58`, or `web3`, and a registry integrity
check must not be the reason a dependency gets added. keccak-256 is
implemented directly below and is verified against published test vectors in
`app/tests/test_registry_integrity.py`.

This validates *structure*, not ownership: it proves an address is
well-formed and self-consistent, never that it belongs to the entity the
registry claims. Ownership is attested by the provenance comment on each
registry entry (on-chain contract name / balance observed at curation time).
"""
from __future__ import annotations

import hashlib
from typing import Optional

# ── keccak-256 (pure stdlib) ────────────────────────────────────────────────
# Needed for EIP-55. This is Keccak, NOT SHA3-256: the only difference is the
# domain padding byte (0x01 here vs 0x06 for SHA3), which is why
# hashlib.sha3_256 cannot be substituted.

_RC = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)
_ROT = (
    (0, 36, 3, 41, 18),
    (1, 44, 10, 45, 2),
    (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 56),
    (27, 20, 39, 8, 14),
)
_MASK = (1 << 64) - 1
_RATE = 136  # bytes; 1088-bit rate for keccak-256


def _rol(x: int, n: int) -> int:
    n %= 64
    return ((x << n) | (x >> (64 - n))) & _MASK


def _keccak_f(a: list[list[int]]) -> list[list[int]]:
    for rnd in range(24):
        c = [a[x][0] ^ a[x][1] ^ a[x][2] ^ a[x][3] ^ a[x][4] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                a[x][y] ^= d[x]
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                b[y][(2 * x + 3 * y) % 5] = _rol(a[x][y], _ROT[x][y])
        for x in range(5):
            for y in range(5):
                a[x][y] = b[x][y] ^ ((~b[(x + 1) % 5][y]) & b[(x + 2) % 5][y])
        a[0][0] ^= _RC[rnd]
    return a


def keccak256(data: bytes) -> bytes:
    """keccak-256 digest. Verified against published vectors in the test suite."""
    a = [[0] * 5 for _ in range(5)]
    buf = bytearray(data)
    buf.append(0x01)
    while len(buf) % _RATE != 0:
        buf.append(0x00)
    buf[-1] ^= 0x80
    for off in range(0, len(buf), _RATE):
        block = buf[off:off + _RATE]
        for i in range(_RATE // 8):
            a[i % 5][i // 5] ^= int.from_bytes(block[i * 8:i * 8 + 8], "little")
        a = _keccak_f(a)
    out = bytearray()
    for i in range(4):
        out += a[i % 5][i // 5].to_bytes(8, "little")
    return bytes(out[:32])


# ── base58check (BTC / TRON) ────────────────────────────────────────────────

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58_decode(s: str) -> bytes:
    n = 0
    for ch in s:
        idx = _B58.find(ch)
        if idx < 0:
            raise ValueError(f"invalid base58 character {ch!r}")
        n = n * 58 + idx
    body = n.to_bytes((n.bit_length() + 7) // 8, "big")
    leading_zeros = len(s) - len(s.lstrip("1"))
    return b"\x00" * leading_zeros + body


def base58check_ok(address: str) -> bool:
    """True if `address` is a structurally valid base58check string."""
    try:
        raw = _b58_decode(address)
    except ValueError:
        return False
    if len(raw) != 25:
        return False
    body, checksum = raw[:21], raw[21:]
    expected = hashlib.sha256(hashlib.sha256(body).digest()).digest()[:4]
    return checksum == expected


def _b58_encode(raw: bytes) -> str:
    n = int.from_bytes(raw, "big")
    out = ""
    while n > 0:
        n, rem = divmod(n, 58)
        out = _B58[rem] + out
    leading_zeros = len(raw) - len(raw.lstrip(bytes([0])))
    return "1" * leading_zeros + out


def base58check_encode(version: int, payload20: bytes) -> str:
    """
    Encode a 20-byte payload as a base58check address with `version` prefix.

    The inverse of `base58check_ok`. Added so seeded-scenario addresses
    (app/services/scenarios/) can be generated with a *correct* checksum rather
    than hand-typed — a malformed one would be rejected by the same validators
    that guard real input, which is exactly the bug the old frontend fixture had
    (its `0x0DEM0...` addresses contained a non-hex 'M').

    Version bytes: 0x00 = BTC P2PKH ("1..."), 0x05 = BTC P2SH ("3..."),
    0x41 = TRON ("T...").
    """
    if len(payload20) != 20:
        raise ValueError("payload must be exactly 20 bytes")
    body = bytes([version]) + payload20
    checksum = hashlib.sha256(hashlib.sha256(body).digest()).digest()[:4]
    return _b58_encode(body + checksum)


# ── EIP-55 (EVM) ────────────────────────────────────────────────────────────

def to_eip55(address: str) -> str:
    """Return `address` in canonical EIP-55 mixed-case form."""
    body = address[2:].lower()
    digest = keccak256(body.encode()).hex()
    return "0x" + "".join(
        ch.upper() if ch.isalpha() and int(digest[i], 16) >= 8 else ch
        for i, ch in enumerate(body)
    )


def _is_hex(s: str) -> bool:
    return all(c in "0123456789abcdefABCDEF" for c in s)


# ── public API ──────────────────────────────────────────────────────────────

def validate_address(address: str, chain: str) -> Optional[str]:
    """
    Structurally validate `address` for `chain`.

    Returns None when the address is well-formed, or a human-readable reason
    string when it is not. A mixed-case EVM address whose EIP-55 checksum does
    not match is reported: registry lookups are case-insensitive so it would
    still *function*, but in this codebase a checksum mismatch has always
    meant a hand-invented address.
    """
    addr = address.strip()
    if not addr:
        return "empty address"

    if chain in ("ETH", "BSC", "Polygon"):
        if not addr.startswith("0x"):
            return "EVM address must start with 0x"
        if len(addr) != 42:
            return f"EVM address must be 42 characters, got {len(addr)}"
        if not _is_hex(addr[2:]):
            return "EVM address contains non-hex characters"
        body = addr[2:]
        if body != body.lower() and body != body.upper() and to_eip55(addr) != addr:
            return f"EIP-55 checksum mismatch (canonical form is {to_eip55(addr)})"
        return None

    if chain == "TRON":
        if not addr.startswith("T"):
            return "TRON base58 address must start with T"
        if len(addr) != 34:
            return f"TRON address must be 34 characters, got {len(addr)}"
        if not base58check_ok(addr):
            return "TRON base58check failed — not a real address"
        return None

    if chain == "BTC":
        if addr.startswith(("bc1", "tb1")):
            # Bech32 has its own checksum; we only bound the length here rather
            # than claim a validation we have not implemented.
            if not (14 <= len(addr) <= 74):
                return f"bech32 address length {len(addr)} out of range"
            if addr != addr.lower() and addr != addr.upper():
                return "bech32 must not be mixed case"
            return None
        if addr[0] not in "13":
            return "BTC base58 address must start with 1 or 3"
        if not (26 <= len(addr) <= 35):
            return f"BTC address length {len(addr)} out of range"
        if not base58check_ok(addr):
            return "BTC base58check failed — not a real address"
        return None

    return f"unknown chain {chain!r}"
