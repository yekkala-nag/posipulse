from pathlib import Path
import pytest

def test_mobile_feed_screen_includes_autoseed_fallback():
    feed_screen_path = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "mobile"
        / "src"
        / "screens"
        / "FeedScreen.tsx"
    )
    assert feed_screen_path.exists(), "FeedScreen.tsx must exist"
    content = feed_screen_path.read_text(encoding="utf-8")
    
    # Assert auto-seeding fallback is present on initial empty feed
    assert "seedDemo" in content, "FeedScreen must support seedDemo"
    assert "autoSeeded" in content or "auto_seed" in content.lower(), (
        "FeedScreen must implement auto-seed fallback when feed is empty on initial load"
    )
