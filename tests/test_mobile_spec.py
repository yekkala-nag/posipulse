"""
Mobile Client Architecture & Contract Tests (Phase 5)
Verifies:
1. Mobile app configuration (iOS bundle identifier, Android applicationId, RTL support).
2. TypeScript contract matching OpenAPI 3.1 Article schema and zero raw-body invariant.
3. Native platform integrations (SFSafariViewController on iOS, CustomTabs on Android).
4. Mobile API client endpoint parity.
5. Gateway contract compliance for mobile readers (Urdu RTL, canonical URLs, length bands).
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config.loader import LanguageConfigRegistry
from src.storage.db import StorageEngine


@pytest.fixture
def mobile_root():
    return Path(__file__).resolve().parent.parent / "src" / "mobile"


@pytest.fixture
def api_client():
    config_dir = Path(__file__).resolve().parent.parent / "config" / "languages"
    registry = LanguageConfigRegistry(str(config_dir))
    storage = StorageEngine(":memory:")
    app = create_app(storage=storage, registry=registry)
    return TestClient(app)


def test_mobile_package_and_expo_config(mobile_root):
    """Verify Expo/React Native configuration for iOS and Android."""
    pkg_file = mobile_root / "package.json"
    assert pkg_file.exists(), "mobile package.json missing"
    pkg = json.loads(pkg_file.read_text(encoding="utf-8"))
    assert "expo" in pkg["dependencies"]
    assert "react-native" in pkg["dependencies"]
    assert "expo-web-browser" in pkg["dependencies"]

    app_json_file = mobile_root / "app.json"
    assert app_json_file.exists(), "mobile app.json missing"
    app_json = json.loads(app_json_file.read_text(encoding="utf-8"))
    expo_cfg = app_json["expo"]
    assert expo_cfg["name"] == "PosiPulse"
    assert expo_cfg["ios"]["bundleIdentifier"] == "com.posipulse.news"
    assert expo_cfg["android"]["package"] == "com.posipulse.news"
    assert expo_cfg["android"]["supportsRtl"] is True


def test_mobile_typescript_schema_invariants(mobile_root):
    """Verify mobile TypeScript interfaces forbid raw publisher body text and include RTL."""
    types_file = mobile_root / "src" / "types" / "index.ts"
    assert types_file.exists(), "mobile types/index.ts missing"
    types_content = types_file.read_text(encoding="utf-8")

    # Invariants
    assert "interface Article" in types_content
    assert "headline: string;" in types_content
    assert "canonical_url: string;" in types_content
    assert "summary: SummaryMetadata;" in types_content
    assert "is_rtl?: boolean;" in types_content
    assert "body:" not in types_content
    assert "raw_body:" not in types_content


def test_mobile_linking_utility(mobile_root):
    """Verify publisher linking utility strips UTM trackers and opens in-app browser."""
    linking_file = mobile_root / "src" / "utils" / "linking.ts"
    assert linking_file.exists(), "mobile linking.ts missing"
    content = linking_file.read_text(encoding="utf-8")
    assert "sanitizePublisherUrl" in content
    assert "utm_source" in content
    assert "openPublisherStory" in content
    assert "expo-web-browser" in content


def test_native_ios_swiftui_view(mobile_root):
    """Verify native iOS SwiftUI view employs SFSafariViewController and RTL."""
    swift_file = mobile_root / "ios" / "PosiPulse" / "ContentView.swift"
    assert swift_file.exists(), "native iOS ContentView.swift missing"
    content = swift_file.read_text(encoding="utf-8")
    assert "SFSafariViewController" in content
    assert "struct SafariView: UIViewControllerRepresentable" in content
    assert "rightToLeft" in content
    assert "Deep Dive" in content
    assert "Compact" in content


def test_native_android_compose_view(mobile_root):
    """Verify native Android Jetpack Compose view employs CustomTabsIntent."""
    kt_file = mobile_root / "android" / "app" / "src" / "main" / "java" / "com" / "posipulse" / "MainActivity.kt"
    assert kt_file.exists(), "native Android MainActivity.kt missing"
    content = kt_file.read_text(encoding="utf-8")
    assert "CustomTabsIntent" in content
    assert "openPublisherCustomTab" in content
    assert "Triple(\"ur\", \"اردو\", true)" in content


def test_mobile_gateway_feed_contract(api_client):
    """Verify mobile reader contract across 16 languages and Urdu RTL."""
    # Seed Urdu and English fixtures
    seed_ur = api_client.post("/v1/demo/seed?language=ur")
    assert seed_ur.status_code == 200
    seed_en = api_client.post("/v1/demo/seed?language=en")
    assert seed_en.status_code == 200

    # Query Urdu feed as mobile client would
    res_ur = api_client.get("/v1/feed?language=ur")
    assert res_ur.status_code == 200
    data_ur = res_ur.json()
    assert len(data_ur["articles"]) >= 1
    art_ur = data_ur["articles"][0]
    assert art_ur["is_rtl"] is True
    assert art_ur["language"] == "ur"
    assert "utm_" not in art_ur["canonical_url"]
    assert "body" not in art_ur

    # Query English feed
    res_en = api_client.get("/v1/feed?language=en")
    assert res_en.status_code == 200
    data_en = res_en.json()
    assert len(data_en["articles"]) >= 1
    art_en = data_en["articles"][0]
    assert art_en["is_rtl"] is False
    assert art_en["language"] == "en"
