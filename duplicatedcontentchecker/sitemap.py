"""Discover URLs from sitemap.xml and sitemap index files."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit, urlunsplit

from .fetcher import Fetcher

log = logging.getLogger(__name__)

MAX_SITEMAPS = 50


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_sitemap(xml_text: str) -> tuple[list[str], list[str]]:
    """Return ``(page_urls, nested_sitemap_urls)`` from a sitemap document."""
    pages: list[str] = []
    nested: list[str] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.warning("Could not parse sitemap: %s", exc)
        return pages, nested
    kind = _local(root.tag)
    for node in root:
        if _local(node.tag) not in ("url", "sitemap"):
            continue
        loc = next((c.text for c in node if _local(c.tag) == "loc" and c.text), None)
        if not loc:
            continue
        loc = loc.strip()
        if kind == "sitemapindex":
            nested.append(loc)
        else:
            pages.append(loc)
    return pages, nested


def discover_sitemap_urls(fetcher: Fetcher, base_url: str, extra: list[str] | None = None) -> list[str]:
    """Collect page URLs from ``/sitemap.xml`` plus any sitemaps in ``extra``."""
    parts = urlsplit(base_url)
    origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    queue = [origin + "/sitemap.xml", origin + "/sitemap_index.xml"]
    if extra:
        queue.extend(extra)

    seen: set[str] = set()
    found: list[str] = []
    while queue and len(seen) < MAX_SITEMAPS:
        sm_url = queue.pop(0)
        if sm_url in seen:
            continue
        seen.add(sm_url)
        text = fetcher.fetch_text(sm_url)
        if not text:
            continue
        pages, nested = parse_sitemap(text)
        log.info("Sitemap %s: %d urls, %d nested sitemaps", sm_url, len(pages), len(nested))
        found.extend(pages)
        queue.extend(nested)
    return found
