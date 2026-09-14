// ============================================================
// Evidence strength — LOW / MEDIUM / HIGH, defined.
//
// Before this file, "evidence strength" was just correlation_score's own
// LOW/MED/HIGH bucketing re-shown wherever a signal chip appeared — a proxy
// for "how many victims complained", nothing else. Now that risk scoring is
// real (a trained XGBoost model + SHAP evidence, not N/A), evidence strength
// should reflect BOTH independent signals ARGUS actually has about a wallet:
//
//   1. VICTIM CORRELATION — how many independent complaints, across how many
//      states, name this wallet (correlation_service.calculate_correlation_score,
//      [0,1]). Real, backend-computed, never recalculated here.
//   2. ML RISK TIER — the trained model's own classification of the wallet's
//      on-chain behavior (critical/high/medium/low/unknown), independent of
//      whether anyone has complained about it yet.
//
// A wallet with 3 complaints AND a critical ML score is stronger evidence
// than either signal alone — that agreement between two independent sources
// is the actual thing worth calling "HIGH". A wallet with only one weak
// signal and nothing else corroborating it should not read as certain.
//
// The thresholds below are named and documented so the criteria are
// auditable, not a black box — and so a reviewer can tell WHY a wallet
// landed in a tier, not just that it did.
// ============================================================

export type EvidenceStrength = "HIGH" | "MEDIUM" | "LOW" | "NONE";

// The backend's RiskTier enum values, but typed as a plain string here (not
// a strict union) since callers pass this straight through from the API
// response — no local re-validation of a value the backend already owns.
export type RiskTier = string | null;

export interface EvidenceInput {
  /** correlation_service.calculate_correlation_score, [0,1]. Null/undefined
   * when no correlation has been run yet for this wallet. */
  correlationScore?: number | null;
  /** The ML model's own tier for this wallet, when a score exists. */
  riskTier?: RiskTier;
}

export interface EvidenceResult {
  strength: EvidenceStrength;
  /** Which signal(s) actually drove the classification — shown in the UI so
   * "HIGH" is never a bare label with nothing behind it. */
  reasons: string[];
}

// Named thresholds — change these in one place, not per-page.
const CORRELATION_HIGH = 0.7; // ~3+ complaints across multiple states
const CORRELATION_MEDIUM = 0.3; // ~2 complaints, or 1 complaint + multi-state
const CORRELATION_LOW = 0.0; // any complaint at all

const RISK_TIER_STRONG = new Set(["critical", "high"]);

/**
 * Combine victim-correlation and ML-risk signals into one evidence-strength
 * verdict. Either signal alone can still produce a verdict (a wallet may
 * have complaints but no risk score yet, or vice versa) — but agreement
 * between the two is what earns HIGH.
 */
export function computeEvidenceStrength(input: EvidenceInput): EvidenceResult {
  const correlation = input.correlationScore ?? null;
  const tier = input.riskTier ?? null;
  const reasons: string[] = [];

  const correlationBand: EvidenceStrength =
    correlation == null
      ? "NONE"
      : correlation >= CORRELATION_HIGH
        ? "HIGH"
        : correlation >= CORRELATION_MEDIUM
          ? "MEDIUM"
          : correlation > CORRELATION_LOW
            ? "LOW"
            : "NONE";

  if (correlationBand !== "NONE") {
    reasons.push(
      correlationBand === "HIGH"
        ? "Multiple independent victims, across states, name this wallet"
        : correlationBand === "MEDIUM"
          ? "More than one independent complaint names this wallet"
          : "At least one complaint names this wallet",
    );
  }

  const riskIsStrong = tier != null && RISK_TIER_STRONG.has(tier);
  if (riskIsStrong) {
    reasons.push(`ML risk model independently classifies this wallet as ${tier}`);
  }

  // Two independent signals agreeing is the actual definition of HIGH here —
  // not just "correlation alone crossed a number".
  let strength: EvidenceStrength;
  if (correlationBand === "HIGH" || (correlationBand === "MEDIUM" && riskIsStrong)) {
    strength = "HIGH";
  } else if (correlationBand === "MEDIUM" || riskIsStrong) {
    strength = "MEDIUM";
  } else if (correlationBand === "LOW") {
    strength = "LOW";
  } else {
    strength = "NONE";
  }

  if (reasons.length === 0) {
    reasons.push("No complaint or risk signal available for this wallet yet");
  }

  return { strength, reasons };
}
