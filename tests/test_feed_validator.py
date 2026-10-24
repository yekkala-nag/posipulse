"""
Unit and integration tests for Feed Guidelines and Feed Validator (Step 2).
Covers RSS 2.0 / Atom 1.0 compliance, security audits, tracking parameter detection,
rights-mode preview simulation, API endpoint, and CLI execution.
"""

import json
import subprocess
import sys
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.ingestion.validator import FeedValidator, ValidationSeverity
from src.schemas.source import RightsMode, SourceProfile


SAMPLE_COMPLIANT_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <title>The Constructive Indian</title>
    <link>https://constructiveindian.org</link>
    <description>Daily constructive and developmental milestones from across India.</description>
    <language>en</language>
    <lastBuildDate>Sat, 24 Oct 2026 12:00:00 +0530</lastBuildDate>
    <item>
      <title>Solar Canal Project Powers 50 Villages in Vidarbha</title>
      <link>https://constructiveindian.org/news/solar-canal-vidarbha-project</link>
      <guid isPermaLink="true">https://constructiveindian.org/news/solar-canal-vidarbha-project</guid>
      <pubDate>Sat, 24 Oct 2026 10:30:00 +0530</pubDate>
      <description>Engineers and local panchayats have commissioned a 15 MW canal-top solar grid that prevents water evaporation and supplies round-the-clock green power to rural homes.</description>
      <category>Solar Energy</category>
      <category>Environment</category>
      <media:content url="https://constructiveindian.org/images/solar-canal.jpg" medium="image" type="image/jpeg" width="1200" height="675" />
    </item>
  </channel>
</rss>
"""

SAMPLE_COMPLIANT_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/atom" xml:lang="en">
  <title>Clean Energy Today</title>
  <link rel="alternate" type="text/html" href="https://cleanenergytoday.org" />
  <updated>2026-10-24T12:00:00+05:30</updated>
  <id>tag:cleanenergytoday.org,2026:feed</id>
  <entry>
    <title>High School Students Design Low-Cost Water Filtration System</title>
    <link rel="alternate" type="text/html" href="https://cleanenergytoday.org/stories/student-water-filtration" />
    <id>tag:cleanenergytoday.org,2026:entry-101</id>
    <published>2026-10-24T09:15:00+05:30</published>
    <summary>A student team in Mysore developed a bio-sand filtration unit using indigenous coconut shell carbon.</summary>
    <category term="education-skills" />
  </entry>
</feed>
"""


# ============================================================================
# 1. RSS & Atom Compliance Checks
# ============================================================================

def test_validate_fully_compliant_rss2():
    validator = FeedValidator()
    result = validator.validate_xml(SAMPLE_COMPLIANT_RSS, declared_language="en")

    assert result.status == "valid"
    assert result.error_count == 0
    assert result.warning_count == 0
    assert result.feed_format == "rss_2.0"
    assert result.feed_title == "The Constructive Indian"
    assert result.feed_link == "https://constructiveindian.org"
    assert result.total_items == 1
    assert result.valid_items_count == 1

    preview = result.item_previews[0]
    assert preview.title == "Solar Canal Project Powers 50 Villages in Vidarbha"
    assert preview.canonical_url == "https://constructiveindian.org/news/solar-canal-vidarbha-project"
    assert preview.thumbnail_url == "https://constructiveindian.org/images/solar-canal.jpg"
    assert preview.is_valid is True


def test_validate_fully_compliant_atom1():
    validator = FeedValidator()
    result = validator.validate_xml(SAMPLE_COMPLIANT_ATOM, declared_language="en")

    assert result.status == "valid"
    assert result.error_count == 0
    assert result.feed_format == "atom_1.0"
    assert result.total_items == 1
    assert result.valid_items_count == 1
    assert result.item_previews[0].title.startswith("High School Students")


# ============================================================================
# 2. Syntax, Malformed, and Missing Mandatory Fields
# ============================================================================

