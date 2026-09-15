"""Shared fixtures. Nothing here touches the network."""

from __future__ import annotations

import pytest

from duplicatedcontentchecker.models import FetchResult


class FakeFetcher:
    """In-memory site. Keys are normalized URLs, values are HTML strings.

    ``blocked`` simulates robots.txt disallow rules. ``redirects`` maps a
    requested URL to the URL it lands on. ``texts`` serves non-HTML resources
    such as sitemaps.
    """

    def __init__(
        self,
        pages: dict[str, str],
        *,
        blocked: set[str] | None = None,
        redirects: dict[str, str] | None = None,
        texts: dict[str, str] | None = None,
    ) -> None:
        self.pages = pages
        self.blocked = blocked or set()
        self.redirects = redirects or {}
        self.texts = texts or {}
        self.requested: list[str] = []

    def allowed(self, url: str) -> bool:
        return url not in self.blocked

    def fetch(self, url: str) -> FetchResult | None:
        self.requested.append(url)
        final = self.redirects.get(url, url)
        html = self.pages.get(final)
        if html is None:
            return None
        return FetchResult(url=url, final_url=final, status=200, html=html)

    def fetch_text(self, url: str) -> str | None:
        self.requested.append(url)
        return self.texts.get(url)


def page(
    title: str,
    body: str,
    *,
    links: list[str] = (),
    canonical: str | None = None,
    noindex: bool = False,
    with_chrome: bool = True,
) -> str:
    """Build a small but realistic HTML document."""
    head = f"<title>{title}</title>"
    if canonical:
        head += f'<link rel="canonical" href="{canonical}">'
    if noindex:
        head += '<meta name="robots" content="noindex, follow">'
    nav = ""
    footer = ""
    if with_chrome:
        nav = '<nav><a href="/">Home</a><a href="/about">About</a><a href="/contact">Contact</a></nav>'
        footer = "<footer>Copyright Example Inc. All rights reserved. Privacy Terms Sitemap</footer>"
    anchors = "".join(f'<a href="{href}">link</a>' for href in links)
    return (
        f'<!doctype html><html lang="en"><head>{head}</head><body>'
        f"{nav}<main><h1>{title}</h1><p>{body}</p>{anchors}</main>{footer}</body></html>"
    )


LOREM_A = (
    "Search engines reward pages that answer a single question thoroughly. "
    "When several URLs on the same site repeat the same paragraphs, ranking "
    "signals split between them and none of the copies performs well. "
    "Consolidate the copies with redirects or canonical tags, then rewrite "
    "what remains so each page has a distinct purpose and audience."
) * 2

LOREM_B = (
    "Product photography guides usually cover lighting, background choice and "
    "lens selection. Shoot on a neutral surface, diffuse the key light, and "
    "keep the camera level with the subject. Export at the size the storefront "
    "actually displays so the browser does not have to scale the image."
) * 2


@pytest.fixture
def simple_site() -> dict[str, str]:
    return {
        "https://example.com/": page(
            "Home",
            LOREM_A[:300] + " Welcome to the home page of Example.",
            links=[
                "/about",
                "/blog/post-1",
                "/blog/post-1-copy",
                "/photo",
                "/short",
                "/file.pdf",
                "https://other.example.org/x",
                "/about#team",
                "/about?utm_source=newsletter&fbclid=abc",
            ],
        ),
        "https://example.com/about": page("About", LOREM_B, links=["/contact"]),
        "https://example.com/contact": page("Contact", "Email us at hello@example.com. " * 30),
        "https://example.com/blog/post-1": page("Post one", LOREM_A),
        "https://example.com/blog/post-1-copy": page("Post one", LOREM_A),
        "https://example.com/photo": page("Photo", LOREM_B + " Additional sentence about tripods and stands."),
        "https://example.com/short": page("Short", "Tiny page."),
    }
