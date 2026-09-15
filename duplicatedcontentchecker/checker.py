"""High-level facade. Keeps the v1 ``ContentDuplicateChecker`` API working."""

from __future__ import annotations

import logging
from pathlib import Path

from .analyzer import analyze
from .crawler import Crawler
from .fetcher import Fetcher
from .models import CrawlConfig, CrawlStats, DuplicatePair, Page, Report
from .report import write_csv, write_json

log = logging.getLogger(__name__)


class ContentDuplicateChecker:
    """Crawl a site and report duplicate content.

    Backwards compatible with v1::

        checker = ContentDuplicateChecker(base_url="https://example.com", max_depth=2)
        checker.run()                      # writes duplicate_report.csv

    New code should prefer :meth:`run_report` or pass a :class:`CrawlConfig`::

        checker = ContentDuplicateChecker(config=CrawlConfig("https://example.com", threshold=0.85))
        report = checker.run_report()
    """

    def __init__(
        self,
        base_url: str | None = None,
        max_depth: int = 2,
        *,
        config: CrawlConfig | None = None,
        fetcher: Fetcher | None = None,
        **overrides,
    ) -> None:
        if config is None:
            if base_url is None:
                raise TypeError("base_url or config is required")
            config = CrawlConfig(base_url=base_url, max_depth=max_depth, **overrides)
        elif base_url is not None or overrides:
            raise TypeError("pass either config or base_url/overrides, not both")
        self.config = config
        self._fetcher = fetcher
        self.report: Report | None = None

        # v1 attributes, populated by crawl()/compare_contents().
        self.base_url = config.base_url
        self.max_depth = config.max_depth
        self.visited_urls: set[str] = set()
        self.content_hashes: dict[str, str] = {}
        self.content_texts: dict[str, str] = {}
        self.similarity_scores: list[tuple[str, str, float]] = []
        self._pages: list[Page] = []
        self._pairs: list[DuplicatePair] = []
        self._thin: list[Page] = []
        self._stats = CrawlStats()

    # -- v1-compatible steps ---------------------------------------------

    def crawl(self, url: str | None = None, depth: int = 0) -> list[Page]:
        """Crawl the site. ``url``/``depth`` are accepted for v1 compatibility
        but the crawl always starts at the configured base URL."""
        if url is not None and url != self.config.base_url:
            log.warning("crawl(url=...) is ignored; crawling configured base_url %s", self.config.base_url)
        crawler = Crawler(self.config, fetcher=self._fetcher)
        self._pages = crawler.crawl()
        self._stats = crawler.stats
        self.visited_urls = set(crawler.visited)
        self.content_hashes = {p.url: p.content_hash for p in self._pages if p.content_hash}
        self.content_texts = {p.url: p.text for p in self._pages if p.text}
        return self._pages

    def compare_contents(self) -> list[DuplicatePair]:
        if not self._pages:
            log.warning("No content available for comparison.")
            self._pairs, self._thin = [], []
        else:
            self._pairs, self._thin = analyze(self._pages, self.config.threshold, self.config.min_words)
        self.similarity_scores = [(p.url_1, p.url_2, p.similarity) for p in self._pairs]
        self.report = Report(
            base_url=self.config.base_url,
            pages=self._pages,
            pairs=self._pairs,
            stats=self._stats,
            config=self.config,
            thin_pages=self._thin,
        )
        return self._pairs

    def generate_report(
        self, output_path: str | Path = "duplicate_report.csv", json_path: str | Path | None = None
    ) -> Path:
        if self.report is None:
            self.compare_contents()
        assert self.report is not None
        path = write_csv(self.report, output_path)
        log.info("Report generated: %s", path)
        if json_path:
            write_json(self.report, json_path)
            log.info("JSON report generated: %s", json_path)
        return path

    def run(self, output_path: str | Path = "duplicate_report.csv") -> Path:
        """v1 entry point: crawl, compare and write the CSV."""
        self.crawl()
        self.compare_contents()
        return self.generate_report(output_path)

    # -- modern entry point ---------------------------------------------

    def run_report(self) -> Report:
        """Crawl and compare without writing anything to disk."""
        self.crawl()
        self.compare_contents()
        assert self.report is not None
        return self.report
