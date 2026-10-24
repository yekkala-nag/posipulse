"""
Publisher feed ingestion and compliance validation module.
"""

def __getattr__(name: str):
    if name in ("FeedValidator", "FeedValidationResult", "FeedValidationIssue", "ValidationSeverity"):
        from src.ingestion.validator import FeedValidator, FeedValidationResult, FeedValidationIssue, ValidationSeverity
        return locals()[name]
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = ["FeedValidator", "FeedValidationResult", "FeedValidationIssue", "ValidationSeverity"]
