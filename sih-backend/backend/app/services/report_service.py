"""
app/services/report_service.py — Forensic PDF Report Generator for Law Enforcement / I4C.

Generates official multi-page PDF reports containing:
  - Case metadata & Executive Summary
  - Phase 4 ML Risk Scores & SHAP Explainability Evidence
  - Phase 3 Multi-Hop On-Chain Traces to Nearest VASP
  - Phase 1 Cross-Victim NCRP Complaints & Correlation Evidence
"""
import io
import uuid
from datetime import datetime, timezone
import logging
from typing import List, Optional

from fastapi import HTTPException, status
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case, CaseWallet
from app.models.complaint import Complaint, ComplaintWallet
from app.models.engine import Anchor, EvidenceLedgerEntry, TaintNode, Trace
from app.models.wallet import Wallet
from app.schemas.common import Chain
from app.services import risk_service, tracing_service

logger = logging.getLogger(__name__)


async def _latest_trace_for_wallet(
    db: AsyncSession, case_id: uuid.UUID, address: str, chain: str
) -> tuple[Optional[Anchor], Optional[Trace], list[TaintNode]]:
    """The most recent COMPLETED taint-propagation run this case has for this
    wallet, with its full node list — the same real multi-hop engine result
    the Investigation graph renders, not the flat single-hop v1 lookup the
    report used to show instead. Returns (None, None, []) if this wallet was
    never actually traced through the v2 engine within this case (e.g. it
    was only linked directly, never searched)."""
    anchor_stmt = (
        select(Anchor)
        .where(Anchor.case_id == case_id, Anchor.address == address, Anchor.chain == chain)
        .order_by(Anchor.asserted_at.desc())
    )
    anchor = (await db.execute(anchor_stmt)).scalars().first()
    if anchor is None:
        return None, None, []

    trace_stmt = (
        select(Trace)
        .where(Trace.anchor_id == anchor.id, Trace.completed_at.isnot(None))
        .order_by(Trace.completed_at.desc())
    )
    trace = (await db.execute(trace_stmt)).scalars().first()
    if trace is None:
        return anchor, None, []

    node_stmt = (
        select(TaintNode)
        .where(TaintNode.trace_id == trace.id)
        .order_by(TaintNode.hop.asc(), TaintNode.address.asc())
    )
    nodes = list((await db.execute(node_stmt)).scalars().all())
    return anchor, trace, nodes