def test_validate_empty_and_malformed_xml():
    validator = FeedValidator()

    # Empty
    res_empty = validator.validate_xml("   ")
    assert res_empty.status == "invalid"
    assert any(i.code == "EMPTY_CONTENT" for i in res_empty.issues)

    # Completely broken XML
    res_broken = validator.validate_xml("<<not-xml>>>totally broken<<>>")
    assert res_broken.status == "invalid"
    assert any(i.code in ("MALFORMED_XML", "UNRECOGNIZED_FORMAT") for i in res_broken.issues)


def test_validate_missing_channel_and_item_fields():
    broken_feed = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <!-- missing title, missing link -->
        <item>
          <!-- missing title -->
          <link>http://insecure-domain.org/story-1</link>
        </item>
        <item>
          <title>Title with Missing Link</title>
          <!-- missing link -->
        </item>
      </channel>
    </rss>
    """
    validator = FeedValidator()
    result = validator.validate_xml(broken_feed)

    assert result.status == "invalid"
    error_codes = [i.code for i in result.issues if i.severity == ValidationSeverity.ERROR]
    assert "MISSING_FEED_TITLE" in error_codes
    assert "MISSING_FEED_LINK" in error_codes
    assert "MISSING_ITEM_TITLE" in error_codes
    assert "MISSING_CANONICAL_LINK" in error_codes


# ============================================================================
# 3. Security Audits & Tracking Detection
# ============================================================================

def test_validate_tracking_parameters():
    feed_with_tracking = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Tech Chronicle</title>
        <link>https://techchronicle.org</link>
        <item>
          <title>Open Source AI Model Released for Indian Languages</title>
          <link>https://techchronicle.org/ai-release?utm_source=twitter&amp;utm_medium=social&amp;fbclid=xyz987</link>
          <pubDate>Sat, 24 Oct 2026 10:00:00 +0530</pubDate>
          <description>Researchers announced a compact multilingual model.</description>
        </item>
      </channel>
    </rss>
    """
    validator = FeedValidator()
    result = validator.validate_xml(feed_with_tracking)

    assert result.status == "valid_with_warnings"
    tracking_issue = next((i for i in result.issues if i.code == "TRACKING_PARAMS_DETECTED"), None)
    assert tracking_issue is not None
    assert tracking_issue.severity == ValidationSeverity.WARNING


def test_validate_script_injection_and_tracking_pixels():
    dangerous_feed = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Security Alert Daily</title>
        <link>https://securityalert.org</link>
        <item>
          <title>Clean Water Project</title>
          <link>https://securityalert.org/clean-water</link>
          <description>
            Clean drinking water initiative.
            &lt;script&gt;alert('malicious');&lt;/script&gt;
            &lt;img src="https://tracker.org/pixel.gif" width="1" height="1" /&gt;
          </description>
        </item>
      </channel>
    </rss>
    """
    validator = FeedValidator()
    result = validator.validate_xml(dangerous_feed)

    assert result.status == "invalid"
    codes = [i.code for i in result.issues]
    assert "SCRIPT_INJECTION_DETECTED" in codes
    assert "TRACKING_PIXEL_DETECTED" in codes


def test_validate_article_dump_detection():
    # Long text exceeding 1000 words
    long_essay = " ".join(["constructive"] * 1050)
    dump_feed = f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Longform Journal</title>
        <link>https://longform.org</link>
        <item>
          <title>Exhaustive History of Rural Electrification</title>
          <link>https://longform.org/history</link>
          <description>{long_essay}</description>
        </item>
      </channel>
    </rss>
    """
    validator = FeedValidator()
    result = validator.validate_xml(dump_feed)

    dump_issue = next((i for i in result.issues if i.code == "ARTICLE_DUMP_DETECTED"), None)
    assert dump_issue is not None
    assert dump_issue.severity == ValidationSeverity.WARNING


# ============================================================================
# 4. Rights-Mode Simulation & Excerpt Truncation
# ============================================================================

