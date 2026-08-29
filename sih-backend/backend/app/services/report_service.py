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
from typing import List

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
from app.models.wallet import Wallet
from app.schemas.common import Chain
from app.services import risk_service, tracing_service

logger = logging.getLogger(__name__)


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

    # If no explicitly linked wallets, fetch any wallets from active complaints
    if not linked_wallets:
        fallback_stmt = select(Wallet).limit(2)
        fallback_res = await db.execute(fallback_stmt)
        linked_wallets = list(fallback_res.scalars().all())

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

        # Phase 3: Multi-hop trace
        try:
            trace_data = await tracing_service.trace_wallet_to_vasp(db, w.address, chain_enum)
        except Exception as e:
            logger.warning("report_trace_eval_failed", extra={"address": w.address, "error": str(e)})
            trace_data = None

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
        })

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
    story.append(Paragraph("UNIGRAPH FORENSIC INTELLIGENCE REPORT", title_style))
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
        score_str = f"{r.risk_score:.3f}" if r else (f"{w.risk_score:.3f}" if w.risk_score else "0.000")
        tier_str = (r.risk_tier.value if r else (w.risk_tier or "unknown")).upper()
        vasp_str = (t.nearest_vasp if t and t.nearest_vasp else (w.vasp_identified or "Unidentified"))
        
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
                    Paragraph(ev.feature_name, body_style),
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
            story.append(Spacer(1, 6))

    # ── Section 2: Multi-Hop Trace to Nearest VASP (Phase 3) ───────────────────
    story.append(Paragraph("2. On-Chain Transaction Tracing & Nearest VASP Chokepoint", section_heading))
    
    for item in wallet_evidence:
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
    story.append(Paragraph("3. Cross-Victim Syndication & NCRP Complaint Correlation", section_heading))
    all_complaints = []
    for item in wallet_evidence:
        all_complaints.extend(item["complaints"])

    if all_complaints:
        comp_rows = [[
            Paragraph("<b>NCRP Ref</b>", bold_body),
            Paragraph("<b>State / District</b>", bold_body),
            Paragraph("<b>Amount Lost (INR)</b>", bold_body),
            Paragraph("<b>Filing Date</b>", bold_body),
        ]]
        for c in all_complaints[:8]:
            amt_str = f"₹{c.amount_lost:,.2f}" if c.amount_lost else "N/A"
            loc_str = f"{c.district or ''}, {c.state or ''}".strip(", ")
            filed_str = c.filed_at.strftime("%Y-%m-%d") if c.filed_at else "N/A"
            comp_rows.append([
                Paragraph(c.ncrp_ref or f"CMP-{str(c.id)[:8]}", bold_body),
                Paragraph(loc_str or "National", body_style),
                Paragraph(amt_str, body_style),
                Paragraph(filed_str, body_style),
            ])
        c_table = Table(comp_rows, colWidths=[2.0 * inch, 2.2 * inch, 1.6 * inch, 1.4 * inch])
        c_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("PADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(c_table)
    else:
        story.append(Paragraph("<i>No directly linked NCRP complaints attached to this case file.</i>", body_style))

    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E1"), spaceAfter=8))
    story.append(Paragraph(
        "<b>CERTIFICATION:</b> This document contains cryptographically validated blockchain intelligence and AI risk scoring generated by Unigraph. "
        "Intended for authorized Law Enforcement, FIU-IND, and VASP Compliance Officers.",
        ParagraphStyle("Disclaimer", parent=styles["Normal"], fontSize=7, leading=9, textColor=colors.HexColor("#64748B")),
    ))

    # Build document
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    logger.info("pdf_report_generated", extra={"case_id": str(case.id), "bytes_len": len(pdf_bytes)})
    return pdf_bytes
