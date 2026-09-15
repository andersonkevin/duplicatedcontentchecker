"""Turn raw HTML into the text that should be compared.

The v1 checker compared the whole page, including navigation, header and footer.
On most sites that shared chrome alone pushes unrelated pages past a 0.7
similarity threshold. Here we prefer ``<main>``/``<article>`` and drop the
boilerplate elements before extracting text.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .models import Page
from .urlutils import normalize_url

# Elements that never carry primary content.
NOISE_TAGS = (
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "canvas",
    "iframe",
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    "button",
    "select",
    "option",
)
# Common class/id fragments used for site chrome. Matched case-insensitively.
NOISE_HINTS = re.compile(
    r"(^|[-_ ])(nav|navbar|menu|sidebar|footer|header|cookie|breadcrumb|banner|"
    r"advert|ads|share|social|related|comments?)([-_ ]|$)",
    re.IGNORECASE,
)

_WS = re.compile(r"\s+")


def _clean_text(text: str) -> str:
    return _WS.sub(" ", text).strip()


def _hash_text(text: str) -> str:
    """Hash of the text with case and whitespace folded, so cosmetic diffs match."""
    folded = _WS.sub(" ", text).strip().lower()
    return hashlib.sha256(folded.encode("utf-8")).hexdigest()


def _has_noise_hint(tag) -> bool:
    attrs = tag.attrs or {}
    candidates: list[str] = []
    for key in ("id", "class", "role"):
        value = attrs.get(key)
        if isinstance(value, list):
            candidates.extend(value)
        elif isinstance(value, str):
            candidates.append(value)
    return any(NOISE_HINTS.search(c) for c in candidates)


def extract_page(html: str, url: str, depth: int = 0, *, full_page: bool = False) -> Page:
    """Build a :class:`Page` from ``html``.

    ``full_page=True`` restores v1 behaviour (everything except script/style).
    """
    soup = BeautifulSoup(html, "html.parser")

    title = _clean_text(soup.title.get_text()) if soup.title else ""
    h1_tag = soup.find("h1")
    h1 = _clean_text(h1_tag.get_text()) if h1_tag else ""

    canonical: str | None = None
    for link in soup.find_all("link", href=True):
        rel = link.get("rel") or []
        rel_values = rel if isinstance(rel, list) else [rel]
        if any(str(r).lower() == "canonical" for r in rel_values):
            canonical = normalize_url(link["href"], base=url)
            break

    noindex = False
    for meta in soup.find_all("meta"):
        name = (meta.get("name") or "").lower()
        if name in ("robots", "googlebot"):
            content = (meta.get("content") or "").lower()
            if "noindex" in content:
                noindex = True
                break

    language: str | None = None
    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        language = str(html_tag["lang"]).strip() or None

    if full_page:
        for tag in soup(["script", "style", "noscript", "template"]):
            tag.decompose()
        root = soup.body or soup
    else:
        for tag in soup(NOISE_TAGS):
            tag.decompose()
        for tag in soup.find_all(True):
            if tag.name in ("div", "section", "ul", "ol", "p", "span") and _has_noise_hint(tag):
                tag.decompose()
        root = soup.find("main") or soup.find("article") or soup.body or soup

    text = _clean_text(" ".join(root.stripped_strings)) if root else ""
    word_count = len(text.split()) if text else 0

    return Page(
        url=url,
        depth=depth,
        title=title,
        h1=h1,
        text=text,
        word_count=word_count,
        canonical=canonical,
        noindex=noindex,
        language=language,
        content_hash=_hash_text(text) if text else "",
    )


def extract_links(html: str, base_url: str) -> list[str]:
    """All ``<a href>`` targets resolved against ``base_url``.

    Links carrying ``rel="nofollow"`` are still returned; scope filtering is the
    crawler's job. ``mailto:``, ``tel:`` and ``javascript:`` are dropped here.
    """
    soup = BeautifulSoup(html, "html.parser")
    base_tag = soup.find("base", href=True)
    # Keep the raw <base href> (trailing slash matters for relative resolution).
    effective_base = urljoin(base_url, base_tag["href"].strip()) if base_tag else base_url
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue
        links.append(normalize_url(href, base=effective_base))
    return links
