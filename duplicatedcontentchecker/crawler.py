"""Breadth-first site crawler bounded by depth, page count and scope rules."""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable

from .extractor import extract_links, extract_page
from .fetcher import Fetcher, HttpFetcher
from .models import CrawlConfig, CrawlStats, Page
from .sitemap import discover_sitemap_urls
from .urlutils import in_scope, is_internal, looks_like_html, normalize_url

log = logging.getLogger(__name__)


class Crawler:
    """Collects :class:`Page` objects from a site.

    The original implementation recursed depth-first with no page limit, which
    could blow the recursion limit on a large site. This version walks
    breadth-first so shallow pages are always visited first, and stops at
    ``max_pages`` regardless of depth.
    """

    def __init__(
        self,
        config: CrawlConfig,
        fetcher: Fetcher | None = None,
        *,
        should_stop: Callable[[], bool] | None = None,
    ) -> None:
        self.config = config
        self.should_stop = should_stop
        self.queued_count = 0
        self.stopped_early = False
        self.fetcher = fetcher or HttpFetcher(
            user_agent=config.user_agent,
            timeout=config.timeout,
            retries=config.retries,
            delay=config.delay,
            respect_robots=config.respect_robots,
        )
        self.stats = CrawlStats()
        self.pages: dict[str, Page] = {}
        self.visited: set[str] = set()

    # -- scope ------------------------------------------------------------

    def _norm(self, url: str, base: str | None = None) -> str:
        return normalize_url(url, base=base, strip_query=self.config.strip_query)

    def _accept(self, url: str) -> bool:
        cfg = self.config
        if not is_internal(url, cfg.base_url, include_subdomains=cfg.include_subdomains):
            return False
        if not looks_like_html(url):
            self.stats.skipped_non_html += 1
            return False
        if not in_scope(url, cfg.include_patterns, cfg.exclude_patterns):
            self.stats.skipped_pattern += 1
            return False
        return True

    # -- main loop --------------------------------------------------------

    def _seeds(self) -> list[tuple[str, int]]:
        start = self._norm(self.config.base_url)
        seeds: list[tuple[str, int]] = [(start, 0)]
        if self.config.use_sitemap:
            extra: list[str] = []
            sitemaps_from_robots = getattr(self.fetcher, "sitemaps_from_robots", None)
            if callable(sitemaps_from_robots):
                extra = list(sitemaps_from_robots(start))
            for raw in discover_sitemap_urls(self.fetcher, start, extra):
                url = self._norm(raw)
                if url != start and self._accept(url):
                    seeds.append((url, 1))
                    self.stats.seeded_from_sitemap += 1
        return seeds

    def crawl(self) -> list[Page]:
        cfg = self.config
        queue: deque[tuple[str, int]] = deque()
        queued: set[str] = set()
        for url, depth in self._seeds():
            if url not in queued:
                queue.append((url, depth))
                queued.add(url)

        while queue and len(self.pages) < cfg.max_pages:
            if self.should_stop is not None and self.should_stop():
                log.info("Crawl canceled after %d pages", len(self.pages))
                self.stopped_early = True
                break
            self.queued_count = len(queue)
            url, depth = queue.popleft()
            if url in self.visited:
                self.stats.duplicates_of_visited += 1
                continue
            self.visited.add(url)

            if not self.fetcher.allowed(url):
                log.info("Blocked by robots.txt: %s", url)
                self.stats.skipped_robots += 1
                continue

            log.info("Fetching (depth %d, %d/%d): %s", depth, len(self.pages) + 1, cfg.max_pages, url)
            result = self.fetcher.fetch(url)
            if result is None:
                self.stats.failed += 1
                continue
            self.stats.fetched += 1

            # Follow redirects: index the page under its final URL. Relative
            # links are resolved against the URL the server actually served,
            # because a trailing slash changes how ``href="page.html"`` resolves.
            served = result.final_url or url
            final = self._norm(served)
            if final != url:
                self.visited.add(final)
                if final in self.pages:
                    self.stats.duplicates_of_visited += 1
                    continue
                if not self._accept(final):
                    continue

            page = extract_page(result.html, final, depth, full_page=cfg.full_page)
            page.status = result.status
            self.pages[final] = page

            if depth >= cfg.max_depth:
                continue
            for link in extract_links(result.html, served):
                link = self._norm(link)
                if link in queued or link in self.visited:
                    continue
                if not self._accept(link):
                    continue
                queued.add(link)
                queue.append((link, depth + 1))

        self.queued_count = len(queue)
        if queue and not self.stopped_early:
            log.info("Stopped at max_pages=%d with %d urls still queued", cfg.max_pages, len(queue))
        return list(self.pages.values())
