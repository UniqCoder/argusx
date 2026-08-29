"""
app/nlp/llm_ner.py — Air-Gapped Local LLM Entity Extraction Engine (Phase 6).

Uses Llama-3.2-3B-Instruct via local Ollama for sub-1.5s structured JSON extraction from
unstructured FIR/NCRP complaint narratives.

Air-gap safety guarantee:
  - Complaint text NEVER leaves the local network (strictly queries local Ollama).
  - No external outbound HTTP calls under any circumstance.
  - Automatically falls back to deterministic spaCy/Regex validator on LLM failure or timeout.
"""
import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import get_settings
from app.nlp.spacy_fallback import extract_entities_spacy_fallback

logger = logging.getLogger(__name__)
settings = get_settings()

OLLAMA_LOCAL_URL = getattr(settings, "ollama_url", "http://127.0.0.1:11434")
OLLAMA_MODEL = "llama3.2:3b"

STRUCTURED_EXTRACTION_PROMPT = """You are an expert Cyber Crime Forensic Intelligence Assistant.
Analyze the following police FIR / NCRP cyber fraud complaint narrative and extract key forensic entities.

Return ONLY a valid JSON object matching this schema:
{{
  "suspect_names": ["string"],
  "amounts_mentioned": [{{"amount": 0.0, "currency": "INR"}}],
  "crypto_addresses": [{{"address": "string", "chain": "BTC"}}],
  "dates_mentioned": ["YYYY-MM-DD or string"],
  "fraud_typology": "investment_fraud",
  "summary": "Concise 1-2 sentence executive summary"
}}

Allowed typology values: investment_fraud, job_task_scam, impersonation, sextortion, phishing, crypto_drainer, other.
Allowed chain values: BTC, ETH, TRON, BSC, UNKNOWN.

Complaint Narrative Text:
\"\"\"{text}\"\"\"
"""


async def extract_entities_from_narrative(
    text: Optional[str],
    timeout_seconds: float = 6.0,
) -> Dict[str, Any]:
    """
    Extract structured forensic entities from FIR narrative text using local Llama-3.2-3B.
    Falls back gracefully to spaCy/Regex if Ollama is unreachable, slow, or invalid.
    """
    if not text or not text.strip():
        return {
            "suspect_names": [],
            "amounts_mentioned": [],
            "crypto_addresses": [],
            "dates_mentioned": [],
            "fraud_typology": "unknown",
            "summary": "No narrative text provided.",
            "extractor_used": "none",
            "latency_ms": 0.0,
        }

    clean_text = text.strip()
    start_time = time.perf_counter()

    # 1. Attempt Air-Gapped Local LLM Extraction (Ollama)
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await client.post(
                f"{OLLAMA_LOCAL_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "user", "content": STRUCTURED_EXTRACTION_PROMPT.format(text=clean_text)}
                    ],
                    "format": "json",
                    "stream": False,
                    "options": {
                        "temperature": 0.0,
                        "num_ctx": 2048,
                    },
                },
            )

            if resp.status_code == 200:
                raw_content = resp.json().get("message", {}).get("content", "")
                parsed = json.loads(raw_content)

                # Validate structure
                if isinstance(parsed, dict) and "crypto_addresses" in parsed:
                    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    parsed["extractor_used"] = f"ollama_{OLLAMA_MODEL}"
                    parsed["latency_ms"] = latency_ms
                    logger.info("llm_ner_extracted_success", extra={"latency_ms": latency_ms, "model": OLLAMA_MODEL})
                    return parsed

    except Exception as e:
        logger.warning("local_llm_ner_failed_falling_back", extra={"error": str(e)})

    # 2. Fallback to spaCy & Deterministic Rules
    fallback_result = extract_entities_spacy_fallback(clean_text)
    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
    fallback_result["latency_ms"] = latency_ms
    logger.info("spacy_fallback_executed", extra={"latency_ms": latency_ms})

    return fallback_result
