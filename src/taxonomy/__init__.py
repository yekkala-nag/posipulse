"""
News Category Taxonomy Package (Version 1)
"""

from src.taxonomy.models import (
    Category,
    CategoryVisibility,
    IPTCReference,
    PositiveFitRating,
    SpecialRuleFlags,
    Subcategory,
    TaxonomyVersion,
)
from src.taxonomy.registry import (
    TaxonomyRegistry,
    get_taxonomy_registry,
    is_category_taxonomy_enabled,
)

__all__ = [
    "Category",
    "CategoryVisibility",
    "IPTCReference",
    "PositiveFitRating",
    "SpecialRuleFlags",
    "Subcategory",
    "TaxonomyVersion",
    "TaxonomyRegistry",
    "get_taxonomy_registry",
    "default_taxonomy_registry",
    "is_category_taxonomy_enabled",
]


def __getattr__(name: str):
    if name == "default_taxonomy_registry":
        return get_taxonomy_registry()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
