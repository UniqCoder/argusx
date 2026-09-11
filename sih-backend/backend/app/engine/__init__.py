"""
app/engine/ — The ARGUS v2 provenance engine.

Implements Layers 0, 1 and 5 of ARGUS-ENGINE-V2.md as additive modules:
  anchors.py    Layer 0 — ground-truth attestations
  taint.py      Layer 1 — taint propagation (haircut/poison/fifo) over live explorers
  registries.py known mixer / bridge contract lookups (Layer 1 terminals)
  decision.py   Layer 5 — the three-tier decision engine + the block-requires-anchor guard
  ledger.py     Layer 5 — the tamper-evident hash-chained evidence ledger

Nothing here replaces or modifies the existing v1 services (risk_service,
tracing_service, correlation_service, registry_service) — those continue to
back the existing routers/frontend untouched. This package is consumed only
by the new app/api/v1/routers/engine.py router.
"""
