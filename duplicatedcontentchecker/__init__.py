"""Detect exact and near-duplicate content across the pages of a website."""

__version__ = "2.1.0"

from .checker import ContentDuplicateChecker  # noqa: E402
from .models import CrawlConfig, CrawlStats, DuplicatePair, Page, Report  # noqa: E402

__all__ = [
    "ContentDuplicateChecker",
    "CrawlConfig",
    "CrawlStats",
    "DuplicatePair",
    "Page",
    "Report",
    "__version__",
]
