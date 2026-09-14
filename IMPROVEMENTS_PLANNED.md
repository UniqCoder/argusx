# ARGUS — Planned Improvements (not yet built)

This file tracks the 5 improvements we picked from `ARGUS_Improvements_Blueprint.md`
to actually build on top of the v2 provenance engine (`ARGUS-ENGINE-V2.md`). Nothing
in this file is implemented yet — this is the plan, written in plain language, so
anyone can pick it up later without re-deriving the reasoning.

Each entry says: what it is, why we picked it, and how it plugs into the engine
that already exists (Layer 0 anchors → Layer 1 taint trace → Layer 5 decision).

Status legend: 🔲 not started · 🟡 in progress · ✅ done

---

## 1. 🔲 Unknown as a first-class state

**What it does:** Right now the engine's decision can only be `monitor`,
`hold_for_review`, or `block`. If there's genuinely no evidence yet — no anchor,
no ML score, nothing computed — the system currently falls through to `monitor`,
which silently looks the same as "we checked and it's clean." We add a fourth
state, `unknown`, so "haven't looked yet" and "looked and it's fine" are never
the same answer.

**Why it matters:** This is the rule the whole blueprint kept repeating —
*"unknown ≠ low risk."* Right now the code doesn't actually enforce that rule
in the one place it matters most: the decision output itself.

**How it fits the flow:**
```
decide() in app/engine/decision.py
   ├─ Class-A anchor + taint trace + qualifying terminal → block   (unchanged)
   ├─ ML score >= threshold                              → hold_for_review (unchanged)
   ├─ anchor present but evidence thin                    → hold_for_review (unchanged)
   ├─ NEW: nothing computed yet / required data missing   → unknown
   └─ everything checked, nothing found                   → monitor (unchanged)
```
One new enum value on `DecisionAction`, one new branch in `decide()`. No change
to the block/hold logic — this only adds a state for "haven't checked" that
didn't exist before.

---

## 2. 🔲 Negative intelligence ("we checked, it's clean")

**What it does:** A dedicated response shape for when the engine actually
looked — sanctions, known-entity, taint trace, ML — and found nothing. Instead
of just silence or a bare `monitor`, the wallet gets an explicit clean bill:

```
Sanctions            NONE
Known entity         NONE
Illicit neighbors    NONE
OVERALL              LOW RISK
EVIDENCE COMPLETENESS  HIGH
```

**Why it matters:** This is the flip side of item 1. Once `unknown` exists to
mean "we haven't checked," `monitor` needs to confidently mean "we checked
everything and it's genuinely fine" — not just "nothing happened to flag it."
It also stops investigators from re-investigating wallets the system already
cleared.

**How it fits the flow:** Sits right after `decide()` returns `monitor` — reads
the same anchor/terminal/ML inputs `decide()` already looked at and turns
"nothing matched" into an explicit statement instead of an empty response.
Needs item 1 done first so "checked, clean" and "not checked" can't collide.

---

## 3. 🔲 Known-entity allowlist

**What it does:** A short list of addresses we already know are legitimate —
major exchange cold wallets, foundation wallets, protocol treasuries. Before
the ML model even runs, the engine checks this list. If the wallet is on it,
that becomes a strong "this is fine" signal — not an unconditional override,
just very heavy evidence pointing at low risk.

**Why it matters:** `ARGUS-ENGINE-V2.md` documents an actual embarrassing
failure from v1: **Satoshi's genesis address scored 0.791 HIGH**, and so did
the Ethereum Foundation's wallet. That happens because the ML model has never
seen a wallet like that and has no way to say "I don't recognize this, but I
also have no reason to be suspicious of it." A known-entity check closes that
exact hole before it can happen live in front of anyone.

**How it fits the flow:**
```
POST /check-wallet or /wallets/{address}/risk
   → known_entity_lookup(address)     ← NEW, runs first
       found?  → strong low-risk evidence, skip/demote ML
       not found? → continue to sanctions → taint → ML as normal
```

---

## 4. 🔲 Explainability endpoint ("why was this flagged?")

**What it does:** A new endpoint, `GET /wallets/{address}/explanation`, that
turns the engine's decision into a structured, readable answer instead of one
paragraph of text:

```json
{
  "decision": "hold_for_review",
  "primary_reasons": [
    { "reason": "Taint trace reached a mixer boundary", "impact": "high" },
    { "reason": "ML triage score 0.81 >= 0.70",         "impact": "medium" }
  ],
  "basis_anchor_id": "...",
  "basis_trace_id": "..."
}
```

**Why it matters:** `app/engine/decision.py` already builds a human-readable
`reasoning` string for every single decision it makes — that work is already
done. Nobody can query it directly yet. This is mostly about exposing what
already exists in a shape a UI (or a judge) can actually read, instead of
digging through logs.

**How it fits the flow:** Reads an existing `Decision` row (already stored via
the ledger/decision tables) and reformats its `reasoning` + `basis_anchor_id` +
`basis_trace_id` fields into the structured response above. No new computation —
this is a formatting/API layer over data the engine already produces.

---

## 5. 🔲 Money-flow path summary

**What it does:** A hop-by-hop breakdown of where a victim's money actually
went, instead of just a final taint percentage:

```
Origin Risk          0.91
Layering Risk        0.78
Mixer Exposure       0.96
Cash-out Proximity   0.94
──────────────────────────
Path Risk            0.93

"Funds moved through 3 newly created wallets, entered a mixer at hop 4,
and are now 2 hops from an exchange deposit address."
```

**Why it matters:** This is the actual money-trail visual the engine's own
design doc (`ARGUS-ENGINE-V2.md`, USP 3 — Provenance Replay) promises. It's
also the single best thing to put in front of a judge: an animated trail is a
much stronger story than a risk number.

**How it fits the flow:** `app/engine/taint.py` already computes every hop —
address, taint fraction, terminal kind (mixer/bridge/VASP/etc.) — for every
trace. This item is a summary/narration layer built directly on the `nodes`
list already returned by `POST /trace`. No new tracing logic, just turning the
raw hop list into the readable breakdown above.

---

## Build order (why this order)

1 → 2 → 3 → 4 → 5. Items 1 and 2 are a pair (unknown vs. clean both need to
exist together or they contradict each other). Item 3 is independent and can
happen any time, but it's cheap and prevents a specific known embarrassment,
so it's next. Items 4 and 5 are both "expose data the engine already computed"
— pure win, no new risk, save for whenever there's time.

## What we deliberately did NOT pick from the blueprint

The blueprint's centerpiece — a weighted "Evidence Fusion Engine" that fuses
sanctions + graph + ML into one confidence score that can drive a `block` —
was explicitly rejected. It conflicts with the engine's actual load-bearing
rule: a `block` can only come from a Class-A anchor + a proven taint trace,
never from ML or a fused score alone. That rule is enforced three times over
in the code on purpose. None of the 5 items above touch it.
