"""
app/tests/test_nlp.py — Tests for Phase 6 Air-Gapped Local LLM (Llama-3.2-3B) & spaCy Fallback.
"""
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient

from app.nlp.llm_ner import extract_entities_from_narrative
from app.nlp.spacy_fallback import (
    classify_typology_regex,
    extract_amounts_regex,
    extract_dates_regex,
    extract_entities_spacy_fallback,
    extract_wallets_regex,
)


def test_spacy_fallback_regex_helpers():
    text = (
        "Victim transferred Rs 50,000 and 1.5 lakh to suspect's BTC wallet "
        "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh and ETH wallet 0x742d35Cc6634C0532925a3b844Bc454e4438f44e "
        "on 2026-08-15 promising crypto investment returns."
    )
    
    # 1. Wallets
    wallets = extract_wallets_regex(text)
    addrs = [w["address"] for w in wallets]
    assert "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh" in addrs
    assert "0x742d35Cc6634C0532925a3b844Bc454e4438f44e" in addrs

    # 2. Amounts
    amounts = extract_amounts_regex(text)
    amt_vals = [a["amount"] for a in amounts]
    assert 50000.0 in amt_vals
    assert 150000.0 in amt_vals

    # 3. Dates
    dates = extract_dates_regex(text)
    assert "2026-08-15" in dates

    # 4. Typology
    typology = classify_typology_regex(text)
    assert typology == "investment_fraud"


def test_spacy_fallback_full_pipeline():
    narrative = (
        "Complaint filed against fraudster Vikram Malhotra. Sent 75000 inr on 12-08-2026 "
        "to TRON wallet TJV2jG54iVp7F1X4BqmGk3hB3Z3K6N7v89 for part time telegram task scam."
    )
    res = extract_entities_spacy_fallback(narrative)
    assert res["extractor_used"] == "spacy_rule_fallback"
    assert res["fraud_typology"] == "job_task_scam"
    assert any(w["address"] == "TJV2jG54iVp7F1X4BqmGk3hB3Z3K6N7v89" for w in res["crypto_addresses"])
    assert any(a["amount"] == 75000.0 for a in res["amounts_mentioned"])


@pytest.mark.asyncio
async def test_llm_ner_live_or_fallback_graceful():
    sample_text = (
        "Victim lost INR 2,00,000 to suspect Alex Kumar. Sent funds to Bitcoin wallet "
        "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh on 2026-08-20."
    )
    result = await extract_entities_from_narrative(sample_text)
    assert "crypto_addresses" in result
    assert "amounts_mentioned" in result
    assert "fraud_typology" in result
    assert "latency_ms" in result
    assert result["latency_ms"] >= 0.0


@pytest.mark.asyncio
async def test_llm_ner_fallback_on_unreachable_server(monkeypatch):
    import app.nlp.llm_ner as ner_mod
    monkeypatch.setattr(ner_mod, "OLLAMA_LOCAL_URL", "http://127.0.0.1:59999")

    text = "Transferred 100000 rupees to 0x742d35Cc6634C0532925a3b844Bc454e4438f44e on 2026-08-01."
    res = await ner_mod.extract_entities_from_narrative(text)
    assert res["extractor_used"] == "spacy_rule_fallback"
    assert any(w["address"] == "0x742d35Cc6634C0532925a3b844Bc454e4438f44e" for w in res["crypto_addresses"])


@pytest.mark.asyncio
async def test_get_complaint_detail_endpoint_with_entities(client: AsyncClient, auth_headers: dict):
    # 1. Ingest a complaint
    comp_res = await client.post(
        "/api/v1/complaints",
        json={
            "ncrp_ref": "NCRP-2026-NLP-01",
            "source_platform": "ncrp",
            "narrative_text": "Victim reported ₹3.5L lost to suspect Rajesh Sharma via fake crypto scheme. Sent BTC to bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh on 2026-08-18.",
            "fraud_typology": "investment_fraud",
            "amount_lost": 350000.0,
            "filed_at": datetime.now(timezone.utc).isoformat(),
            "state": "Delhi",
            "district": "New Delhi",
        },
        headers=auth_headers,
    )
    assert comp_res.status_code == 201
    comp_id = comp_res.json()["id"]

    # 2. Query complaint detail
    detail_res = await client.get(f"/api/v1/complaints/{comp_id}", headers=auth_headers)
    assert detail_res.status_code == 200
    data = detail_res.json()
    assert data["id"] == comp_id
    assert "extracted_entities" in data
    entities = data["extracted_entities"]
    assert entities is not None
    assert "crypto_addresses" in entities
    assert any(w["address"] == "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh" for w in entities["crypto_addresses"])
