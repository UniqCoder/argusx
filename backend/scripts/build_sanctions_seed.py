"""
app/scripts -> backend/scripts/build_sanctions_seed.py — OFAC SDN digital-currency seed builder.

Re-runnable ingestion pipeline that downloads the official OFAC Sanctions List Service
(SLS) feeds, extracts the digital-currency address records for a curated set of
designations, validates every address per chain, and writes a provenance-annotated
JSON seed consumable by the risk registry (USP 2 sanctions interception).

Feeds (official, Sanctions List Service v2.0.0):
  * SDN_XML.ZIP  -> SDN.XML           (legacy model; idType="Digital Currency Address - XBT/ETH")
  * SDN_ADVANCED.ZIP -> SDN_ADVANCED.XML (advanced model; FeatureTypeID 344=XBT, 345=ETH,
                                          VersionDetail DetailTypeID=1432 holds the address)

Chain validators are dependency-free:
  BTC: base58check (P2PKH 0x00 / P2SH 0x05) or bech32/bech32m with HRP "bc".
  ETH: 0x[hex]{40}; EIP-55 checksum enforced for mixed-case addresses (embedded
       Keccak-256, validated against known-answer vectors at startup).

Usage (from backend root):
    python -m scripts.build_sanctions_seed [--out app/data/sanctions_seed.json]
                                           [--workspace .sdn_cache] [--keep-feeds] [--use-cached]
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from typing import Iterable, Optional

import httpx
import xml.etree.ElementTree as ET

ADV_NS = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ADVANCED_XML"
ADV_Q = lambda t: "{%s}%s" % (ADV_NS, t)  # noqa: E731

SLS_BASE = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports"

DCA_FEATURE_TYPES = {"344": "XBT", "345": "ETH"}

# Curated designations -> name substrings matched (case-insensitive) against the
# official feeds' primary names.  Tornado Cash is covered via its designated
# developer record (Semenov Roman); see COVERAGE_NOTES.
TARGET_DESIGNATIONS = [
    {"key": "garantex_europe_ou", "match": ["garantex europe"], "display": "Garantex Europe OU"},
    {"key": "hydra_market", "match": ["hydra market"], "display": "Hydra Market"},
    {"key": "tornado_cash_semenov", "match": ["semenov"], "display": "Semenov Roman (Tornado Cash co-founder)"},
]

COVERAGE_NOTES = [
    "The official SDN feed's structured digital-currency-address field for the "
    "Tornado Cash designation contains only the developer/associated wallet "
    "addresses (Semenov Roman, 8 ETH).  The mixer's smart-contract addresses are "
    "NOT published in the structured field of the current official releases — no "
    "'Tornado Cash' entity row carries digital currency address ids.  Coverage is "
    "therefore partial relative to the full Tornado Cash designation and must be "
    "documented as such; this seed does NOT claim complete coverage of the mixer.",
]

# -------------------------------------------------------------------------------------
# Keccak-256 (original Keccak, used by EIP-55) — dependency-free, self-tested.
_KECCAK_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
_KECCAK_R = [
    [0, 36, 3, 41, 18],
    [1, 44, 10, 45, 2],
    [62, 6, 43, 15, 61],
    [28, 55, 25, 21, 56],
    [27, 20, 39, 8, 14],
]
_MASK64 = (1 << 64) - 1


def _roll(x: int, n: int) -> int:
    n %= 64
    return ((x << n) | (x >> (64 - n))) & _MASK64 if n else x


def _keccak_f1600(state: list[int]) -> None:
    for rc in _KECCAK_RC:
        c = [state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20] for x in range(5)]
        for x in range(5):
            d = c[(x + 4) % 5] ^ _roll(c[(x + 1) % 5], 1)
            for y in range(0, 25, 5):
                state[x + y] ^= d
        b = [0] * 25
        for x in range(5):
            for y in range(5):
                b[y + 5 * ((2 * x + 3 * y) % 5)] = _roll(state[x + 5 * y], _KECCAK_R[x][y])
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] = b[x + 5 * y] ^ ((~b[(x + 1) % 5 + 5 * y]) & b[(x + 2) % 5 + 5 * y])
        state[0] ^= rc


def keccak256(data: bytes) -> bytes:
    rate = 136
    state = [0] * 25
    blocks = len(data) - len(data) % rate
    for off in range(0, blocks, rate):
        for i in range(rate):
            state[i // 8] ^= data[off + i] << (8 * (i % 8))
        _keccak_f1600(state)
    final = bytearray(data[blocks:])
    final.append(0x01)
    final.extend(b"\x00" * (rate - len(final) % rate))
    final[-1] |= 0x80
    for i in range(rate):
        state[i // 8] ^= final[i] << (8 * (i % 8))
    _keccak_f1600(state)
    out = b"".join(s.to_bytes(8, "little") for s in state[: rate // 8])
    return out[:32]


# -------------------------------------------------------------------------------------
# Chain validators
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _b58decode(s: str) -> bytes:
    n = 0
    for ch in s:
        n = n * 58 + BASE58_ALPHABET.index(ch)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    pad = len(s) - len(s.lstrip("1"))
    return b"\x00" * pad + raw


def validate_btc(address: str) -> tuple[bool, str]:
    if not (26 <= len(address) <= 62):
        return False, "bad_length"
    if address.startswith("bc1"):
        return validate_bech32(address)
    if address[0] in ("1", "3"):
        try:
            raw = _b58decode(address)
            if len(raw) != 25:
                return False, "not_base58check25"
            payload, checksum = raw[:-4], raw[-4:]
            if hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4] != checksum:
                return False, "checksum_mismatch"
            if payload[0] not in (0x00, 0x05):
                return False, "unsupported_version"
            return True, "base58check"
        except ValueError:
            return False, "invalid_base58"
    return False, "unsupported_prefix"


def _bech32_polymod(values: list[int]) -> int:
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        top = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            if (top >> i) & 1:
                chk ^= gen[i]
    return chk


def _bech32_hrp_expand(hrp: str) -> list[int]:
    return [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]


def validate_bech32(address: str) -> tuple[bool, str]:
    if len(address) < 14 or len(address) > 74:
        return False, "bad_length"
    pos = address.rfind("1")
    if pos < 2:
        return False, "no_separator"
    hrp, data = address[:pos], address[pos + 1:]
    try:
        vals = [BECH32_CHARSET.index(c) for c in data]
    except ValueError:
        return False, "invalid_charset"
    if vals[0] > 16:
        return False, "bad_witness_version"
    chk = _bech32_polymod(_bech32_hrp_expand(hrp) + vals)
    if chk not in (1, 0x2BC830A3):
        return False, "bad_checksum"
    return True, "bech32"


def _eip55_checksum_valid(address: str) -> bool:
    lower_hex = address[2:].lower()
    orig = address[2:]
    digest = keccak256(lower_hex.encode("ascii")).hex()
    for i, ch in enumerate(lower_hex):
        if ch in "0123456789":
            continue
        should_upper = (int(digest[i], 16) & 8) != 0
        if orig[i].isupper() != should_upper:
            return False
    return True


def validate_eth(address: str) -> tuple[bool, str]:
    if len(address) != 42 or not address.startswith("0x"):
        return False, "bad_format"
    hex_body = address[2:]
    if not all(c in "0123456789abcdefABCDEF" for c in hex_body):
        return False, "not_hex"
    is_all_lower = hex_body == hex_body.lower()
    is_all_upper = hex_body == hex_body.upper()
    if is_all_lower or is_all_upper:
        return True, "hex40"
    return (True, "eip55") if _eip55_checksum_valid(address) else (False, "eip55_mismatch")


def validate_address(chain: str, address: str) -> tuple[bool, str]:
    address = address.strip()
    if chain == "XBT":
        return validate_btc(address)
    if chain == "ETH":
        return validate_eth(address)
    return False, "unsupported_chain"


# -------------------------------------------------------------------------------------
# Feed acquisition + extraction
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download_sls(filename: str, workspace: str, use_cached: bool) -> tuple[bytes, str, str]:
    """Return (file_bytes, local_path, sha256)."""
    dest = os.path.join(workspace, filename)
    if use_cached and os.path.exists(dest):
        data = open(dest, "rb").read()
        return data, dest, sha256_bytes(data)
    url = f"{SLS_BASE}/{filename}"
    r = httpx.get(url, timeout=600, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    data = r.content
    open(dest, "wb").write(data)
    return data, dest, sha256_bytes(data)


def feed_release_date(advanced_xml: bytes) -> str:
    head = advanced_xml[:8192].decode("utf-8", "replace")
    m = re.search(r"<Year>(\d+)</Year>\s*<Month>(\d+)</Month>\s*<Day>(\d+)</Day>", head)
    if not m:
        return ""
    y, mo, d = m.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def advanced_dca_rows(advanced_xml: bytes) -> list[dict]:
    """Extract (primary_name, chain, address) from the advanced model.

    Chain derived from FeatureTypeID 344 (XBT) / 345 (ETH); address is the
    VersionDetail (DetailTypeID 1432) under the feature's FeatureVersion.
    Each Feature carrying an IdentityReference IdentityID is attributed to the
    identity whose ID matches.
    """
    ctx = ET.iterparse(io.BytesIO(advanced_xml), events=("end",))
    rows: list[dict] = []
    for _ev, el in ctx:
        if el.tag != ADV_Q("DistinctParty"):
            continue
        for prof in el.findall(ADV_Q("Profile")):
            for ident in prof.findall(ADV_Q("Identity")):
                iid = ident.get("ID")
                name = ""
                for al in ident.findall(ADV_Q("Alias")):
                    if al.get("Primary") == "true":
                        parts = [npv.text or "" for npv in al.iter(ADV_Q("NamePartValue"))]
                        name = " ".join(p for p in parts if p).strip()
                        break
                for f in prof.findall(ADV_Q("Feature")):
                    ft = f.get("FeatureTypeID")
                    if ft not in DCA_FEATURE_TYPES:
                        continue
                    vd = f.findtext(f"{ADV_Q('FeatureVersion')}/{ADV_Q('VersionDetail')}")
                    ref_el = f.find(ADV_Q("IdentityReference"))
                    ref = ref_el.get("IdentityID") if ref_el is not None else None
                    if ref == iid and vd and vd.strip():
                        rows.append({"name": name, "chain": DCA_FEATURE_TYPES[ft], "address": vd.strip()})
        el.clear()
    return rows


def legacy_target_meta(legacy_xml: bytes) -> dict[str, dict]:
    """Extract per-entry metadata (list, programs, uid) from the legacy SDN.XML.

    Returns target_key -> meta map.
    """
    root = ET.fromstring(legacy_xml)
    ns = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""
    qx = lambda t: "{%s}%s" % (ns, t) if ns else t  # noqa: E731
    meta: dict[str, dict] = {}
    for ent in root.findall(f".//{qx('sdnEntry')}"):
        org = (ent.findtext(f"{qx('lastName')}") or "").strip()
        low_name = org.lower()
        target_key = None
        for d in TARGET_DESIGNATIONS:
            if any(m in low_name for m in d["match"]):
                target_key = d["key"]
                break
        if not target_key:
            continue
        ids = [id_.findtext(f"{qx('idNumber')}") or "" for id_ in ent.findall(f".//{qx('id')}")]
        programs = [p.text or "" for p in ent.findall(f".//{qx('programList')}/{qx('program')}")]
        lst = ent.findtext(f"{qx('list')}") or "SDN"
        uid = ent.findtext(f"{qx('uid')}") or ""
        existing = meta.setdefault(target_key, {"list": lst, "uid": uid, "programs": set()})
        existing["programs"].update(programs)
    for k in meta:
        meta[k]["programs"] = sorted(meta[k]["programs"])
    return meta


def build_seed(out_path: str, workspace: str, keep_feeds: bool, use_cached: bool) -> dict:
    os.makedirs(workspace, exist_ok=True)
    adv_zip, adv_zip_path, adv_zip_sha = download_sls("SDN_ADVANCED.ZIP", workspace, use_cached)
    legacy_zip, legacy_zip_path, legacy_zip_sha = download_sls("SDN_XML.ZIP", workspace, use_cached)

    with zipfile.ZipFile(io.BytesIO(adv_zip)) as zf:
        adv_name = zf.namelist()[0]
        adv_xml = zf.read(adv_name)
    with zipfile.ZipFile(io.BytesIO(legacy_zip)) as zf:
        legacy_name = zf.namelist()[0]
        legacy_xml = zf.read(legacy_name)

    release_date = feed_release_date(adv_xml)
    rows = advanced_dca_rows(adv_xml)

    target_keys = {d["key"]: d for d in TARGET_DESIGNATIONS}
    match_map: dict[str, str] = {}
    for r in rows:
        low = r["name"].lower()
        for d in TARGET_DESIGNATIONS:
            if any(m in low for m in d["match"]):
                match_map.setdefault(r["address"].lower(), d["key"])

    meta = legacy_target_meta(legacy_xml)

    entities: list[dict] = []
    for key, d in target_keys.items():
        ent = {
            "designation_key": key,
            "designation": d["display"],
            "list": meta.get(key, {}).get("list", "SDN"),
            "uid": meta.get(key, {}).get("uid", ""),
            "programs": meta.get(key, {}).get("programs", []),
            "addresses": [],
        }
        seen = set()
        invalid = []
        for r in rows:
            if match_map.get(r["address"].lower()) != key:
                continue
            if r["address"].lower() in seen:
                continue
            ok, how = validate_address(r["chain"], r["address"])
            if not ok:
                invalid.append({"address": r["address"], "chain": r["chain"], "reason": how})
                continue
            seen.add(r["address"].lower())
            ent["addresses"].append({"chain": "BTC" if r["chain"] == "XBT" else "ETH", "address": r["address"], "validated": how})
        ent["address_count"] = len(ent["addresses"])
        ent["invalid_rows"] = invalid
        entities.append(ent)

    total = sum(e["address_count"] for e in entities)
    seed = {
        "schema_version": 1,
        "generated_by": "backend/scripts/build_sanctions_seed.py",
        "source": {
            "organization": "US Department of the Treasury, Office of Foreign Assets Control (OFAC)",
            "feed_host": "Sanctions List Service (https://sanctionslistservice.ofac.treas.gov)",
            "files": [
                {"filename": "SDN_ADVANCED.ZIP", "download_url": f"{SLS_BASE}/SDN_ADVANCED.ZIP", "member": adv_name, "sha256": adv_zip_sha},
                {"filename": "SDN_XML.ZIP", "download_url": f"{SLS_BASE}/SDN_XML.ZIP", "member": legacy_name, "sha256": legacy_zip_sha},
            ],
            "feed_release_date": release_date,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
        "covering": {
            "designations": [d["display"] for d in TARGET_DESIGNATIONS],
            "address_count": total,
            "validator": {"BTC": "base58check mainnet P2PKH/P2SH + bech32/bech32m (HRP bc)", "ETH": "0x hex-40 + EIP-55 checksum (embedded Keccak-256)"},
        },
        "coverage_notes": COVERAGE_NOTES,
        "designations": entities,
    }
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(seed, fh, indent=2)
    if not keep_feeds:
        shutil.rmtree(workspace, ignore_errors=True)
    return seed


def self_test() -> None:
    assert keccak256(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
    assert keccak256(b"abc").hex() == "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45"
    assert validate_eth("0x52908400098527886E0F7030069857D2E4169EE7") == (True, "hex40")
    assert validate_eth("0xde709f2102306220921060314715629080e2fb77") == (True, "hex40")
    assert validate_eth("0x5AEDA56215b167893e80B4fE645BA6d5Bab767DE") == (True, "eip55")
    assert validate_eth("0x5aEDA56215b167893e80B4fE645BA6d5Bab767DE") == (False, "eip55_mismatch")
    assert validate_btc("1FfmbHfnpaZjKFvyi1okTjJJusN455paPH")[0]
    assert validate_btc("bc1q8c6fshw2dlwun7ekn9qwf37cu2rn755upcp6el")[0]


def main() -> None:
    ap = argparse.ArgumentParser(description="Build curated OFAC SDN digital-currency sanctions seed.")
    ap.add_argument("--out", default="app/data/sanctions_seed.json")
    ap.add_argument("--workspace", default=None, help="Temp dir for downloaded feeds (default: system temp)")
    ap.add_argument("--keep-feeds", action="store_true", help="Keep downloaded feeds after generation")
    ap.add_argument("--use-cached", action="store_true", help="Reuse previously downloaded feeds in workspace")
    args = ap.parse_args()

    self_test()
    ws = args.workspace or tempfile.mkdtemp(prefix="sdn_feeds_")
    print(f"[sanctions_seed] workspace={ws}")
    seed = build_seed(args.out, ws, args.keep_feeds or bool(args.workspace), args.use_cached)
    print(f"[sanctions_seed] wrote {args.out}")
    for e in seed["designations"]:
        print(f"  {e['designation']}: {e['address_count']} addresses  "
              f"(invalid={len(e['invalid_rows'])}) programs={e['programs']} list={e['list']}")
    print(f"[sanctions_seed] total curated addresses: {seed['covering']['address_count']}")
    print("[sanctions_seed] feed release:", seed["source"]["feed_release_date"])


if __name__ == "__main__":
    main()