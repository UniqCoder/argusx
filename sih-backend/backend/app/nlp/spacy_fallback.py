"""
app/nlp/spacy_fallback.py — Offline, Air-Gapped Fallback and Entity Validator (Phase 6).

Provides deterministic rule-based and spaCy NLP entity extraction when the local
LLM is offline, times out, or produces malformed JSON.
"""
import re
from typing import Any, Dict, List, Optional
import logging

from app.schemas.common import Chain

logger = logging.getLogger(__name__)

# Regular expressions for crypto wallet addresses
BTC_BECH32_PATTERN = r"\b(bc1[a-z0-9]{38,59}|tb1[a-z0-9]{38,59})\b"
BTC_LEGACY_PATTERN = r"\b([13][a-km-zA-HJ-NP-Z1-9]{25,34})\b"
ETH_PATTERN = r"\b(0x[a-fA-F0-9]{40})\b"
TRON_PATTERN = r"\b(T[a-zA-Z0-9]{33})\b"

# Currency / Amount patterns
AMOUNT_PATTERN = r"(?:(?:(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?(?:\s*(?:lakh|lakhs|cr|crore|k))?))|(?:([\d,]+(?:\.\d+)?)\s*(?:rs\.?|inr|rupees|lakh|lakhs|cr|crore|usdt|usd|btc|eth)))"

# Date patterns
DATE_PATTERN = r"\b(\d{4}-\d{2}-\d{2}|\d{2}[-/]\d{2}[-/]\d{4}|\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4})\b"

# Typology keywords
TYPOLOGY_KEYWORDS = {
    "investment_fraud": ["investment", "returns", "trading", "profit", "crypto return", "forex", "binary", "guaranteed"],
    "job_task_scam": ["task", "part-time", "part time", "youtube like", "hotel review", "recharge", "prepaid task", "telegram task"],
    "impersonation": ["cbi", "police", "customs", "mha", "fedex", "parcel", "arrest", "digital arrest", "officer"],
    "sextortion": ["video call", "nude", "blackmail", "whatsapp call", "threat"],
    "phishing": ["apk", "link", "otp", "kyc", "bank update", "credit card limit", "screen share", "anydesk"],
    "crypto_drainer": ["permit", "drainer", "smart contract", "airdrop", "approve", "metamask"],
}


def extract_wallets_regex(text: str) -> List[Dict[str, str]]:
    """Extract blockchain wallet addresses via deterministic regular expressions."""
    found: List[Dict[str, str]] = []
    seen = set()

    for match in re.finditer(ETH_PATTERN, text):
        addr = match.group(1)
        if addr not in seen:
            seen.add(addr)
            found.append({"address": addr, "chain": "ETH"})

    for match in re.finditer(BTC_BECH32_PATTERN, text, re.IGNORECASE):
        addr = match.group(1)
        if addr not in seen:
            seen.add(addr)
            found.append({"address": addr, "chain": "BTC"})

    for match in re.finditer(BTC_LEGACY_PATTERN, text):
        addr = match.group(1)
        if addr not in seen and not addr.startswith("0x"):
            seen.add(addr)
            found.append({"address": addr, "chain": "BTC"})

    for match in re.finditer(TRON_PATTERN, text):
        addr = match.group(1)
        if addr not in seen:
            seen.add(addr)
            found.append({"address": addr, "chain": "TRON"})

    return found


def extract_amounts_regex(text: str) -> List[Dict[str, Any]]:
    """Extract financial amounts and normalize units (e.g. lakh, cr)."""
    amounts: List[Dict[str, Any]] = []
    
    # 1. Match numeric expressions with lakh/cr
    lakh_matches = re.finditer(r"([\d.]+)\s*(?:lakh|lakhs|lac|lacs)", text, re.IGNORECASE)
    for m in lakh_matches:
        try:
            val = float(m.group(1)) * 100000.0
            amounts.append({"amount": val, "currency": "INR"})
        except ValueError:
            pass

    cr_matches = re.finditer(r"([\d.]+)\s*(?:cr|crore|crores)", text, re.IGNORECASE)
    for m in cr_matches:
        try:
            val = float(m.group(1)) * 10000000.0
            amounts.append({"amount": val, "currency": "INR"})
        except ValueError:
            pass

    # 2. Match standard digits with leading or trailing currency (e.g. Rs 50,000 or 75000 inr / 75000 rupees)
    std_matches = re.finditer(r"(?:(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?))|(?:([\d,]+(?:\.\d+)?)\s*(?:rs\.?|inr|rupees|usd|usdt|btc|eth))", text, re.IGNORECASE)
    for m in std_matches:
        raw_num = (m.group(1) or m.group(2) or "").replace(",", "")
        try:
            val = float(raw_num)
            if val > 10.0:  # ignore trivial numbers
                amounts.append({"amount": val, "currency": "INR"})
        except ValueError:
            pass

    # Deduplicate amounts
    unique_amounts = []
    seen = set()
    for a in amounts:
        key = (a["amount"], a["currency"])
        if key not in seen:
            seen.add(key)
            unique_amounts.append(a)

    return unique_amounts


def extract_dates_regex(text: str) -> List[str]:
    """Extract dates mentioned in narrative."""
    dates = []
    seen = set()
    for m in re.finditer(DATE_PATTERN, text, re.IGNORECASE):
        d = m.group(1).strip()
        if d not in seen:
            seen.add(d)
            dates.append(d)
    return dates


def classify_typology_regex(text: str) -> str:
    """Classify cyber fraud typology via keyword frequency heuristic."""
    text_lower = text.lower()
    scores = {}
    for typology, keywords in TYPOLOGY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[typology] = score

    if scores:
        return max(scores, key=scores.get)
    return "other"


def extract_entities_spacy_fallback(text: str) -> Dict[str, Any]:
    """
    Complete offline fallback extracting suspect names, wallets, amounts, dates, and typology.
    """
    suspect_names: List[str] = []

    # Attempt spaCy Person extraction
    try:
        import spacy
        try:
            nlp = spacy.load("en_core_web_sm")
            doc = nlp(text)
            for ent in doc.ents:
                if ent.label_ == "PERSON" and len(ent.text.strip()) > 2:
                    suspect_names.append(ent.text.strip())
        except Exception:
            # Blank English token heuristic fallback
            nlp = spacy.blank("en")
            doc = nlp(text)
            # Find capitalized name pairs following words like 'against', 'named', 'admin', 'scammer'
            pattern = re.finditer(r"(?:against|named|admin|caller|scammer|fraudster|impersonating)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)", text)
            for m in pattern:
                suspect_names.append(m.group(1).strip())
    except Exception as e:
        logger.warning("spacy_extraction_failed", extra={"error": str(e)})

    wallets = extract_wallets_regex(text)
    amounts = extract_amounts_regex(text)
    dates = extract_dates_regex(text)
    typology = classify_typology_regex(text)

    return {
        "suspect_names": list(dict.fromkeys(suspect_names)),
        "amounts_mentioned": amounts,
        "crypto_addresses": wallets,
        "dates_mentioned": dates,
        "fraud_typology": typology,
        "summary": text[:200] + ("..." if len(text) > 200 else ""),
        "extractor_used": "spacy_rule_fallback",
    }
