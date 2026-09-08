"""
app/ml/shap_report.py — Generate SHAP evidence reports for demo addresses.

Computes SHAP feature contributions for test addresses to show how graph
features influence model predictions relative to tabular features.
"""
import json
import logging
import os

import numpy as np
import pandas as pd
import xgboost as xgb
import shap
import joblib

from app.ml.features import FEATURE_COLUMNS, GRAPH_FEATURE_COLUMNS
from app.ml.train import ARTIFACTS_DIR

logger = logging.getLogger(__name__)

# Demo addresses from the project (known illicit, TRON scams, etc.)
DEMO_ADDRESSES = {
    "garantex_deposit": {
        "address": "3Lpoy53K625zVeE47ZasiG5jGkAxJ27kh1",
        "chain": "BTC",
        "description": "Garantex crypto exchange (known illicit in OFAC records)",
    },
    "lazarus_proxy": {
        "address": "TLa2f6VPqDMsaxQVj7FSrsDjjQuT5Zox1g",
        "chain": "TRON",
        "description": "Lazarus Group proxy address (TRON chain)",
    },
    "satoshi_genesis": {
        "address": "1A1z7agoat4wr8GkidKjsKtdGuwAks2t24",
        "chain": "BTC",
        "description": "Satoshi Nakamoto genesis output (historical, unique topology)",
    },
}


def load_trained_model(model_path: str | None = None) -> xgb.XGBClassifier:
    """Load the trained XGBoost model."""
    if model_path is None:
        model_path = os.path.join(ARTIFACTS_DIR, "risk_model_with_graph_features.joblib")
    
    if not os.path.exists(model_path):
        # Fall back to production model
        model_path = os.path.join(ARTIFACTS_DIR, "risk_model.joblib")
    
    logger.info(f"Loading model from {model_path}")
    return joblib.load(model_path)


def generate_shap_report(
    model: xgb.XGBClassifier,
    X_features: pd.DataFrame,
    demo_addresses: dict[str, dict],
    output_path: str | None = None,
) -> dict:
    """
    Generate SHAP contribution report for demo addresses.
    
    Args:
        model: trained XGBoost model
        X_features: DataFrame with all feature values (one row per demo address)
        demo_addresses: dict mapping address -> metadata
        output_path: where to save JSON report
    
    Returns:
        dict with SHAP contributions for each address
    """
    
    logger.info("Computing SHAP values for demo addresses...")
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_features)
    
    # Handle multi-class output
    if isinstance(shap_values, list):
        shap_values = shap_values[1]  # Use illicit class (class 1)
    
    predictions = model.predict_proba(X_features)[:, 1]
    
    report = {
        "metadata": {
            "model_path": os.path.join(ARTIFACTS_DIR, "risk_model_with_graph_features.joblib"),
            "feature_count": len(FEATURE_COLUMNS),
            "graph_features": GRAPH_FEATURE_COLUMNS,
        },
        "demo_addresses": {},
    }
    
    for (addr_key, addr_info), pred, shap_row in zip(demo_addresses.items(), predictions, shap_values):
        address = addr_info["address"]
        chain = addr_info["chain"]
        description = addr_info["description"]
        
        # Get feature values and SHAP contributions
        features_at_address = X_features.iloc[len(report["demo_addresses"])].to_dict()
        
        # Rank features by absolute SHAP contribution
        feature_contributions = [
            {
                "feature": FEATURE_COLUMNS[i],
                "value": float(features_at_address.get(FEATURE_COLUMNS[i], 0.0)),
                "shap_value": float(shap_row[i]),
                "abs_shap": float(np.abs(shap_row[i])),
                "is_graph_feature": FEATURE_COLUMNS[i] in GRAPH_FEATURE_COLUMNS,
            }
            for i in range(len(FEATURE_COLUMNS))
        ]
        
        # Sort by absolute SHAP contribution
        feature_contributions.sort(key=lambda x: x["abs_shap"], reverse=True)
        
        report["demo_addresses"][addr_key] = {
            "address": address,
            "chain": chain,
            "description": description,
            "predicted_risk_score": float(pred),
            "top_10_contributing_features": feature_contributions[:10],
            "graph_feature_contributions": [
                f for f in feature_contributions
                if f["is_graph_feature"]
            ],
        }
        
        logger.info(
            f"\n{addr_key} ({address}):"
            f"\n  Risk Score: {pred:.4f}"
            f"\n  Top Feature: {feature_contributions[0]['feature']} "
            f"(SHAP: {feature_contributions[0]['shap_value']:.6f})"
        )
    
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        logger.info(f"Saved SHAP report to {output_path}")
    
    return report


if __name__ == "__main__":
    import argparse
    
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", default=None, help="Path to trained model")
    parser.add_argument("--output-path", default=None, help="Path to save report")
    args = parser.parse_args()
    
    model = load_trained_model(args.model_path)
    
    # Create dummy feature DataFrame for demo addresses
    # In practice, these would come from live feature extraction
    X_demo = pd.DataFrame({
        col: [0.0] * len(DEMO_ADDRESSES)
        for col in FEATURE_COLUMNS
    })
    
    report = generate_shap_report(
        model,
        X_demo,
        DEMO_ADDRESSES,
        output_path=args.output_path or os.path.join(ARTIFACTS_DIR, "shap_demo_report.json"),
    )
    
    print("\n" + "="*70)
    print("SHAP REPORT")
    print("="*70)
    print(json.dumps(report, indent=2))
