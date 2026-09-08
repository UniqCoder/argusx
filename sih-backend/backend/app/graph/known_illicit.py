"""
app/graph/known_illicit.py — Canonical curated list of known-illicit addresses.

Single source of truth for the live-graph `illicit` enrichment task
(app/workers/tasks/illicit_enrichment.py). Addresses here are documented in
the repo as sanctions/illicit controls:

  - Garantex deposit address (OFAC-recorded, BTC) — also referenced by
    app/ml/shap_report.py and app/ml/broadened_ood_validation.py.
  - Lazarus Group proxy address (TRON) — documented in app/ml/shap_report.py.

The live graph stores these flags so graph topology features
(illicit_neighbor_ratio_1hop/2hop, shortest_path_to_known_illicit) can be
non-degenerate at runtime. Flags are idempotently SET true by the task.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.schemas.common import Chain


@dataclass(frozen=True)
class KnownIllicitWallet:
    label: str
    address: str
    chain: Chain
    source: str


KNOWN_ILLICIT_WALLETS: tuple[KnownIllicitWallet, ...] = (
    KnownIllicitWallet(
        label="garantex_ofac",
        address="3Lpoy53K625zVeE47ZasiG5jGkAxJ27kh1",
        chain=Chain.BTC,
        source="OFAC / documented in shap_report.py + broadened_ood_validation.py",
    ),
    KnownIllicitWallet(
        label="lazarus_group_proxy",
        address="TLa2f6VPqDMsaxQVj7FSrsDjjQuT5Zox1g",
        chain=Chain.TRON,
        source="documented in shap_report.py (Lazarus Group proxy)",
    ),
)

# Case statuses that imply a wallet is a confirmed (enforcement) actor rather
# than merely a suspected lead. Wallets linked to such cases are enriched too.
ILLICIT_CASE_STATUSES: tuple[str, ...] = ("frozen",)