async def generate_case_pdf_report(db: AsyncSession, case_id: uuid.UUID) -> bytes:
    """
    Generate an official forensic PDF report for a case by gathering live evidence
    from PostgreSQL, Neo4j, live blockchain explorers, and ML risk models.
    """
    # 1. Fetch Case record
    stmt = select(Case).where(Case.id == case_id)
    res = await db.execute(stmt)
    case = res.scalar_one_or_none()

    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "CASE_NOT_FOUND",
                    "message": f"Case with ID '{case_id}' was not found.",
                    "details": {"case_id": str(case_id)},
                }
            },
        )

    # 2. Fetch linked Wallets
    wallet_stmt = (
        select(Wallet)
        .join(CaseWallet, CaseWallet.wallet_id == Wallet.id)
        .where(CaseWallet.case_id == case.id)
    )
    wallet_res = await db.execute(wallet_stmt)
    linked_wallets = list(wallet_res.scalars().all())

    # 3. Gather live Phase 1, Phase 3, Phase 4 evidence for each wallet
    wallet_evidence = []
    for w in linked_wallets:
        chain_enum = Chain(w.chain.upper()) if w.chain else Chain.BTC
        
        # Phase 4: Risk score & SHAP evidence
        try:
            risk_data = await risk_service.evaluate_wallet_risk(db, w.address, chain_enum)
        except Exception as e:
            logger.warning("report_risk_eval_failed", extra={"address": w.address, "error": str(e)})
            risk_data = None

        # Phase 3 (legacy): flat single-hop lookup, kept only as a fallback
        # source for "nearest VASP" when this wallet was never run through
        # the real v2 engine within this case.
        try:
            trace_data = await tracing_service.trace_wallet_to_vasp(db, w.address, chain_enum)
        except Exception as e:
            logger.warning("report_trace_eval_failed", extra={"address": w.address, "error": str(e)})
            trace_data = None

        # Phase 3 (v2, real): the actual multi-hop taint-propagation run this
        # case has for this wallet — real nodes, roles, typologies, path
        # risk, termination provenance. This is what the Investigation graph
        # and Evidence Trail show; the report now describes the same run
        # instead of a separately-computed, much thinner one.
        anchor, engine_trace, engine_nodes = await _latest_trace_for_wallet(
            db, case.id, w.address, w.chain or chain_enum.value
        )

        # Phase 1: Correlated complaints
        comp_stmt = (
            select(Complaint)
            .join(ComplaintWallet, ComplaintWallet.complaint_id == Complaint.id)
            .where(ComplaintWallet.wallet_id == w.id)
        )
        comp_res = await db.execute(comp_stmt)
        complaints = list(comp_res.scalars().all())

        wallet_evidence.append({
            "wallet": w,
            "risk": risk_data,
            "trace": trace_data,
            "complaints": complaints,
            "anchor": anchor,
            "engine_trace": engine_trace,
            "engine_nodes": engine_nodes,
        })

    # Case-wide evidence ledger — the tamper-evident hash chain backing
    # every anchor/trace/decision event in this case (app/engine/ledger.py).
    ledger_stmt = (
        select(EvidenceLedgerEntry)
        .where(EvidenceLedgerEntry.case_id == case.id)
        .order_by(EvidenceLedgerEntry.seq.asc())
    )
    ledger_entries = list((await db.execute(ledger_stmt)).scalars().all())

    # 4. Build PDF document via ReportLab
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#475569"),
        spaceAfter=12,
    )
    section_heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#1E293B"),
        spaceBefore=14,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "DocBody",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#334155"),
    )
    bold_body = ParagraphStyle(
        "BoldBody",
        parent=body_style,
        fontName="Helvetica-Bold",
    )
    badge_critical = ParagraphStyle(
        "BadgeCritical",
        parent=body_style,
        textColor=colors.HexColor("#DC2626"),
        fontName="Helvetica-Bold",
    )

    story = []

    # ── Header Banner ──────────────────────────────────────────────────────────
    story.append(Paragraph("ARGUS FORENSIC INTELLIGENCE REPORT", title_style))
    story.append(Paragraph("INDIAN CYBER CRIME COORDINATION CENTRE (I4C) — MHA / LEA DISPATCH", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284C7"), spaceAfter=10))

    # ── Case Summary Box ───────────────────────────────────────────────────────
    opened_str = case.opened_at.strftime("%Y-%m-%d %H:%M:%S UTC") if case.opened_at else "N/A"
    closed_str = case.closed_at.strftime("%Y-%m-%d %H:%M:%S UTC") if case.closed_at else "Active / Under Investigation"
    investigator = case.assigned_investigator or "Unassigned (I4C Central Desk)"

    summary_data = [
        [
            Paragraph("<b>Case Reference:</b>", bold_body),
            Paragraph(f"CASE-{str(case.id)[:8].upper()}", body_style),
            Paragraph("<b>Status:</b>", bold_body),
            Paragraph(case.status.upper(), badge_critical if case.status in ("frozen", "escalated_to_vasp") else bold_body),
        ],
        [
            Paragraph("<b>Investigator:</b>", bold_body),
            Paragraph(investigator, body_style),
            Paragraph("<b>Date Opened:</b>", bold_body),
            Paragraph(opened_str, body_style),
        ],
        [
            Paragraph("<b>Linked Wallets:</b>", bold_body),
            Paragraph(f"{len(linked_wallets)} Suspect Addresses", body_style),
            Paragraph("<b>Report Generated:</b>", bold_body),
            Paragraph(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"), body_style),
        ],
    ]
    summary_table = Table(summary_data, colWidths=[1.3 * inch, 2.2 * inch, 1.3 * inch, 2.4 * inch])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10))

    # ── Executive Statistics Strip ──────────────────────────────────────────
    # Deduplicated by complaint id — a complaint can name more than one of
    # this case's linked wallets and must only count once toward the
    # victim/loss totals, or a multi-wallet case would overstate both.
    _seen_complaint_ids: set = set()
    _unique_complaints = []
    for item in wallet_evidence:
        for c in item["complaints"]:
            if c.id not in _seen_complaint_ids:
                _seen_complaint_ids.add(c.id)
                _unique_complaints.append(c)
    _total_loss = sum(float(c.amount_lost) for c in _unique_complaints if c.amount_lost)
    _critical_wallets = sum(
        1 for item in wallet_evidence
        if item["risk"] and item["risk"].risk_tier and item["risk"].risk_tier.value in ("critical", "high")
    )
    _traced_wallets = sum(1 for item in wallet_evidence if item["engine_trace"] is not None)
    _total_nodes_mapped = sum(
        (item["engine_trace"].node_count or 0) for item in wallet_evidence if item["engine_trace"]
    )

    stats_data = [[
        Paragraph("<b>Linked Wallets</b>", bold_body), Paragraph(str(len(linked_wallets)), body_style),
        Paragraph("<b>High/Critical Risk</b>", bold_body), Paragraph(str(_critical_wallets), body_style),
        Paragraph("<b>Wallets Traced</b>", bold_body), Paragraph(str(_traced_wallets), body_style),
    ], [
        Paragraph("<b>Unique Complaints</b>", bold_body), Paragraph(str(len(_unique_complaints)), body_style),
        Paragraph("<b>Total Reported Loss</b>", bold_body), Paragraph(f"INR {_total_loss:,.2f}", body_style),
        Paragraph("<b>Addresses Mapped</b>", bold_body), Paragraph(str(_total_nodes_mapped), body_style),
    ]]
    stats_strip = Table(stats_data, colWidths=[1.1 * inch, 0.8 * inch, 1.2 * inch, 0.7 * inch, 1.1 * inch, 0.7 * inch])
    stats_strip.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EFF6FF")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#BFDBFE")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DBEAFE")),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(stats_strip)
    story.append(Spacer(1, 10))

    # ── Section 1: Suspect Wallets & ML Risk Scoring (Phase 4) ─────────────────
    story.append(Paragraph("1. Suspect Wallets & AI Risk Engine Evidence", section_heading))
    
    wallet_table_data = [
        [
            Paragraph("<b>Wallet Address</b>", bold_body),
            Paragraph("<b>Chain</b>", bold_body),
            Paragraph("<b>Risk Score</b>", bold_body),
            Paragraph("<b>Tier</b>", bold_body),
            Paragraph("<b>Identified VASP</b>", bold_body),
        ]
    ]

    for item in wallet_evidence:
        w = item["wallet"]
        r = item["risk"]
        t = item["trace"]
        # `r` is a RiskResponse whenever risk_service ran at all — including
        # its own honest degraded case (risk_score=None, tier=unknown) when
        # no scoring model is available. `f"{None:.3f}"` raises, which used
        # to crash report generation outright for every wallet whenever the
        # ML artifact was missing, rather than showing the same "unscored"
        # state the rest of the app shows. Never render a fabricated 0.000
        # for a wallet that was never actually scored.
        fresh_score = r.risk_score if r else None
        is_stale_fallback = fresh_score is None and w.risk_score is not None
        score_value = fresh_score if fresh_score is not None else w.risk_score
        # A stale DB value (from a previous evaluation) must never render
        # identically to a fresh one — it used to, silently presenting an
        # old score as if it were current the moment the live pipeline
        # degraded (explorer outage, missing artifacts) mid-report.
        score_str = (
            f"{score_value:.4f} (last known — live scoring unavailable)"
            if is_stale_fallback
            else f"{score_value:.4f}"
            if score_value is not None
            else "N/A"
        )
        tier_str = (r.risk_tier.value if r else (w.risk_tier or "unknown")).upper()
        # Prefer the real v2 engine's own VASP terminal (a node the taint
        # BFS actually reached and classified) over the legacy flat lookup.
        engine_nodes = item["engine_nodes"]
        engine_vasp = next(
            (n.entity_name for n in engine_nodes if n.terminal_kind == "VASP" and n.entity_name), None
        )
        vasp_str = engine_vasp or (t.nearest_vasp if t and t.nearest_vasp else (w.vasp_identified or "Unidentified"))

        wallet_table_data.append([
            Paragraph(f"<font size=7>{w.address}</font>", body_style),
            Paragraph(w.chain or "BTC", body_style),
            Paragraph(score_str, bold_body),
            Paragraph(tier_str, badge_critical if tier_str in ("CRITICAL", "HIGH") else body_style),
            Paragraph(vasp_str, bold_body),
        ])

    w_table = Table(wallet_table_data, colWidths=[2.8 * inch, 0.7 * inch, 0.9 * inch, 1.0 * inch, 1.8 * inch])
    w_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#94A3B8")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(w_table)
    story.append(Spacer(1, 8))

    # SHAP Evidence Subsection
    for item in wallet_evidence:
        r = item["risk"]
        if r and r.evidence:
            story.append(Paragraph(f"<b>Key Feature Risk Drivers (SHAP) for {item['wallet'].address[:12]}...:</b>", body_style))
            evidence_data = [[
                Paragraph("<b>Feature Indicator</b>", bold_body),
                Paragraph("<b>Impact Magnitude</b>", bold_body),
                Paragraph("<b>Risk Direction</b>", bold_body),
            ]]
            for ev in r.evidence:
                dir_color = "#DC2626" if ev.direction.value == "increases_risk" else "#16A34A"
                evidence_data.append([
                    Paragraph(ev.feature_name + (f"<br/><font size=6 color='#64748B'>{ev.detail}</font>" if ev.detail else ""), body_style),
                    Paragraph(f"{ev.contribution:.4f}", body_style),
                    Paragraph(f"<font color='{dir_color}'>{ev.direction.value.replace('_', ' ').upper()}</font>", bold_body),
                ])
            ev_table = Table(evidence_data, colWidths=[3.2 * inch, 1.8 * inch, 2.2 * inch])
            ev_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("PADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(ev_table)
            # Full scoring provenance — lets a reader confirm this exact
            # figure came from a specific, reproducible computation (see
            # risk_service.py's snapshot_id / model_version), not just trust
            # a number on a page.
            story.append(Paragraph(
                f"<font size=6 color='#94A3B8'>Model: {r.model_version or 'n/a'} &nbsp;·&nbsp; "
                f"Feature schema: {r.feature_schema_version or 'n/a'} &nbsp;·&nbsp; "
                f"Snapshot: {r.snapshot_id or 'n/a'} &nbsp;·&nbsp; "
                f"Computed: {r.calculated_at or 'n/a'} &nbsp;·&nbsp; Source: {r.risk_source}</font>",
                body_style,
            ))
            story.append(Spacer(1, 6))

    # ── Section 1b: Multi-Hop Taint Trace Analysis (real v2 engine output) ────
    story.append(Paragraph("1b. Multi-Hop Taint Propagation — Full Trace Analysis", section_heading))
    any_engine_trace = False
    for item in wallet_evidence:
        w = item["wallet"]
        anchor = item["anchor"]
        et = item["engine_trace"]
        nodes = item["engine_nodes"]
        if et is None:
            continue
        any_engine_trace = True

        term_reason = (et.termination_reason or "unknown").replace("_", " ").title()
        story.append(Paragraph(
            f"<b>Trace for {w.address[:14]}... (anchor asserted {anchor.asserted_at.strftime('%Y-%m-%d %H:%M UTC') if anchor and anchor.asserted_at else 'n/a'} "
            f"by {anchor.asserted_by if anchor else 'n/a'}, class {anchor.attestation_class if anchor else '?'})</b>",
            body_style,
        ))

        stat_rows = [
            [
                Paragraph("<b>Method</b>", bold_body), Paragraph(et.method or "haircut", body_style),
                Paragraph("<b>Depth</b>", bold_body), Paragraph(f"{et.depth_reached} reached / {et.max_hops} requested", body_style),
            ],
            [
                Paragraph("<b>Nodes Mapped</b>", bold_body), Paragraph(str(et.node_count or len(nodes)), body_style),
                Paragraph("<b>Termination</b>", bold_body), Paragraph(term_reason, body_style),
            ],
            [
                Paragraph("<b>Seed Value</b>", bold_body),
                Paragraph(f"{et.seed_value:.6f} {et.asset or ''} ({et.seed_basis or 'n/a'})" if et.seed_value is not None else "N/A", body_style),
                Paragraph("<b>Data Source</b>", bold_body),
                Paragraph((et.data_source or "unknown") + (f" ({et.scenario_key})" if et.scenario_key else ""), body_style),
            ],
            [
                Paragraph("<b>Pruned (dust)</b>", bold_body),
                Paragraph(f"{et.pruned_branch_count or 0} branches, {et.pruned_branch_value or 0:.6f} {et.asset or ''}", body_style),
                Paragraph("<b>Other-Asset Outflow</b>", bold_body),
                Paragraph(f"{et.other_asset_branch_count or 0} branches not traced", body_style),
            ],
            [
                Paragraph("<b>Reproducible Hash</b>", bold_body),
                Paragraph(f"<font size=6>{et.reproducible_hash}</font>", body_style),
                Paragraph("<b>Completed</b>", bold_body),
                Paragraph(et.completed_at.strftime("%Y-%m-%d %H:%M UTC") if et.completed_at else "N/A", body_style),
            ],
        ]
        stat_table = Table(stat_rows, colWidths=[1.1 * inch, 2.4 * inch, 1.1 * inch, 2.4 * inch])
        stat_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(stat_table)
        story.append(Spacer(1, 4))

        # Path-risk breakdown (Origin / Layering / Mixer Exposure / Cash-out
        # Proximity) — explanation only, never the basis for a block
        # decision (app/engine/decision.py never reads this column).
        pr = et.path_risk or {}
        if pr:
            story.append(Paragraph(
                f"<b>Path Risk Summary:</b> overall {pr.get('overall', 'n/a')} ({str(pr.get('tier', 'n/a')).upper()}) — "
                "explanatory only, not a standalone basis for any block/freeze decision.",
                body_style,
            ))
            pr_rows = [[
                Paragraph("<b>Dimension</b>", bold_body),
                Paragraph("<b>Score</b>", bold_body),
                Paragraph("<b>Flags</b>", bold_body),
            ]]
            for dim_key, dim_label in [
                ("origin_risk", "Origin"), ("layering_risk", "Layering"),
                ("mixer_exposure", "Mixer Exposure"), ("cashout_proximity", "Cash-out Proximity"),
            ]:
                dim = pr.get(dim_key) or {}
                pr_rows.append([
                    Paragraph(dim_label, body_style),
                    Paragraph(str(dim.get("score", "n/a")), body_style),
                    Paragraph(", ".join(dim.get("flags", [])) or "—", body_style),
                ])
            pr_table = Table(pr_rows, colWidths=[1.4 * inch, 0.9 * inch, 4.7 * inch])
            pr_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("PADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(pr_table)
            story.append(Spacer(1, 4))

        # Typologies detected
        typologies = et.typologies or []
        if typologies:
            story.append(Paragraph("<b>Typologies Detected:</b>", body_style))
            for ty in typologies:
                story.append(Paragraph(
                    f"&nbsp;&nbsp;• <b>{ty.get('label', ty.get('code', 'Unknown'))}:</b> {ty.get('narrative', '')}",
                    body_style,
                ))
            story.append(Spacer(1, 4))

        # Full node table — every address the trace reached, its role, and
        # where the money is. Capped for page length; the cap is disclosed,
        # never a silent truncation.
        NODE_ROWS_CAP = 20
        if nodes:
            story.append(Paragraph(
                f"<b>Traced Addresses</b> ({len(nodes)} total"
                + (f", showing first {NODE_ROWS_CAP}" if len(nodes) > NODE_ROWS_CAP else "")
                + "):",
                body_style,
            ))
            node_rows = [[
                Paragraph("<b>Hop</b>", bold_body),
                Paragraph("<b>Address</b>", bold_body),
                Paragraph("<b>Role</b>", bold_body),
                Paragraph("<b>Terminal</b>", bold_body),
                Paragraph("<b>Value In / Out</b>", bold_body),
                Paragraph("<b>Entity</b>", bold_body),
            ]]
            for n in nodes[:NODE_ROWS_CAP]:
                node_rows.append([
                    Paragraph(str(n.hop), body_style),
                    Paragraph(f"<font size=6>{n.address[:16]}...</font>", body_style),
                    Paragraph((n.role or "—").replace("_", " ").title(), body_style),
                    Paragraph((n.terminal_kind or "—").replace("_", " ").title(), body_style),
                    Paragraph(f"{n.value_in or 0:.4f} / {n.value_out or 0:.4f}", body_style),
                    Paragraph(n.entity_name or "—", body_style),
                ])
            node_table = Table(node_rows, colWidths=[0.5 * inch, 1.7 * inch, 1.1 * inch, 1.1 * inch, 1.2 * inch, 1.4 * inch])
            node_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("PADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(node_table)
        story.append(Spacer(1, 8))

    if not any_engine_trace:
        story.append(Paragraph(
            "<i>No wallet in this case has been run through the multi-hop taint-propagation engine yet "
            "(Trace Wallet was never used within this case's context). Section 1 above still reflects live "
            "ML risk scoring for each linked wallet independently.</i>",
            body_style,
        ))
        story.append(Spacer(1, 8))

    # ── Section 2: Direct Transaction Snapshot (fallback, v1) ──────────────────
    # Section 1b above already gives the real multi-hop trace for any wallet
    # that has one; this stays only as a fallback single-hop view for a
    # wallet linked to the case that was never actually run through the v2
    # engine, so a case is never silently missing ALL transaction evidence.
    fallback_items = [item for item in wallet_evidence if item["engine_trace"] is None]
    if fallback_items:
        story.append(Paragraph("2. Direct Transaction Snapshot (Single-Hop, Fallback)", section_heading))
        story.append(Paragraph(
            "<i>The wallets below were not run through the multi-hop taint-propagation engine within this "
            "case (see Section 1b) — this is their direct transaction history only, as a fallback.</i>",
            body_style,
        ))
    for item in fallback_items:
        t = item["trace"]
        if t and t.path:
            story.append(Paragraph(f"<b>Trace Route for {item['wallet'].address[:12]}... (Nearest VASP: {t.nearest_vasp or 'Unknown'}, Hops: {t.hops_count})</b>", body_style))
            trace_rows = [[
                Paragraph("<b>Tx Hash</b>", bold_body),
                Paragraph("<b>From</b>", bold_body),
                Paragraph("<b>To</b>", bold_body),
                Paragraph("<b>Amount</b>", bold_body),
            ]]
            for hop in t.path[:5]:
                trace_rows.append([
                    Paragraph(f"<font size=6>{hop.tx_hash[:16]}...</font>", body_style),
                    Paragraph(f"<font size=6>{hop.from_address[:12]}...</font>", body_style),
                    Paragraph(f"<font size=6>{hop.to_address[:12]}...</font>", body_style),
                    Paragraph(f"{hop.amount:.4f} {hop.chain.value}", body_style),
                ])
            t_table = Table(trace_rows, colWidths=[2.2 * inch, 1.8 * inch, 1.8 * inch, 1.4 * inch])
            t_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("PADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(t_table)
            story.append(Spacer(1, 6))

    # ── Section 3: Linked Victim NCRP Complaints (Phase 1) ─────────────────────
    story.append(Spacer(1, 4))
    story.append(Paragraph("3. Cross-Victim Syndication & NCRP Complaint Correlation", section_heading))
    all_complaints = []
    for item in wallet_evidence:
        all_complaints.extend(item["complaints"])

    if all_complaints:
        total_lost = sum(float(c.amount_lost) for c in all_complaints if c.amount_lost)
        story.append(Paragraph(
            f"<b>{len(all_complaints)} complaint(s)</b> linked to this case's wallets, "
            f"<b>INR {total_lost:,.2f}</b> total reported loss across them.",
            body_style,
        ))
        COMPLAINT_ROWS_CAP = 15
        comp_rows = [[
            Paragraph("<b>NCRP Ref</b>", bold_body),
            Paragraph("<b>Platform</b>", bold_body),
            Paragraph("<b>Typology</b>", bold_body),
            Paragraph("<b>State / District</b>", bold_body),
            Paragraph("<b>Amount Lost (INR)</b>", bold_body),
            Paragraph("<b>Filing Date</b>", bold_body),
        ]]
        for c in all_complaints[:COMPLAINT_ROWS_CAP]:
            amt_str = f"INR {c.amount_lost:,.2f}" if c.amount_lost else "N/A"
            loc_str = f"{c.district or ''}, {c.state or ''}".strip(", ")
            filed_str = c.filed_at.strftime("%Y-%m-%d") if c.filed_at else "N/A"
            comp_rows.append([
                Paragraph(c.ncrp_ref or f"CMP-{str(c.id)[:8]}", bold_body),
                Paragraph((c.source_platform or "—").upper(), body_style),
                Paragraph(c.fraud_typology or "Unclassified", body_style),
                Paragraph(loc_str or "National", body_style),
                Paragraph(amt_str, body_style),
                Paragraph(filed_str, body_style),
            ])
        c_table = Table(comp_rows, colWidths=[1.4 * inch, 0.8 * inch, 1.3 * inch, 1.7 * inch, 1.2 * inch, 0.9 * inch])
        c_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("PADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(c_table)
        if len(all_complaints) > COMPLAINT_ROWS_CAP:
            story.append(Paragraph(
                f"<i>+{len(all_complaints) - COMPLAINT_ROWS_CAP} additional complaint(s) not shown — see the case's Evidence Trail for the full list.</i>",
                body_style,
            ))
    else:
        story.append(Paragraph("<i>No directly linked NCRP complaints attached to this case file.</i>", body_style))

    # ── Section 4: Evidence Ledger (tamper-evident audit trail) ────────────────
    story.append(Spacer(1, 10))
    story.append(Paragraph("4. Evidence Ledger — Tamper-Evident Audit Trail", section_heading))
    if ledger_entries:
        story.append(Paragraph(
            f"<b>{len(ledger_entries)} event(s)</b> recorded, hash-chained (each entry's hash covers the previous "
            "entry's hash, so any edit or reordering after the fact is detectable).",
            body_style,
        ))
        LEDGER_ROWS_CAP = 25
        ledger_rows = [[
            Paragraph("<b>Seq</b>", bold_body),
            Paragraph("<b>Event</b>", bold_body),
            Paragraph("<b>Actor</b>", bold_body),
            Paragraph("<b>Occurred</b>", bold_body),
            Paragraph("<b>Entry Hash</b>", bold_body),
        ]]
        for e in ledger_entries[:LEDGER_ROWS_CAP]:
            ledger_rows.append([
                Paragraph(str(e.seq), body_style),
                Paragraph(e.event_type.replace("_", " ").title(), body_style),
                Paragraph(e.actor, body_style),
                Paragraph(e.occurred_at.strftime("%Y-%m-%d %H:%M UTC") if e.occurred_at else "N/A", body_style),
                Paragraph(f"<font size=6>{e.entry_hash[:20]}...</font>", body_style),
            ])
        ledger_table = Table(ledger_rows, colWidths=[0.5 * inch, 1.5 * inch, 1.7 * inch, 1.5 * inch, 1.8 * inch])
        ledger_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("PADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(ledger_table)
        if len(ledger_entries) > LEDGER_ROWS_CAP:
            story.append(Paragraph(
                f"<i>+{len(ledger_entries) - LEDGER_ROWS_CAP} additional event(s) not shown — see the case's Evidence Trail for the full chain.</i>",
                body_style,
            ))
    else:
        story.append(Paragraph("<i>No evidence ledger events recorded for this case yet.</i>", body_style))

    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E1"), spaceAfter=8))
    story.append(Paragraph(
        "<b>CERTIFICATION:</b> This document contains cryptographically validated blockchain intelligence and AI risk scoring generated by Argus. "
        "Intended for authorized Law Enforcement, FIU-IND, and VASP Compliance Officers.",
        ParagraphStyle("Disclaimer", parent=styles["Normal"], fontSize=7, leading=9, textColor=colors.HexColor("#64748B")),
    ))

    # Build document
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    logger.info("pdf_report_generated", extra={"case_id": str(case.id), "bytes_len": len(pdf_bytes)})
    return pdf_bytes
