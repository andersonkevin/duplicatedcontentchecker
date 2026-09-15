"""Data structures shared across the crawler, analyzer and reporters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

DEFAULT_USER_AGENT = "DuplicatedContentChecker/2.0 (+https://github.com/andersonkevin/duplicatedcontentchecker)"


@dataclass(slots=True)
class CrawlConfig:
    """Everything that controls how a site is crawled and compared."""

    base_url: str
    max_depth: int = 2
    max_pages: int = 500
    threshold: float = 0.8
    min_words: int = 50
    delay: float = 0.0
    timeout: float = 15.0
    retries: int = 2
    user_agent: str = DEFAULT_USER_AGENT
    respect_robots: bool = True
    include_subdomains: bool = False
    include_patterns: tuple[str, ...] = ()
    exclude_patterns: tuple[str, ...] = ()
    use_sitemap: bool = False
    full_page: bool = False
    strip_query: bool = False

    def __post_init__(self) -> None:
        scheme = self.base_url.split("://", 1)[0].lower() if "://" in (self.base_url or "") else ""
        if scheme == "http":
            raise ValueError("base_url must use https; plain-http sites are not scanned")
        if scheme != "https":
            raise ValueError("base_url must be an absolute https URL")
        if self.max_depth < 0:
            raise ValueError("max_depth must be >= 0")
        if self.max_pages < 1:
            raise ValueError("max_pages must be >= 1")
        if not 0.0 < self.threshold <= 1.0:
            raise ValueError("threshold must be in (0, 1]")
        if self.min_words < 0:
            raise ValueError("min_words must be >= 0")
        if self.delay < 0:
            raise ValueError("delay must be >= 0")


@dataclass(slots=True)
class FetchResult:
    """A successful HTTP response that looks like an HTML document."""

    url: str
    final_url: str
    status: int
    html: str
    content_type: str = "text/html"


@dataclass(slots=True)
class Page:
    """Content extracted from a single crawled page."""

    url: str
    depth: int
    title: str = ""
    h1: str = ""
    text: str = ""
    word_count: int = 0
    canonical: str | None = None
    noindex: bool = False
    language: str | None = None
    content_hash: str = ""
    status: int = 200

    @property
    def is_thin(self) -> bool:
        return self.word_count == 0


DuplicateKind = Literal["exact", "near"]


@dataclass(slots=True)
class DuplicatePair:
    """Two pages whose content is identical or highly similar."""

    url_1: str
    url_2: str
    similarity: float
    kind: DuplicateKind
    canonicalized: bool = False
    noindex: bool = False

    @property
    def note(self) -> str:
        notes: list[str] = []
        if self.canonicalized:
            notes.append("canonical points to the other page")
        if self.noindex:
            notes.append("at least one page is noindex")
        return "; ".join(notes)


@dataclass(slots=True)
class CrawlStats:
    """Counters gathered during the crawl."""

    fetched: int = 0
    skipped_robots: int = 0
    skipped_pattern: int = 0
    skipped_non_html: int = 0
    skipped_http: int = 0
    failed: int = 0
    duplicates_of_visited: int = 0
    seeded_from_sitemap: int = 0


@dataclass(slots=True)
class Report:
    """Result of a full run."""

    base_url: str
    pages: list[Page]
    pairs: list[DuplicatePair]
    stats: CrawlStats
    config: CrawlConfig
    thin_pages: list[Page] = field(default_factory=list)

    @property
    def exact_pairs(self) -> list[DuplicatePair]:
        return [p for p in self.pairs if p.kind == "exact"]

    @property
    def near_pairs(self) -> list[DuplicatePair]:
        return [p for p in self.pairs if p.kind == "near"]
