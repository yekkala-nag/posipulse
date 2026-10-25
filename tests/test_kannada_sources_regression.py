from pathlib import Path
import yaml
import pytest

def test_kannada_has_healthy_active_sources():
    config_dir = Path(__file__).resolve().parent.parent / "config" / "languages"
    with open(config_dir / "kn.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    
    source_ids = [s["id"] for s in cfg.get("sources", [])]
    # Verify tv9-kannada is present and active
    assert "tv9-kannada" in source_ids, "tv9-kannada must be present in kn.yaml sources"
    
    tv9_src = next(s for s in cfg["sources"] if s["id"] == "tv9-kannada")
    assert tv9_src["is_active"] is True
    assert tv9_src["feed_url"] == "https://tv9kannada.com/feed"
