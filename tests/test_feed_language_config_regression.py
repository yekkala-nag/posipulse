from pathlib import Path
import yaml
import pytest

def test_feed_language_config_no_english_mismatch():
    config_dir = Path(__file__).resolve().parent.parent / "config" / "languages"
    
    # 1. Odia config check
    with open(config_dir / "or.yaml", "r", encoding="utf-8") as f:
        or_cfg = yaml.safe_load(f)
    
    for src in or_cfg.get("sources", []):
        if src.get("id") == "odisha-tv":
            assert src.get("feed_url") != "https://odishatv.in/feed", (
                "odisha-tv in or.yaml is pointing to the English feed (https://odishatv.in/feed) "
                "instead of the Odia feed (https://otvkhabar.in/rss)"
            )
            assert "otvkhabar.in" in src.get("feed_url"), (
                f"odisha-tv feed URL should point to otvkhabar.in, got {src.get('feed_url')}"
            )

    # 2. Konkani config check
    with open(config_dir / "gom.yaml", "r", encoding="utf-8") as f:
        gom_cfg = yaml.safe_load(f)
    
    for src in gom_cfg.get("sources", []):
        if src.get("id") == "google-news-goa-konkani":
            feed_url = src.get("feed_url", "")
            assert "hl=en" not in feed_url, (
                f"google-news-goa-konkani in gom.yaml is configured with English language params: {feed_url}"
            )
            assert "q=Goa+Konkani" not in feed_url, (
                f"google-news-goa-konkani in gom.yaml is querying in English: {feed_url}"
            )
