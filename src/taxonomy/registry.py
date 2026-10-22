"""
Taxonomy Registry and Feature Flag Management

Loads and validates versioned taxonomy configuration from config/taxonomy/v1.json.
Provides fail-closed lookup methods and feature-flagged runtime controls.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from src.taxonomy.models import Category, CategoryVisibility, Subcategory, TaxonomyVersion


# Feature flag key for news category taxonomy
ENV_FEATURE_FLAG = "POSIPULSE_ENABLE_CATEGORY_TAXONOMY_V1"


def is_category_taxonomy_enabled() -> bool:
    """
    Checks whether the Category Taxonomy v1 feature flag is enabled.
    Defaults to True. Can be disabled via POSIPULSE_ENABLE_CATEGORY_TAXONOMY_V1=false
    for zero-downtime rollback.
    """
    val = os.environ.get(ENV_FEATURE_FLAG, "true").strip().lower()
    return val not in ("false", "0", "no", "off")


class TaxonomyRegistry:
    """
    Thread-safe registry for the controlled news category taxonomy.
    Enforces strict immutability, ID uniqueness, and checksum verification.
    """

    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = Path(__file__).resolve().parent.parent.parent / "config" / "taxonomy" / "v1.json"
        self.config_path = config_path
        self._taxonomy: TaxonomyVersion = self._load_and_validate()
        self._categories_by_id: Dict[int, Category] = {c.id: c for c in self._taxonomy.categories}
        self._categories_by_slug: Dict[str, Category] = {c.slug: c for c in self._taxonomy.categories}
        self._subcategories_by_id: Dict[str, Subcategory] = {}
        for c in self._taxonomy.categories:
            for sub in c.subcategories:
                self._subcategories_by_id[sub.id] = sub

    def _load_and_validate(self) -> TaxonomyVersion:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Taxonomy configuration file not found at {self.config_path}")

        raw_content = self.config_path.read_text(encoding="utf-8")
        data = json.loads(raw_content)

        # Validate with Pydantic
        taxonomy = TaxonomyVersion.model_validate(data)

        # Integrity Checksum Verification
        canonical_repr = json.dumps([c.model_dump(mode="json") for c in taxonomy.categories], sort_keys=True, ensure_ascii=False)
        calculated_checksum = hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()

        if calculated_checksum != taxonomy.checksum:
            raise ValueError(
                f"Taxonomy integrity checksum mismatch! Expected {taxonomy.checksum}, calculated {calculated_checksum}. "
                "Any change to categories requires updating the checksum and bumping the taxonomy version."
            )

        # Invariant Validations
        self._validate_invariants(taxonomy)
        return taxonomy

    @staticmethod
    def _validate_invariants(taxonomy: TaxonomyVersion) -> None:
        category_ids = set()
        category_slugs = set()
        subcategory_ids = set()

        for cat in taxonomy.categories:
            if cat.id in category_ids:
                raise ValueError(f"Duplicate category ID {cat.id} detected.")
            category_ids.add(cat.id)

            if cat.slug in category_slugs:
                raise ValueError(f"Duplicate category slug '{cat.slug}' detected.")
            category_slugs.add(cat.slug)

            # Validate subcategory uniqueness
            for sub in cat.subcategories:
                if sub.id in subcategory_ids:
                    raise ValueError(f"Duplicate subcategory ID '{sub.id}' detected across taxonomy.")
                subcategory_ids.add(sub.id)

    @property
    def version(self) -> str:
        return self._taxonomy.version

    @property
    def effective_date(self) -> str:
        return self._taxonomy.effective_date

    def list_all(self) -> List[Category]:
        return list(self._taxonomy.categories)

    def list_visible(self) -> List[Category]:
        return [c for c in self._taxonomy.categories if c.visibility == CategoryVisibility.VISIBLE]

    def list_hidden(self) -> List[Category]:
        return [c for c in self._taxonomy.categories if c.visibility == CategoryVisibility.HIDDEN]

    def get_by_id(self, category_id: int) -> Optional[Category]:
        return self._categories_by_id.get(category_id)

    def get_by_slug(self, slug: str) -> Optional[Category]:
        return self._categories_by_slug.get(slug)

    def get_subcategory(self, subcategory_id: str) -> Optional[Subcategory]:
        return self._subcategories_by_id.get(subcategory_id)

    def is_hidden(self, category_id: int) -> bool:
        cat = self.get_by_id(category_id)
        if not cat:
            return True  # Unknown categories fail closed as hidden
        return cat.visibility == CategoryVisibility.HIDDEN

    def get_display_name(self, category_id: int, language_code: str) -> str:
        cat = self.get_by_id(category_id)
        if not cat:
            return "Unknown"
        # Fallback to English if language code is not mapped
        return cat.display_names.get(language_code) or cat.display_names.get("en", "Unknown")


_default_registry: Optional[TaxonomyRegistry] = None


def get_taxonomy_registry() -> TaxonomyRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = TaxonomyRegistry()
    return _default_registry


def __getattr__(name: str):
    if name == "default_taxonomy_registry":
        return get_taxonomy_registry()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
