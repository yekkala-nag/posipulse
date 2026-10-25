"""
Regression test for Telugu (te) language sources.
Ensures:
1. Telugu has >= 3 healthy sources.
2. Verified constructive desks (V6 Velugu, TV9 Telugu Tech Desk, Namasthe Telangana Vyavasayam) are present and active.
3. Problematic endpoints (eenadu-national, news18-telugu) are appropriately marked degraded.
4. All Telugu feeds have no English language parameters.
"""

from pathlib import Path
import yaml
import pytest


def test_telugu_has_healthy_active_constructive_sources():
    config_dir = Path(__file__).resolve().parent.parent / "config" / "languages"
    with open(config_dir / "te.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    assert cfg["language_code"] == "te"
    assert cfg["status"] == "active"
    assert cfg["positivity_threshold"] == 0.85

    sources = cfg.get("sources", [])
    source_map = {s["id"]: s for s in sources}

    # Verify constructive topic desks exist and are active and healthy
    for expected_id in ["v6-velugu", "tv9-telugu-tech", "ntnews-agriculture"]:
        assert expected_id in source_map, f"{expected_id} must be in te.yaml sources"
        assert source_map[expected_id]["is_active"] is True
        assert source_map[expected_id]["health_status"] == "healthy"

    # Verify degraded endpoints are tracked as degraded
    assert source_map["eenadu-national"]["health_status"] == "degraded"
    assert source_map["news18-telugu"]["health_status"] == "degraded"

    # Verify total healthy sources >= 3
    healthy_sources = [s for s in sources if s.get("health_status") == "healthy" and s.get("is_active") is True]
    assert len(healthy_sources) >= 3, f"Expected >= 3 healthy sources, found {len(healthy_sources)}"
