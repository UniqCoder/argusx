"""
app/engine/typologies.py — Naming the laundering patterns a trace exhibits.

Each detector answers one question with a yes/no trigger condition and, on a
match, a plain-English sentence naming exactly what was observed. Nothing here
computes a score: item detection feeds the risk NARRATIVE ("why is this
flagged"), never a number that could substitute for the decision engine's own
Class-A-anchor requirement. See app/engine/decision.py and
IMPROVEMENTS_PLANNED.md's rejection of a fused confidence score for why that
line is enforced deliberately, not by omission.

Detectors run over the finished, role-annotated graph (app/engine/roles.py has
already run), so they can lean on `role` and `value_*` rather than
re-deriving graph shape from scratch.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional


@dataclass(frozen=True)
class Typology:
    code: str
    label: str
    narrative: str
    # Node keys (lowercased address, chain) this instance was observed on —
    # lets the UI highlight exactly which wallets triggered it, not just the
    # trace as a whole.
    node_keys: tuple[tuple[str, str], ...] = ()


def _minutes(a, b) -> Optional[float]:
    if a is None or b is None:
        return None
    return abs((b - a).total_seconds()) / 60.0


def detect(
    nodes: list,
    inbound_sources: list,
    depth_reached: int,
    anchor_address: str,
    anchor_chain: str,
) -> list[Typology]:
    """All typologies this trace exhibits, most significant first."""
    found: list[Typology] = []
    key = lambda n: (n.address.lower(), n.chain)  # noqa: E731

    # ── MULTI_HOP ────────────────────────────────────────────────────────────
    if depth_reached >= 4:
        found.append(Typology(
            code="MULTI_HOP", label="Multi-hop layering",
            narrative=f"Funds passed through {depth_reached} hops before this trace stopped following them.",
        ))

    # ── RAPID_MOVEMENT ───────────────────────────────────────────────────────
    timestamps = [n.first_tainted_at for n in nodes if n.first_tainted_at]
    if len(timestamps) >= 3:
        span = max(timestamps) - min(timestamps)
        if span <= timedelta(minutes=30):
            found.append(Typology(
                code="RAPID_MOVEMENT", label="Rapid fund movement",
                narrative=(
                    f"The entire traced chain of {len(nodes)} wallets moved within "
                    f"{span.total_seconds() / 60:.0f} minutes — far faster than ordinary use."
                ),
                node_keys=tuple(key(n) for n in nodes),
            ))

    # ── RAPID_TO_EXCHANGE ────────────────────────────────────────────────────
    vasp_nodes = [n for n in nodes if n.terminal_kind == "VASP"]
    anchor_time = next(
        (n.first_tainted_at for n in nodes if key(n) == (anchor_address.lower(), anchor_chain)),
        None,
    )
    for v in vasp_nodes:
        mins = _minutes(anchor_time, v.first_tainted_at)
        if mins is not None and mins <= 60:
            found.append(Typology(
                code="RAPID_TO_EXCHANGE", label="Rapid movement to exchange",
                narrative=(
                    f"Funds reached {v.entity_name or 'an exchange'} within {mins:.0f} minutes "
                    f"of the reported wallet receiving them — consistent with a pre-arranged cash-out."
                ),
                node_keys=(key(v),),
            ))

    # ── STRUCTURING (fan-out into near-equal amounts) ───────────────────────
    for n in nodes:
        if getattr(n, "role", None) == "DISTRIBUTOR":
            found.append(Typology(
                code="STRUCTURING", label="Structuring / smurfing",
                narrative=n.description or "One balance was split into several near-equal transfers.",
                node_keys=(key(n),),
            ))

    # ── FAN_OUT (broader than structuring: many children, any size) ─────────
    children_count: dict[tuple[str, str], int] = {}
    for n in nodes:
        if n.parent_address:
            pk = (n.parent_address.lower(), n.chain)
            children_count[pk] = children_count.get(pk, 0) + 1
    for pk, count in children_count.items():
        if count >= 5:
            found.append(Typology(
                code="FAN_OUT", label="Fan-out distribution",
                narrative=f"One wallet distributed funds to {count} separate addresses.",
                node_keys=(pk,),
            ))

    # ── PEEL_CHAIN ───────────────────────────────────────────────────────────
    peel_hops = [n for n in nodes if getattr(n, "role", None) == "PEEL_HOP"]
    if len(peel_hops) >= 2:
        found.append(Typology(
            code="PEEL_CHAIN", label="Peel chain",
            narrative=(
                f"{len(peel_hops)} consecutive hops each forwarded most of their balance while "
                f"shedding a small remainder — the repeating shape of a peel chain."
            ),
            node_keys=tuple(key(n) for n in peel_hops),
        ))

    # ── MIXER_CONTACT ────────────────────────────────────────────────────────
    for n in nodes:
        if n.terminal_kind == "MIXER_BOUNDARY":
            found.append(Typology(
                code="MIXER_CONTACT", label="Mixer / tumbler interaction",
                narrative=f"Funds entered {n.entity_name or 'a mixing service'}, breaking the traceable link.",
                node_keys=(key(n),),
            ))

    # ── BRIDGE_HOP ───────────────────────────────────────────────────────────
    bridge_nodes = [n for n in nodes if n.terminal_kind == "BRIDGE"]
    if bridge_nodes:
        crossed = [n for n in nodes if getattr(n, "link_basis", "ON_CHAIN") == "CROSS_CHAIN_HEURISTIC"]
        found.append(Typology(
            code="BRIDGE_HOP", label="Cross-chain bridge hop" + ("s" if len(bridge_nodes) > 1 else ""),
            narrative=(
                f"Funds crossed {len(bridge_nodes)} bridge contract"
                + ("s" if len(bridge_nodes) > 1 else "")
                + (
                    f", continuing onto {len(crossed)} destination-chain address"
                    f"{'es' if len(crossed) != 1 else ''} matched by value and time."
                    if crossed else "."
                )
            ),
            node_keys=tuple(key(n) for n in bridge_nodes),
        ))

    # ── DORMANT_BURST ────────────────────────────────────────────────────────
    if anchor_time is not None:
        first_outflow = min(
            (n.first_tainted_at for n in nodes if n.parent_address and n.first_tainted_at),
            default=None,
        )
        if first_outflow is not None:
            dormant_days = (first_outflow - anchor_time).days
            if dormant_days >= 7:
                found.append(Typology(
                    code="DORMANT_BURST", label="Dormant then burst",
                    narrative=(
                        f"The reported wallet sat untouched for {dormant_days} days, then moved "
                        f"its balance in a single burst — a common pattern for waiting out scrutiny."
                    ),
                ))

    # ── CROSS_VICTIM_CONVERGENCE ─────────────────────────────────────────────
    for n in nodes:
        if getattr(n, "role", None) == "PRIMARY_SUSPECT":
            found.append(Typology(
                code="CROSS_VICTIM_CONVERGENCE", label="Cross-victim convergence",
                narrative=n.role_basis or "Multiple independent sources converge on this wallet.",
                node_keys=(key(n),),
            ))

    return found


def summarize_path_risk(nodes: list, typologies: list[Typology]) -> dict:
    """
    Item 5 of IMPROVEMENTS_PLANNED.md: "expose data already computed" as a
    scored-but-not-decisive path summary. Four sub-scores in [0, 1], each with
    the observation behind it, and an overall Path Risk that is a plain
    average — deliberately simple and legible rather than a tuned model,
    because this is EXPLANATION, not the decision engine's block/hold logic.
    """
    codes = {t.code for t in typologies}

    origin_flags = []
    origin = 0.0
    if "CROSS_VICTIM_CONVERGENCE" in codes:
        origin = 0.9
        origin_flags.append("named by multiple independent sources")
    elif any(getattr(n, "role", None) == "REPORTED_WALLET" for n in nodes):
        origin = 0.3
        origin_flags.append("single reported source")

    layering = 0.0
    layering_flags = []
    depth = max((n.hop for n in nodes), default=0)
    if depth >= 6:
        layering, layering_flags = 0.85, [f"{depth} hops of layering"]
    elif depth >= 3:
        layering, layering_flags = 0.5, [f"{depth} hops of layering"]
    if "STRUCTURING" in codes:
        layering = min(1.0, layering + 0.25)
        layering_flags.append("structuring observed")
    if "RAPID_MOVEMENT" in codes:
        layering = min(1.0, layering + 0.15)
        layering_flags.append("unusually fast movement")

    mixer = 1.0 if "MIXER_CONTACT" in codes else (0.4 if "BRIDGE_HOP" in codes else 0.0)
    mixer_flags = (
        ["funds entered a mixing service"] if "MIXER_CONTACT" in codes else
        ["funds crossed a bridge"] if "BRIDGE_HOP" in codes else
        ["no mixer or bridge contact observed"]
    )

    cashout = 0.0
    cashout_flags = []
    if any(getattr(n, "role", None) == "EXCHANGE_DEPOSIT" for n in nodes):
        cashout = 0.8
        cashout_flags.append("funds reached an exchange deposit address")
    if "RAPID_TO_EXCHANGE" in codes:
        cashout = min(1.0, cashout + 0.2)
        cashout_flags.append("reached the exchange within the hour")
    if not cashout_flags:
        cashout_flags.append("no exchange off-ramp found in this trace")

    overall = round((origin + layering + mixer + cashout) / 4.0, 3)
    tier = "critical" if overall >= 0.75 else "high" if overall >= 0.5 else "medium" if overall >= 0.25 else "low"

    return {
        "overall": overall,
        "tier": tier,
        "origin_risk": {"score": round(origin, 3), "flags": origin_flags or ["no convergence signal"]},
        "layering_risk": {"score": round(layering, 3), "flags": layering_flags or ["shallow trace"]},
        "mixer_exposure": {"score": round(mixer, 3), "flags": mixer_flags},
        "cashout_proximity": {"score": round(cashout, 3), "flags": cashout_flags},
        "narrative": _narrate(overall, tier, origin_flags, layering_flags, mixer_flags, cashout_flags),
    }


def _narrate(overall, tier, origin_flags, layering_flags, mixer_flags, cashout_flags) -> str:
    bits = []
    if origin_flags:
        bits.append(origin_flags[0])
    if layering_flags:
        bits.append(layering_flags[0])
    if mixer_flags and "no mixer" not in mixer_flags[0]:
        bits.append(mixer_flags[0])
    if cashout_flags and "no exchange" not in cashout_flags[0]:
        bits.append(cashout_flags[0])
    joined = "; ".join(bits) if bits else "no significant risk indicators observed in this trace"
    return f"Path risk {overall:.0%} ({tier.upper()}): {joined}."
