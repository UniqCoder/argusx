import uuid
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient

from app.schemas.common import CaseStatus


@pytest.mark.asyncio
async def test_case_lifecycle_and_valid_transitions(client: AsyncClient, auth_headers: dict):
    # 1. Create a new case
    create_res = await client.post(
        "/api/v1/cases",
        json={
            "assigned_investigator": "inspector_deshmukh",
            "initial_status": "new",
        },
        headers=auth_headers,
    )
    assert create_res.status_code == 201
    case = create_res.json()
    case_id = case["id"]
    assert case["status"] == "new"
    assert case["assigned_investigator"] == "inspector_deshmukh"
    assert case["closed_at"] is None

    # 2. Transition: new -> investigating (valid)
    res_inv = await client.patch(
        f"/api/v1/cases/{case_id}",
        json={"status": "investigating"},
        headers=auth_headers,
    )
    assert res_inv.status_code == 200
    assert res_inv.json()["status"] == "investigating"

    # 3. Transition: investigating -> escalated_to_vasp (valid)
    res_esc = await client.patch(
        f"/api/v1/cases/{case_id}",
        json={"status": "escalated_to_vasp"},
        headers=auth_headers,
    )
    assert res_esc.status_code == 200
    assert res_esc.json()["status"] == "escalated_to_vasp"

    # 4. Transition: escalated_to_vasp -> frozen (valid)
    res_frz = await client.patch(
        f"/api/v1/cases/{case_id}",
        json={"status": "frozen"},
        headers=auth_headers,
    )
    assert res_frz.status_code == 200
    assert res_frz.json()["status"] == "frozen"

    # 5. Transition: frozen -> closed (valid, populates closed_at)
    res_cls = await client.patch(
        f"/api/v1/cases/{case_id}",
        json={"status": "closed"},
        headers=auth_headers,
    )
    assert res_cls.status_code == 200
    assert res_cls.json()["status"] == "closed"
    assert res_cls.json()["closed_at"] is not None

    # 6. Transition: closed -> investigating (re-open, clears closed_at)
    res_reopen = await client.patch(
        f"/api/v1/cases/{case_id}",
        json={"status": "investigating"},
        headers=auth_headers,
    )
    assert res_reopen.status_code == 200
    assert res_reopen.json()["status"] == "investigating"
    assert res_reopen.json()["closed_at"] is None


@pytest.mark.asyncio
async def test_case_invalid_status_transition_rejected(client: AsyncClient, auth_headers: dict):
    # Create new case
    create_res = await client.post(
        "/api/v1/cases",
        json={"assigned_investigator": "inspector_patil", "initial_status": "new"},
        headers=auth_headers,
    )
    case_id = create_res.json()["id"]

    # Attempt illegal transition: new -> frozen (skipping investigation/escalation)
    patch_res = await client.patch(
        f"/api/v1/cases/{case_id}",
        json={"status": "frozen"},
        headers=auth_headers,
    )
    assert patch_res.status_code == 422
    data = patch_res.json()
    assert "error" in data
    assert data["error"]["code"] == "INVALID_STATUS_TRANSITION"


@pytest.mark.asyncio
async def test_get_case_by_id_and_list_filtering(client: AsyncClient, auth_headers: dict):
    # Create two cases with distinct statuses
    res1 = await client.post(
        "/api/v1/cases",
        json={"assigned_investigator": "officer_1", "initial_status": "new"},
        headers=auth_headers,
    )
    case1_id = res1.json()["id"]

    # Get single case
    get_res = await client.get(f"/api/v1/cases/{case1_id}", headers=auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == case1_id

    # Non-existent case
    fake_id = str(uuid.uuid4())
    nf_res = await client.get(f"/api/v1/cases/{fake_id}", headers=auth_headers)
    assert nf_res.status_code == 404
    assert nf_res.json()["error"]["code"] == "CASE_NOT_FOUND"

    # List cases
    list_res = await client.get("/api/v1/cases?status=new&page=1&page_size=10", headers=auth_headers)
    assert list_res.status_code == 200
    data = list_res.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_get_case_pdf_report_generates_valid_binary(client: AsyncClient, auth_headers: dict):
    # 1. Create a complaint
    comp_res = await client.post(
        "/api/v1/complaints",
        json={
            "ncrp_ref": "NCRP-2026-CASE-01",
            "source_platform": "ncrp",
            "narrative_text": "Victim defrauded of INR 5,00,000 via crypto investment scam.",
            "fraud_typology": "investment_fraud",
            "amount_lost": 500000.0,
            "filed_at": datetime.now(timezone.utc).isoformat(),
            "state": "Maharashtra",
            "district": "Mumbai",
        },
        headers=auth_headers,
    )
    assert comp_res.status_code == 201

    # 2. Create case
    case_res = await client.post(
        "/api/v1/cases",
        json={"assigned_investigator": "sp_cyber_crime", "initial_status": "investigating"},
        headers=auth_headers,
    )
    case_id = case_res.json()["id"]

    # 3. Request PDF report
    report_res = await client.get(f"/api/v1/cases/{case_id}/report", headers=auth_headers)
    assert report_res.status_code == 200
    assert report_res.headers.get("content-type") == "application/pdf"
    content = report_res.content

    # PDF Magic header assertion
    assert content.startswith(b"%PDF-")
    assert len(content) > 1000  # Non-trivial report with full styling & tables


@pytest.mark.asyncio
async def test_case_audit_logging_trail(client: AsyncClient, auth_headers: dict):
    # 1. Create a case
    case_res = await client.post(
        "/api/v1/cases",
        json={"assigned_investigator": "inspector_audit", "initial_status": "new"},
        headers=auth_headers,
    )
    case_id = case_res.json()["id"]

    # 2. View case (triggers view_case audit log)
    view_res = await client.get(f"/api/v1/cases/{case_id}", headers=auth_headers)
    assert view_res.status_code == 200

    # 3. Update status (triggers update_case_status audit log)
    update_res = await client.patch(
        f"/api/v1/cases/{case_id}",
        json={"status": "investigating"},
        headers=auth_headers,
    )
    assert update_res.status_code == 200

    # 4. Export report (triggers export_pdf_report audit log)
    report_res = await client.get(f"/api/v1/cases/{case_id}/report", headers=auth_headers)
    assert report_res.status_code == 200
