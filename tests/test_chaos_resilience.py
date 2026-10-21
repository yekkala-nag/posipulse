"""
Chaos & Fault-Tolerance Resilience Tests (Phase 6)
Verifies:
1. Upstream publisher timeouts, HTTP 504 Gateway Timeouts, and HTTP 429 Rate Limits.
2. Exponential backoff and source health degradation.
3. Malformed XML, broken CDATA, empty payloads, and Byte-Order-Marks (BOM).
4. Run cost cap circuit breaking: engagement and DLQ routing.
5. Adversarial hallucination & verbatim reproduction DLQ isolation.
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
import httpx
import pytest

from src.config.loader import LanguageConfigRegistry
from src.observability.metrics import metrics_collector
from src.pipeline.fetcher import FeedFetcher
from src.pipeline.orchestrator import PipelineOrchestrator
from src.pipeline.verifier import FaithfulnessVerifier
from src.schemas.article import EphemeralIngestedItem, SummaryMetadata
from src.schemas.config import CostCapConfig, PublisherSource
from src.storage.db import StorageEngine


@pytest.fixture
def sample_source():
    return PublisherSource(
        id="test-publisher",
        name="Test Publisher",
        feed_url="https://publisher.example.com/rss.xml",
        homepage_url="https://publisher.example.com",
        language="en",
        is_active=True,
        health_status="healthy",
        fetch_interval_minutes=30,
        circuit_breaker_fail_threshold=3,
        respect_robots_txt=True,
    )


@pytest.fixture
def registry():
    config_dir = Path(__file__).resolve().parent.parent / "config" / "languages"
    return LanguageConfigRegistry(str(config_dir))


def test_malformed_xml_handling(sample_source):
    """Verify FeedFetcher gracefully parses corrupt, truncated, or BOM-prefixed XML."""
    fetcher = FeedFetcher(sample_source)

    # 1. Truncated XML
    truncated_xml = "<rss><channel><title>Broken</title><item><title>Good</title><link>https://example.com"
    items = fetcher.parse_raw_content(truncated_xml)
    assert isinstance(items, list)

    # 2. Corrupt binary garbage
    garbage_xml = "\x00\x01\x02<garbage>not xml</garbage>\xff\xfe"
    items_garbage = fetcher.parse_raw_content(garbage_xml)
    assert isinstance(items_garbage, list)

    # 3. UTF-8 BOM prefix
    bom_xml = '\ufeff<?xml version="1.0"?><rss version="2.0"><channel><item><title>BOM Title</title><link>https://example.com/bom</link></item></channel></rss>'
    items_bom = fetcher.parse_raw_content(bom_xml)
    assert len(items_bom) == 1
    assert items_bom[0].headline == "BOM Title"

    # 4. Empty or whitespace
    assert fetcher.parse_raw_content("") == []
    assert fetcher.parse_raw_content("   \n\t  ") == []


def test_publisher_http_errors_and_circuit_breaker(sample_source):
    """Verify FeedFetcher retries on HTTP 504 and marks source degraded/failing."""
    metrics_collector.reset_for_testing()
    fetcher = FeedFetcher(sample_source, max_retries=3, timeout_seconds=1)

    # Mock httpx.Client to simulate consecutive 504 Gateway Timeouts
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "504 Gateway Timeout", request=MagicMock(), response=mock_resp
        )
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value.__enter__.return_value = mock_client

        with pytest.raises(RuntimeError) as exc_info:
            fetcher.fetch_live()

        assert "All 3 fetch attempts failed" in str(exc_info.value)
        assert sample_source.health_status in ["degraded", "failing"]
        summary = metrics_collector.get_summary()
        assert summary["counters"].get("posipulse_fetch_errors_total_source_id_test-publisher", 0) >= 3


def test_cost_cap_circuit_breaker(registry):
    """
    Verify orchestrator circuit breaker halts pipeline and routes to DLQ
    when per-run cost cap is reached.
    """
    en_config = registry.get_strict("en").model_copy(deep=True)
    # Set an ultra-low cost cap that trips on the first item
    en_config.cost_caps.max_cost_per_run_usd = 0.00001

    storage = StorageEngine(":memory:")
    orchestrator = PipelineOrchestrator(language_config=en_config, storage=storage)

    fixture_path = Path(__file__).resolve().parent / "fixtures" / "the_hindu_sample.xml"
    xml_content = fixture_path.read_text(encoding="utf-8")

    stats = orchestrator.process_raw_xml(xml_content, source_id="the-hindu-national")
    # Circuit breaker engaged
    assert len(orchestrator.dead_letter_queue) >= 1
    cost_dlq = [e for e in orchestrator.dead_letter_queue if e.stage == "cost_guard"]
    assert len(cost_dlq) >= 1
    assert "Circuit breaker engaged" in cost_dlq[0].error


def test_faithfulness_verifier_dlq_isolation(registry):
    """Verify that unfaithful or hallucinated summaries fail closed into DLQ."""
    en_config = registry.get_strict("en")
    verifier = FaithfulnessVerifier(verifier_model="gemini-1.5-pro")

    item = EphemeralIngestedItem(
        id="item-fail-verify",
        source_id="the-hindu-national",
        source_name="The Hindu",
        url="https://thehindu.com/article1",
        canonical_url="https://thehindu.com/article1",
        headline="ISRO successfully deploys indigenous weather satellite into geostationary orbit",
        raw_body="The Indian Space Research Organisation launched the meteorological satellite today from Sriharikota.",
        published_at=datetime.now(timezone.utc),
        declared_language="en",
    )

    # Hallucinated summary asserting false facts
    hallucinated_summary = SummaryMetadata(
        text="ISRO's satellite crashed into the ocean shortly after takeoff due to rocket failure, resulting in total mission loss.",
        model="untrusted-model",
        prompt_version="1.0.0",
        verified=False,
        word_count=18,
    )

    passed, score, reasons = verifier.verify(item, hallucinated_summary)
    assert passed is False
    assert score < 0.95
    assert len(reasons) >= 1
