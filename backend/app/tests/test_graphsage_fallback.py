import pytest

from app.ml.graphsage_risk import compute_graph_context_summary


def test_graph_context_summary_returns_neighbor_stats():
    summary = compute_graph_context_summary("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")

    assert isinstance(summary, dict)
    assert "address" in summary
    assert "neighbor_count" in summary
    assert "is_sparse" in summary
    assert "mode" in summary
    assert summary["address"] == "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
    assert summary["neighbor_count"] >= 0
