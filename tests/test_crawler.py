from duplicatedcontentchecker.crawler import Crawler
from duplicatedcontentchecker.models import CrawlConfig

from .conftest import LOREM_A, LOREM_B, FakeFetcher, page


def test_crawl_normalizes_and_stays_internal(simple_site):
    fetcher = FakeFetcher(simple_site)
    crawler = Crawler(CrawlConfig("https://example.com", max_depth=3), fetcher)
    pages = crawler.crawl()
    urls = sorted(p.url for p in pages)
    assert urls == sorted(simple_site.keys())
    # /about, /about#team and /about?utm_source=... collapsed into one fetch
    assert fetcher.requested.count("https://example.com/about") == 1
    assert not any("other.example.org" in u for u in fetcher.requested)
    assert not any(u.endswith(".pdf") for u in fetcher.requested)
    assert crawler.stats.skipped_non_html >= 1
    assert crawler.stats.fetched == len(simple_site)


def test_max_depth_limits_discovery(simple_site):
    fetcher = FakeFetcher(simple_site)
    pages = Crawler(CrawlConfig("https://example.com", max_depth=0), fetcher).crawl()
    assert [p.url for p in pages] == ["https://example.com/"]


def test_max_pages_stops_early(simple_site):
    fetcher = FakeFetcher(simple_site)
    pages = Crawler(CrawlConfig("https://example.com", max_depth=5, max_pages=3), fetcher).crawl()
    assert len(pages) == 3


def test_robots_blocking_is_counted(simple_site):
    fetcher = FakeFetcher(simple_site, blocked={"https://example.com/contact"})
    crawler = Crawler(CrawlConfig("https://example.com", max_depth=3), fetcher)
    pages = crawler.crawl()
    assert "https://example.com/contact" not in {p.url for p in pages}
    assert crawler.stats.skipped_robots == 1


def test_include_exclude_patterns(simple_site):
    fetcher = FakeFetcher(simple_site)
    cfg = CrawlConfig("https://example.com", max_depth=3, exclude_patterns=(r"/blog/",))
    pages = Crawler(cfg, fetcher).crawl()
    assert not any("/blog/" in p.url for p in pages)
    cfg = CrawlConfig("https://example.com", max_depth=3, include_patterns=(r"^https://example\.com/?$", r"/blog/"))
    pages = Crawler(cfg, fetcher).crawl()
    assert {p.url for p in pages} == {
        "https://example.com/",
        "https://example.com/blog/post-1",
        "https://example.com/blog/post-1-copy",
    }


def test_redirects_index_final_url():
    site = {
        "https://example.com/": page("Home", LOREM_A, links=["/old", "/new"]),
        "https://example.com/new": page("New", LOREM_B),
    }
    fetcher = FakeFetcher(site, redirects={"https://example.com/old": "https://example.com/new"})
    crawler = Crawler(CrawlConfig("https://example.com", max_depth=2), fetcher)
    pages = crawler.crawl()
    assert sorted(p.url for p in pages) == ["https://example.com/", "https://example.com/new"]
    assert fetcher.requested.count("https://example.com/new") <= 1


def test_sitemap_seeding():
    site = {
        "https://example.com/": page("Home", LOREM_A),
        "https://example.com/orphan": page("Orphan", LOREM_B),
    }
    sitemap_index = (
        '<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<sitemap><loc>https://example.com/pages.xml</loc></sitemap></sitemapindex>"
    )
    pages_xml = (
        '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://example.com/orphan#top</loc></url>"
        "<url><loc>https://example.com/brochure.pdf</loc></url>"
        "<url><loc>https://elsewhere.org/x</loc></url></urlset>"
    )
    fetcher = FakeFetcher(
        site, texts={"https://example.com/sitemap.xml": sitemap_index, "https://example.com/pages.xml": pages_xml}
    )
    crawler = Crawler(CrawlConfig("https://example.com", max_depth=0, use_sitemap=True), fetcher)
    pages = crawler.crawl()
    assert sorted(p.url for p in pages) == ["https://example.com/", "https://example.com/orphan"]
    assert crawler.stats.seeded_from_sitemap == 1


def test_relative_links_resolve_against_served_url():
    """A start URL like /docs/ must resolve href="page.html" to /docs/page.html."""
    site = {
        "https://example.com/docs/": page("Docs", LOREM_A, links=["page.html", "../top"], with_chrome=False),
        "https://example.com/docs/page.html": page("Page", LOREM_B, with_chrome=False),
        "https://example.com/top": page("Top", LOREM_B + " More words about the top page.", with_chrome=False),
    }
    fetcher = FakeFetcher(site)
    crawler = Crawler(CrawlConfig("https://example.com/docs/", max_depth=1), fetcher)
    pages = crawler.crawl()
    assert sorted(p.url for p in pages) == sorted(site)
    assert crawler.stats.failed == 0


def test_trailing_slash_variants_are_reported_not_merged():
    """If a site serves /a and /a/ with the same content, that is a real duplicate."""
    site = {
        "https://example.com/": page("Home", LOREM_A, links=["/a", "/a/"]),
        "https://example.com/a": page("A", LOREM_B),
        "https://example.com/a/": page("A", LOREM_B),
    }
    pages = Crawler(CrawlConfig("https://example.com", max_depth=1), FakeFetcher(site)).crawl()
    assert sorted(p.url for p in pages) == sorted(site)