def test_rights_mode_simulation_preview():
    profile_headline_only = SourceProfile(
        id="test-pub-headline", publisher_id="pub-1", publisher_name="Pub 1",
        primary_domain="constructiveindian.org", feed_urls=["https://constructiveindian.org/feed"],
        homepage_url="https://constructiveindian.org", language="en",
        rights_mode=RightsMode.HEADLINE_ONLY
    )
    profile_excerpt = SourceProfile(
        id="test-pub-excerpt", publisher_id="pub-1", publisher_name="Pub 1",
        primary_domain="constructiveindian.org", feed_urls=["https://constructiveindian.org/feed"],
        homepage_url="https://constructiveindian.org", language="en",
        rights_mode=RightsMode.FEED_PROVIDED_EXCERPT,
        excerpt_ceiling_chars=120,
        excerpt_ceiling_words=18
    )

    validator = FeedValidator()

    # 1. Headline-Only Preview
    res_hl = validator.validate_xml(SAMPLE_COMPLIANT_RSS, source_profile=profile_headline_only)
    assert res_hl.item_previews[0].display_excerpt is None
    assert res_hl.item_previews[0].rights_mode_applied == RightsMode.HEADLINE_ONLY

    # 2. Excerpt Preview
    res_ex = validator.validate_xml(SAMPLE_COMPLIANT_RSS, source_profile=profile_excerpt)
    excerpt = res_ex.item_previews[0].display_excerpt
    assert excerpt is not None
    assert len(excerpt) <= 123
    assert len(excerpt.split()) <= 19
    assert res_ex.item_previews[0].rights_mode_applied == RightsMode.FEED_PROVIDED_EXCERPT


def test_domain_mismatch_and_hidden_category_mapping():
    profile = SourceProfile(
        id="hindu-profile", publisher_id="the-hindu", publisher_name="The Hindu",
        primary_domain="thehindu.com", feed_urls=["https://thehindu.com/rss"],
        homepage_url="https://thehindu.com", language="en"
    )
    mismatched_feed = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>The Hindu National</title>
        <link>https://thehindu.com</link>
        <item>
          <title>Military Modernization and Border Security Deployment</title>
          <link>https://thirdparty-affiliate.com/story-123</link>
          <pubDate>Sat, 24 Oct 2026 10:00:00 +0530</pubDate>
          <category>defence-security</category>
          <description>Updates regarding regional defense and military personnel.</description>
        </item>
      </channel>
    </rss>
    """
    validator = FeedValidator()
    result = validator.validate_xml(mismatched_feed, source_profile=profile)

    codes = [i.code for i in result.issues]
    assert "DOMAIN_MISMATCH" in codes
    assert "HIDDEN_CATEGORY_MAPPED" in codes


# ============================================================================
# 5. FastAPI Endpoint Verification
# ============================================================================

def test_api_validate_feed_endpoint():
    app = create_app()
    client = TestClient(app)

    # Test validating compliant XML via API
    payload = {
        "xml_content": SAMPLE_COMPLIANT_RSS,
        "primary_domain": "constructiveindian.org",
        "language": "en",
        "rights_mode": "feed_provided_excerpt"
    }
    response = client.post("/v1/publishers/validate-feed", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "valid"
    assert data["total_items"] == 1
    assert data["valid_items_count"] == 1
    assert len(data["item_previews"]) == 1
    assert data["item_previews"][0]["display_excerpt"] is not None

    # Test bad request when neither feed_url nor xml_content is provided
    empty_resp = client.post("/v1/publishers/validate-feed", json={"primary_domain": "test.com"})
    assert empty_resp.status_code == 400


# ============================================================================
# 6. CLI Execution
# ============================================================================

def test_cli_execution_via_python_module(tmp_path):
    feed_file = tmp_path / "test_feed.xml"
    feed_file.write_text(SAMPLE_COMPLIANT_RSS, encoding="utf-8")

    cmd = [
        sys.executable,
        "-m", "src.ingestion.validator",
        "--file", str(feed_file),
        "--domain", "constructiveindian.org",
        "--rights-mode", "feed_provided_excerpt",
        "--format", "json"
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0
    parsed_json = json.loads(proc.stdout)
    assert parsed_json["status"] == "valid"
    assert parsed_json["total_items"] == 1
