"""
scripts/build_osint_snapshot.py — Regenerate the bundled ransomwhe.re OSINT snapshot.

Downloads the public ransomwhe.re bulk export and writes a compact JSON snapshot
(address, blockchain, family, created_at, updated_at) used by the OSINT module as
its in-memory index (no network dependency at lookup time).

Usage:
    python -m scripts.build_osint_snapshot

The committed asset lives at backend/app/data/osint/ransomwhe_export.json.
This is the same transformation the Celery sync task applies at runtime.
"""
import json
import sys
import urllib.request
from pathlib import Path

RANSOMWHE_EXPORT_URL = "https://api.ransomwhe.re/export"
OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "osint" / "ransomwhe_export.json"


def main() -> int:
    print(f"Downloading {RANSOMWHE_EXPORT_URL} ...")
    with urllib.request.urlopen(RANSOMWHE_EXPORT_URL, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    entries = data.get("result", [])
    compact = [{
        "address": e["address"],
        "blockchain": e.get("blockchain", "bitcoin").lower(),
        "family": e.get("family", ""),
        "created_at": e.get("createdAt", ""),
        "updated_at": e.get("updatedAt", ""),
    } for e in entries]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(compact, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {len(compact)} entries to {OUT} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
