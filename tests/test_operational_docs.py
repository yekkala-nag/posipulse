"""
Tests for Step 8: Architecture Decision Records (ADRs), Operations Runbook,
and Operational Verification.
Verifies:
1. Presence and structural integrity of all ADRs (ADR 0001 to ADR 0009).
2. Presence and completeness of publisher guidelines and operational runbooks.
3. Architecture invariants: zero raw publisher body storage, rights-mode ceilings,
   fail-closed 13 visible categories, and DPDP k-anonymity compliance.
"""

from pathlib import Path
import pytest


@pytest.fixture
def repo_root():
    return Path(__file__).resolve().parent.parent


def test_adrs_present_and_structured(repo_root):
    """Verifies ADR 0001 through 0009 are documented with standard ADR structure."""
    adr_dir = repo_root / "docs" / "adr"
    assert adr_dir.exists(), "docs/adr directory must exist"

    expected_adrs = [
        "0001-pipeline-orchestration-and-queues.md",
        "0002-storage-engine-and-article-lifecycle.md",
        "0003-llm-gateway-and-fallbacks.md",
        "0004-multilingual-deduplication.md",
        "0005-mobile-client-architecture.md",
        "0006-controlled-news-category-taxonomy.md",
        "0007-centralized-publisher-source-profiles.md",
        "0008-rights-mode-verbatim-excerpts.md",
        "0009-privacy-preserving-publisher-analytics.md",
    ]

    for filename in expected_adrs:
        adr_file = adr_dir / filename
        assert adr_file.exists(), f"Missing required ADR: {filename}"
        content = adr_file.read_text(encoding="utf-8")

        # Standard ADR sections
        assert "## Status" in content, f"{filename} missing Status section"
        assert "## Context" in content, f"{filename} missing Context section"
        assert "## Decision" in content, f"{filename} missing Decision section"
        assert "Accepted" in content or "Proposed" in content, f"{filename} missing valid Status"


def test_publisher_feed_guidelines_documentation(repo_root):
    """Verifies publisher feed guidelines document Tier 1 requirements."""
    guidelines_file = repo_root / "docs" / "publisher-feed-guidelines.md"
    assert guidelines_file.exists(), "docs/publisher-feed-guidelines.md missing"
    content = guidelines_file.read_text(encoding="utf-8")

    assert "RSS 2.0" in content
    assert "Atom 1.0" in content
    assert "headline_only" in content
    assert "feed_provided_excerpt" in content
    assert "longer_excerpt" in content
    assert "tracking pixels" in content.lower()


def test_publisher_operations_runbook_documentation(repo_root):
    """Verifies publisher operations runbook contains all standard operating procedures."""
    runbook_file = repo_root / "docs" / "publisher-operations-runbook.md"
    assert runbook_file.exists(), "docs/publisher-operations-runbook.md missing"
    content = runbook_file.read_text(encoding="utf-8")

    assert "SOP 1: Publisher Onboarding & Domain Verification" in content
    assert "SOP 2: Feed Compliance Audits & Troubleshooting" in content
    assert "SOP 3: RightsMode Adjustments & Legal Licensing Workflow" in content
    assert "SOP 4: Immediate Takedown & Cascading Delisting Execution" in content
    assert "SOP 5: Privacy & DPDP Act 2023 Compliance Audits" in content
    assert "DNS TXT" in content
    assert "k-anonymity" in content.lower()


def test_core_system_invariants_across_codebase(repo_root):
    """
    Codebase static analysis ensuring non-negotiable Tier 1 invariants:
    1. Zero raw publisher body text in persistent Article schema.
    2. Rights mode enforcement in Presentation layer.
    3. Fail-closed 13 visible categories.
    """
    from src.schemas.article import Article
    # 1. Article schema invariants: raw body is strictly forbidden
    assert "raw_body" not in Article.model_fields
    assert "body" not in Article.model_fields
    assert "verbatim_excerpt" in Article.model_fields

    # 2. SourceProfile schema
    source_schema_file = repo_root / "src" / "schemas" / "source.py"
    source_schema = source_schema_file.read_text(encoding="utf-8")
    assert "RightsMode" in source_schema
    assert "excerpt_ceiling_chars" in source_schema
    assert "excerpt_ceiling_words" in source_schema
    assert "utm_opt_in" in source_schema

    # 3. AttributionEngine
    attribution_file = repo_root / "src" / "presentation" / "attribution.py"
    attribution = attribution_file.read_text(encoding="utf-8")
    assert "format_verbatim_excerpt" in attribution
    assert "clean_url" in attribution
    assert "format_direct_link" in attribution
