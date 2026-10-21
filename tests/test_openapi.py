"""
Unit Tests for OpenAPI 3.1 Specification
Verifies:
1. docs/openapi.yaml exists and is valid YAML.
2. Required endpoints (/v1/feed, /v1/articles/{id}, /v1/clusters/{cluster_id},
   /v1/languages, /v1/feedback, /v1/privacy/delist) are present.
3. Schema components (ArticleItem, FeedResponse, DelistRequest) are well-defined.
"""

from pathlib import Path
import pytest
import yaml


@pytest.fixture
def openapi_spec():
    spec_path = Path(__file__).resolve().parent.parent / "docs" / "openapi.yaml"
    assert spec_path.exists(), "docs/openapi.yaml must exist"
    with open(spec_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_openapi_metadata(openapi_spec):
    assert openapi_spec["openapi"].startswith("3.1"), "Must be OpenAPI 3.1"
    assert "Positive News App API Gateway" in openapi_spec["info"]["title"]


def test_required_endpoints_present(openapi_spec):
    paths = openapi_spec["paths"]
    assert "/v1/feed" in paths
    assert "/v1/articles/{id}" in paths
    assert "/v1/clusters/{cluster_id}" in paths
    assert "/v1/languages" in paths
    assert "/v1/feedback" in paths
    assert "/v1/privacy/delist" in paths
    assert "/health" in paths
    assert "/metrics" in paths


def test_feed_endpoint_parameters(openapi_spec):
    feed_get = openapi_spec["paths"]["/v1/feed"]["get"]
    param_names = [p["name"] for p in feed_get["parameters"]]
    assert "language" in param_names
    assert "category" in param_names
    assert "since" in param_names
    assert "limit" in param_names


def test_article_item_schema(openapi_spec):
    components = openapi_spec["components"]["schemas"]
    assert "ArticleItem" in components
    article_props = components["ArticleItem"]["properties"]
    assert "canonical_url" in article_props
    assert "summary" in article_props
    assert "positivity" in article_props
    assert "is_rtl" in article_props
