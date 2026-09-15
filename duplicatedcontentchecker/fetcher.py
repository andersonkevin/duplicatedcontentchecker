"""HTTP layer: a polite session with timeouts, retries and robots.txt support."""

from __future__ import annotations

import logging
import time
from typing import Protocol
from urllib import robotparser
from urllib.parse import urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import DEFAULT_USER_AGENT, FetchResult

log = logging.getLogger(__name__)

HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")


class Fetcher(Protocol):
    """Anything the crawler can pull pages from. Tests inject a fake."""

    def fetch(self, url: str) -> FetchResult | None: ...

    def allowed(self, url: str) -> bool: ...

    def fetch_text(self, url: str) -> str | None: ...


class HttpFetcher:
    """requests-based fetcher used in production."""

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = 15.0,
        retries: int = 2,
        delay: float = 0.0,
        respect_robots: bool = True,
        max_bytes: int = 5_000_000,
    ) -> None:
        self.timeout = timeout
        self.delay = delay
        self.respect_robots = respect_robots
        self.max_bytes = max_bytes
        self.user_agent = user_agent
        self._last_request = 0.0
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
                "Accept-Language": "en,*;q=0.5",
            }
        )
        retry = Retry(
            total=retries,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    # -- politeness -------------------------------------------------------

    def _throttle(self) -> None:
        if self.delay <= 0:
            return
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def _robots_for(self, url: str) -> robotparser.RobotFileParser | None:
        parts = urlsplit(url)
        origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        if origin in self._robots:
            return self._robots[origin]
        parser = robotparser.RobotFileParser()
        robots_url = origin + "/robots.txt"
        try:
            self._throttle()
            resp = self.session.get(robots_url, timeout=self.timeout)
            self._last_request = time.monotonic()
            if resp.status_code == 200:
                parser.parse(resp.text.splitlines())
            elif 400 <= resp.status_code < 500:
                parser.allow_all = True
            else:
                # Server error: be conservative and allow, but log it.
                log.warning("robots.txt returned %s for %s; assuming allow", resp.status_code, origin)
                parser.allow_all = True
        except requests.RequestException as exc:
            log.warning("Could not read %s (%s); assuming allow", robots_url, exc)
            parser.allow_all = True
        self._robots[origin] = parser
        return parser

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parser = self._robots_for(url)
        return parser is None or parser.can_fetch(self.user_agent, url)

    def sitemaps_from_robots(self, url: str) -> list[str]:
        """Sitemap URLs declared in robots.txt, if any."""
        parser = self._robots_for(url)
        if parser is None:
            return []
        return list(parser.site_maps() or [])

    # -- fetching ---------------------------------------------------------

    def fetch_text(self, url: str) -> str | None:
        """Fetch any text resource (used for sitemaps). No content-type check."""
        try:
            self._throttle()
            resp = self.session.get(url, timeout=self.timeout)
            self._last_request = time.monotonic()
        except requests.RequestException as exc:
            log.warning("Failed to fetch %s: %s", url, exc)
            return None
        if resp.status_code != 200:
            log.debug("%s returned %s", url, resp.status_code)
            return None
        return resp.text

    def fetch(self, url: str) -> FetchResult | None:
        """Fetch an HTML page. Returns None for errors and non-HTML responses."""
        try:
            self._throttle()
            resp = self.session.get(url, timeout=self.timeout, stream=True)
            self._last_request = time.monotonic()
            content_type = resp.headers.get("Content-Type", "").lower()
            if resp.status_code != 200:
                log.warning("%s returned HTTP %s", url, resp.status_code)
                resp.close()
                return None
            if not content_type.startswith(HTML_CONTENT_TYPES):
                log.debug("Skipping %s: content-type %s", url, content_type or "unknown")
                resp.close()
                return None
            body = resp.raw.read(self.max_bytes, decode_content=True)
            resp.close()
            encoding = resp.encoding or "utf-8"
            try:
                html = body.decode(encoding, errors="replace")
            except LookupError:
                html = body.decode("utf-8", errors="replace")
            return FetchResult(
                url=url,
                final_url=resp.url,
                status=resp.status_code,
                html=html,
                content_type=content_type,
            )
        except requests.RequestException as exc:
            log.warning("Failed to fetch %s: %s", url, exc)
            return None
