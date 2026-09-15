"""URL normalization and scope helpers.

The original checker treated ``/about``, ``/about/`` and ``/about#team`` as three
different pages and reported them as duplicates of each other. Everything here
exists to avoid that class of false positive.
"""

from __future__ import annotations

import posixpath
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

# Query parameters that never change the page content.
TRACKING_PARAMS = frozenset(
    {
        "fbclid",
        "gclid",
        "dclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "yclid",
        "_ga",
        "_gl",
        "ref",
        "igshid",
    }
)
TRACKING_PREFIXES = ("utm_",)

# Extensions that are never HTML documents. Content-Type is still checked on
# fetch, but skipping these early saves a request.
NON_HTML_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".svg",
        ".ico",
        ".bmp",
        ".avif",
        ".mp3",
        ".mp4",
        ".m4a",
        ".wav",
        ".ogg",
        ".webm",
        ".mov",
        ".avi",
        ".zip",
        ".gz",
        ".tar",
        ".rar",
        ".7z",
        ".dmg",
        ".exe",
        ".msi",
        ".apk",
        ".css",
        ".js",
        ".mjs",
        ".json",
        ".xml",
        ".rss",
        ".atom",
        ".txt",
        ".csv",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".eot",
    }
)

_DEFAULT_PORTS = {"http": "80", "https": "443"}


def _is_tracking_param(name: str) -> bool:
    lowered = name.lower()
    return lowered in TRACKING_PARAMS or lowered.startswith(TRACKING_PREFIXES)


def normalize_url(url: str, base: str | None = None, *, strip_query: bool = False) -> str:
    """Return a canonical form of ``url`` so equivalent links compare equal.

    - resolves relative references against ``base``
    - lowercases scheme and host, drops default ports and ``www.`` is kept as-is
    - removes the fragment
    - collapses ``.``/``..`` segments and duplicate slashes
    - keeps a trailing slash: ``/about`` and ``/about/`` are different resources
      and relative links resolve differently from each of them. When a site
      serves both without redirecting, they are reported as an exact duplicate,
      which is a real finding.
    - drops known tracking parameters and sorts the rest (or drops the whole
      query when ``strip_query`` is true)
    """
    if base:
        url = urljoin(base, url)
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if not scheme or not host:
        return url.strip()
    port = parts.port
    netloc = host
    if port and str(port) != _DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{port}"

    raw_path = parts.path or "/"
    path = posixpath.normpath(raw_path)
    if not path.startswith("/"):
        path = "/" + path
    path = re.sub(r"/{2,}", "/", path)
    if raw_path.endswith("/") and not path.endswith("/"):
        path += "/"  # normpath drops it; put it back

    if strip_query:
        query = ""
    else:
        pairs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _is_tracking_param(k)]
        pairs.sort()
        query = urlencode(pairs, doseq=True)

    return urlunsplit((scheme, netloc, path, query, ""))


def registrable_host(host: str) -> str:
    """Strip a leading ``www.`` so ``www.example.com`` and ``example.com`` match."""
    host = host.lower()
    return host[4:] if host.startswith("www.") else host


def is_internal(url: str, base_url: str, *, include_subdomains: bool = False) -> bool:
    """True when ``url`` belongs to the same site as ``base_url``."""
    target = urlsplit(url)
    base = urlsplit(base_url)
    if target.scheme not in ("http", "https"):
        return False
    t_host = registrable_host(target.hostname or "")
    b_host = registrable_host(base.hostname or "")
    if not t_host or not b_host:
        return False
    if t_host == b_host:
        return True
    return include_subdomains and t_host.endswith("." + b_host)


def looks_like_html(url: str) -> bool:
    """Cheap pre-filter based on the path extension."""
    path = urlsplit(url).path.lower()
    _, ext = posixpath.splitext(path)
    return ext not in NON_HTML_EXTENSIONS


def matches_any(url: str, patterns: tuple[str, ...] | list[str]) -> bool:
    return any(re.search(p, url) for p in patterns)


def in_scope(url: str, include: tuple[str, ...], exclude: tuple[str, ...]) -> bool:
    """Apply include/exclude regex filters. Include wins only if non-empty."""
    if include and not matches_any(url, include):
        return False
    if exclude and matches_any(url, exclude):
        return False
    return True
