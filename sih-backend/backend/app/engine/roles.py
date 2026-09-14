"""
app/engine/roles.py — Who is who in a fund-flow graph.

A graph of addresses and arrows tells an investigator very little on its own.
The question a case actually turns on is "which of these wallets is the
fraudster, which is the victim, and where did the money end up" — and that was
being left entirely to the reader.

Roles here are DERIVED from graph shape and the engine's own terminal
classification, never asserted. Every role ships with a `basis`: one sentence
naming the specific observation that produced it. A label a reader cannot
check is worse than no label, because it looks like a finding.

WHAT THIS DOES NOT DO
---------------------
It does not identify people. `PRIMARY_SUSPECT` means "the wallet the complaints
name and the money converges on", which is a statement about a graph, not an
accusation about a person. The wording of every basis string is chosen to keep
that distinction visible.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable, Optional


class NodeRole(str, Enum):
    VICTIM_SOURCE = "VICTIM_SOURCE"        # funded the reported wallet
    PRIMARY_SUSPECT = "PRIMARY_SUSPECT"    # reported wallet, money converges here
    REPORTED_WALLET = "REPORTED_WALLET"    # the anchor, without convergence
    DISTRIBUTOR = "DISTRIBUTOR"            # splits funds many ways (fan-out)
    PEEL_HOP = "PEEL_HOP"                  # forwards most, sheds a little
    LAYERING_MULE = "LAYERING_MULE"        # pass-through hop
    MIXER = "MIXER"                        # curated mixer contract
    BRIDGE = "BRIDGE"                      # curated bridge contract
    CASH_OUT = "CASH_OUT"                  # last wallet before an exchange
    EXCHANGE_DEPOSIT = "EXCHANGE_DEPOSIT"  # attributed VASP address
    PARKED_FUNDS = "PARKED_FUNDS"          # received, never moved
    DUST_BRANCH = "DUST_BRANCH"            # below the economic floor
    UNRESOLVED = "UNRESOLVED"              # budget or explorer stopped us


# Roles that mean "the money is still here and might be freezable".
RECOVERABLE_ROLES = {NodeRole.PARKED_FUNDS, NodeRole.EXCHANGE_DEPOSIT}


@dataclass
class NodeAnnotation:
    role: str
    role_basis: str
    description: str
    value_in: float = 0.0
    value_out: float = 0.0
    value_parked: float = 0.0
    cluster_id: Optional[str] = None
    cluster_label: Optional[str] = None


def _fmt(value: float, asset: str) -> str:
    if value >= 1000:
        return f"{value:,.2f} {asset}"
    if value >= 1:
        return f"{value:,.4f}".rstrip("0").rstrip(".") + f" {asset}"
    return f"{value:.8f}".rstrip("0").rstrip(".") + f" {asset}"


def _minutes_between(a: Optional[datetime], b: Optional[datetime]) -> Optional[float]:
    if a is None or b is None:
        return None
    return abs((b - a).total_seconds()) / 60.0


def annotate(
    nodes: list,
    anchor_address: str,
    anchor_chain: str,
    asset: str,
    inbound_sources: Optional[list] = None,
    complaint_count: int = 0,
) -> dict[tuple[str, str], NodeAnnotation]:
    """
    Role, basis and plain-English description for every node in a trace.

    `nodes` are `TaintedNode`s; `inbound_sources` are the wallets observed
    funding the anchor (see app/engine/taint.py), which is what lets the graph
    show the victim side at all — the BFS only walks forwards.
    """
    key = lambda n: (n.address.lower(), n.chain)  # noqa: E731
    by_key = {key(n): n for n in nodes}

    # Children, from the parent pointer each node carries.
    children: dict[tuple[str, str], list] = {k: [] for k in by_key}
    for n in nodes:
        if not n.parent_address:
            continue
        pk = (n.parent_address.lower(), n.chain)
        if pk not in children:
            # A cross-chain child's parent sits on the source chain.
            pk = next(
                (k for k in by_key if k[0] == n.parent_address.lower()), None
            )
        if pk is not None:
            children.setdefault(pk, []).append(n)

    # A parent's "child" here is a small stand-in object, not a full
    # TaintedNode, because a convergent payer only has an edge into an
    # already-settled node -- there is no second node to point at. It carries
    # exactly what leads_to_vasp / value_out below actually read.
    class _ConvergentChild:
        __slots__ = ("terminal_kind", "entity_name", "tx_amount", "first_tainted_at")

        def __init__(self, terminal_kind, entity_name, tx_amount, first_tainted_at):
            self.terminal_kind = terminal_kind
            self.entity_name = entity_name
            self.tx_amount = tx_amount
            self.first_tainted_at = first_tainted_at

    for n in nodes:
        for edge in getattr(n, "convergent_parents", []) or []:
            pk = (edge["address"].lower(), edge["chain"])
            if pk not in children:
                pk = next((k for k in by_key if k[0] == edge["address"].lower()), None)
            if pk is None:
                continue
            children.setdefault(pk, []).append(
                _ConvergentChild(n.terminal_kind, n.entity_name, edge["tx_amount"], edge["first_tainted_at"])
            )

    annotations: dict[tuple[str, str], NodeAnnotation] = {}
    anchor_key = (anchor_address.lower(), anchor_chain)
    sources = inbound_sources or []

    # ── The victim side ─────────────────────────────────────────────────────
    for src in sources:
        annotations[(src.address.lower(), src.chain)] = NodeAnnotation(
            role=NodeRole.VICTIM_SOURCE.value,
            role_basis=(
                f"Sent {_fmt(src.amount, asset)} to the reported wallet and received "
                f"nothing back in the observed window."
            ),
            description=(
                f"A wallet that paid into the reported address. "
                f"{_fmt(src.amount, asset)} on "
                f"{src.timestamp.strftime('%d %b %Y, %H:%M UTC') if src.timestamp else 'an unrecorded date'}."
            ),
            value_out=src.amount,
        )

    for n in nodes:
        k = key(n)
        kids = children.get(k, [])
        value_out = sum(c.tx_amount or 0.0 for c in kids)
        value_in = n.tx_amount if n.tx_amount is not None else n.taint_value
        terminal = n.terminal_kind

        # ── Terminals: the engine has already classified these ──────────────
        if terminal == "MIXER_BOUNDARY":
            ann = NodeAnnotation(
                role=NodeRole.MIXER.value,
                role_basis=(
                    f"This address is {n.entity_name or 'a curated mixer contract'} in the "
                    f"mixer registry. Funds entering a mixing pool cannot be followed out."
                ),
                description=(
                    f"Mixer. {_fmt(n.taint_value, asset)} entered "
                    f"{n.entity_name or 'this pool'} and the trail ends here — not because "
                    f"the trace ran out of budget, but because the link between deposits "
                    f"and withdrawals is genuinely broken by design."
                ),
                value_in=value_in,
            )
        elif terminal == "BRIDGE":
            crossed = [c for c in kids if getattr(c, "link_basis", "") == "CROSS_CHAIN_HEURISTIC"]
            ann = NodeAnnotation(
                role=NodeRole.BRIDGE.value,
                role_basis=(
                    f"This address is {n.entity_name or 'a curated bridge contract'} in the "
                    f"bridge registry."
                    + (
                        f" A matching release was found on {crossed[0].chain}, so the trail continues there."
                        if crossed
                        else " No matching release was found, so the trail stops here."
                    )
                ),
                description=(
                    f"Cross-chain bridge. {_fmt(n.taint_value, asset)} was deposited into "
                    f"{n.entity_name or 'this bridge'}"
                    + (
                        f" and reappeared on {crossed[0].chain}. That continuation is a value-and-time "
                        f"correlation, not a signed transaction — it is drawn as a dashed edge for that reason."
                        if crossed
                        else ". The destination-chain address is not derivable from the deposit alone."
                    )
                ),
                value_in=value_in,
                value_out=value_out,
            )
        elif terminal == "VASP":
            ann = NodeAnnotation(
                role=NodeRole.EXCHANGE_DEPOSIT.value,
                role_basis=(
                    f"This address is attributed to {n.entity_name or 'a known exchange'}"
                    + (f" ({n.entity_jurisdiction})" if n.entity_jurisdiction else "")
                    + " in the VASP registry."
                ),
                description=(
                    f"Exchange off-ramp. {_fmt(n.taint_value, asset)} of traced funds reached "
                    f"{n.entity_name or 'an exchange'}"
                    + (f", jurisdiction {n.entity_jurisdiction}" if n.entity_jurisdiction else "")
                    + ". This is the actionable end of the trail: an exchange holds KYC on the "
                    "account behind a deposit address and can freeze it on a valid request."
                ),
                value_in=value_in,
            )
        elif terminal == "NO_OUTFLOW":
            ann = NodeAnnotation(
                role=NodeRole.PARKED_FUNDS.value,
                role_basis=(
                    "No outgoing transaction was observed from this address after it "
                    "received the traced funds."
                ),
                description=(
                    f"Funds still here. {_fmt(n.taint_value, asset)} arrived and has not moved. "
                    f"This is the only kind of branch a freeze request can still reach — "
                    f"everything that has already cashed out cannot be un-sent."
                ),
                value_in=value_in,
                value_parked=n.taint_value,
            )
        elif terminal in ("DUST", "DILUTED_OUTFLOW"):
            ann = NodeAnnotation(
                role=NodeRole.DUST_BRANCH.value,
                role_basis=(
                    "The apportioned value on this branch fell below the economic dust "
                    "floor for this asset, so following it further would cost more than "
                    "it could recover."
                ),
                description=(
                    f"Below the dust floor. {_fmt(n.taint_value, asset)} — real, but too "
                    f"small to be worth chasing. Counted, not hidden."
                ),
                value_in=value_in,
            )
        elif terminal in ("NODE_LIMIT", "DEPTH_LIMIT", "EXPLORER_UNAVAILABLE"):
            reason = {
                "NODE_LIMIT": "the trace hit its node budget with this branch still unexplored",
                "DEPTH_LIMIT": (
                    "the trace reached its hop limit here"
                    if n.chain in ("BTC", "ETH", "TRON")
                    else f"there is no live explorer for {n.chain}, so this address cannot be walked"
                ),
                "EXPLORER_UNAVAILABLE": "the blockchain explorer was unreachable for this address",
            }[terminal]
            ann = NodeAnnotation(
                role=NodeRole.UNRESOLVED.value,
                role_basis=f"Not a dead end — {reason}.",
                description=(
                    f"Unresolved. {_fmt(n.taint_value, asset)} was still moving when "
                    f"{reason}. Re-running with a larger budget, or when the explorer "
                    f"recovers, would continue from here. This is explicitly NOT a finding "
                    f"that the money stopped."
                ),
                value_in=value_in,
            )

        # ── The anchor ──────────────────────────────────────────────────────
        elif k == anchor_key:
            funders = len(sources)
            window = None
            if len(sources) >= 2:
                times = [s.timestamp for s in sources if s.timestamp]
                if len(times) >= 2:
                    window = _minutes_between(min(times), max(times))
            converged = funders >= 2 or complaint_count >= 2
            if converged:
                basis_bits = []
                if complaint_count >= 2:
                    basis_bits.append(f"named by {complaint_count} separate complaints")
                if funders >= 2:
                    bit = f"received funds from {funders} distinct wallets"
                    if window is not None:
                        bit += f" within {window:.0f} minutes"
                    basis_bits.append(bit)
                ann = NodeAnnotation(
                    role=NodeRole.PRIMARY_SUSPECT.value,
                    role_basis=(
                        "The reported wallet, and the point every traced payment converges on: "
                        + " and ".join(basis_bits)
                        + ". Independent victims paying one address is the fraud signal."
                    ),
                    description=(
                        f"Collector wallet — the operator-controlled address victims were told to pay. "
                        f"It took in {_fmt(n.taint_value, asset)}"
                        + (f" from {funders} separate victim wallets" if funders >= 2 else "")
                        + (f" and moved it onward within {window:.0f} minutes" if window is not None else "")
                        + ". This is the strongest attribution in the graph, and it is a statement "
                        "about wallets, not about an identified person."
                    ),
                    value_in=n.taint_value,
                    value_out=value_out,
                )
            else:
                ann = NodeAnnotation(
                    role=NodeRole.REPORTED_WALLET.value,
                    role_basis="The address this investigation was anchored on.",
                    description=(
                        f"The reported wallet. {_fmt(n.taint_value, asset)} of traced value "
                        f"starts here"
                        + (
                            f", split across {len(kids)} onward transfers."
                            if kids
                            else "."
                        )
                    ),
                    value_in=n.taint_value,
                    value_out=value_out,
                )

        # ── Intermediate hops ───────────────────────────────────────────────
        else:
            leads_to_vasp = any(c.terminal_kind == "VASP" for c in kids)
            out_count = len(kids)
            if leads_to_vasp:
                exchange = next(
                    (c.entity_name for c in kids if c.terminal_kind == "VASP"), "an exchange"
                )
                ann = NodeAnnotation(
                    role=NodeRole.CASH_OUT.value,
                    role_basis=f"The last wallet in the chain before funds reached {exchange}.",
                    description=(
                        f"Cash-out wallet. Held {_fmt(n.taint_value, asset)} and sent it "
                        f"straight to a {exchange} deposit address. This is the wallet an "
                        f"exchange freeze request would name."
                    ),
                    value_in=value_in, value_out=value_out,
                )
            elif out_count >= 4:
                amounts = [c.tx_amount or 0.0 for c in kids]
                spread = (max(amounts) - min(amounts)) / max(amounts) if max(amounts) else 1.0
                structured = spread < 0.1
                ann = NodeAnnotation(
                    role=NodeRole.DISTRIBUTOR.value,
                    role_basis=(
                        f"Split its balance across {out_count} onward addresses"
                        + (
                            f", all within {spread * 100:.1f}% of the same size — the signature of "
                            f"deliberate structuring rather than ordinary spending."
                            if structured
                            else "."
                        )
                    ),
                    description=(
                        f"Distribution wallet. {_fmt(n.taint_value, asset)} was fanned out to "
                        f"{out_count} addresses"
                        + (
                            " in near-identical amounts, which is how a single sum is made to "
                            "look like many unrelated small ones."
                            if structured
                            else "."
                        )
                    ),
                    value_in=value_in, value_out=value_out,
                )
            elif out_count == 2 and value_out > 0:
                amounts = sorted((c.tx_amount or 0.0 for c in kids), reverse=True)
                if amounts[0] > 0 and amounts[1] / amounts[0] < 0.25:
                    ann = NodeAnnotation(
                        role=NodeRole.PEEL_HOP.value,
                        role_basis=(
                            f"Forwarded {amounts[0] / value_out * 100:.0f}% of its balance onward "
                            f"and peeled off the remainder — the repeating unit of a peel chain."
                        ),
                        description=(
                            f"Peel-chain hop. {_fmt(amounts[0], asset)} continued down the chain "
                            f"while {_fmt(amounts[1], asset)} was shed to the side. Repeating this "
                            f"erodes the traceable balance one small step at a time."
                        ),
                        value_in=value_in, value_out=value_out,
                    )
                else:
                    ann = _mule(n, kids, value_in, value_out, asset)
            else:
                ann = _mule(n, kids, value_in, value_out, asset)

        annotations[k] = ann

    return annotations


def _mule(n, kids: Iterable, value_in: float, value_out: float, asset: str) -> NodeAnnotation:
    kids = list(kids)
    held = _minutes_between(
        n.first_tainted_at,
        min((c.first_tainted_at for c in kids if c.first_tainted_at), default=None),
    )
    return NodeAnnotation(
        role=NodeRole.LAYERING_MULE.value,
        role_basis=(
            "A pass-through hop: funds arrived and were forwarded onward"
            + (f" after {held:.0f} minutes" if held is not None else "")
            + ", with no other observed purpose."
        ),
        description=(
            f"Layering wallet. {_fmt(n.taint_value, asset)} passed through"
            + (
                f" and left again after {held:.0f} minutes."
                if held is not None and held < 120
                else "."
            )
            + " Hops like this exist to add distance between the victim and the cash-out, "
            "not to do anything with the money."
        ),
        value_in=value_in,
        value_out=value_out,
    )
