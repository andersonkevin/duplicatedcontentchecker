from duplicatedcontentchecker import ContentDuplicateChecker, CrawlConfig
from duplicatedcontentchecker.actions import build_clusters, recommend
from duplicatedcontentchecker.extractor import extract_page
from duplicatedcontentchecker.models import CrawlStats, DuplicatePair, Report

from .conftest import LOREM_A, LOREM_B, FakeFetcher, page


def _page(url, body, depth=1, **kw):
    p = extract_page(page("Same title", body, **kw), url, depth)
    return p


def _report(pages, pairs, thin=None, **cfg):
    config = CrawlConfig("https://e.com", **cfg)
    return Report("https://e.com", pages, pairs, CrawlStats(), config, thin or [])


def test_cluster_picks_canonical_target_then_shallowest_then_shortest():
    pages = [
        _page("https://e.com/long-url-variant", LOREM_A, depth=1, canonical="https://e.com/a"),
        _page("https://e.com/a", LOREM_A, depth=2),
        _page("https://e.com/b", LOREM_A, depth=1),
    ]
    pairs = [
        DuplicatePair("https://e.com/a", "https://e.com/long-url-variant", 1.0, "exact", canonicalized=True),
        DuplicatePair("https://e.com/a", "https://e.com/b", 1.0, "exact"),
        DuplicatePair("https://e.com/b", "https://e.com/long-url-variant", 1.0, "exact"),
    ]
    clusters = build_clusters(pages, pairs)
    assert len(clusters) == 1
    c = clusters[0]
    assert c.primary == "https://e.com/a"  # canonical target wins over depth
    assert c.members == ["https://e.com/a", "https://e.com/b", "https://e.com/long-url-variant"]
    assert c.kind == "exact" and c.min_similarity == 1.0
    assert c.duplicates == ["https://e.com/b", "https://e.com/long-url-variant"]

    # Without canonical votes: shallower page wins, then shorter URL.
    pages2 = [
        _page("https://e.com/deep", LOREM_A, depth=3),
        _page("https://e.com/x", LOREM_A, depth=1),
        _page("https://e.com/y", LOREM_A, depth=1),
    ]
    pairs2 = [
        DuplicatePair("https://e.com/deep", "https://e.com/x", 1.0, "exact"),
        DuplicatePair("https://e.com/x", "https://e.com/y", 1.0, "exact"),
    ]
    assert build_clusters(pages2, pairs2)[0].primary == "https://e.com/x"


def test_recommend_one_action_per_duplicate_url():
    pages = [
        _page("https://e.com/a", LOREM_A),
        _page("https://e.com/a-copy", LOREM_A),
        _page("https://e.com/b", LOREM_B),
        _page("https://e.com/b-near", LOREM_B),
        _page("https://e.com/c", LOREM_B),
        _page("https://e.com/c-canon", LOREM_B, canonical="https://e.com/c"),
        _page("https://e.com/d", LOREM_A),
        _page("https://e.com/d-noindex", LOREM_A, noindex=True),
    ]
    pairs = [
        DuplicatePair("https://e.com/a", "https://e.com/a-copy", 1.0, "exact"),
        DuplicatePair("https://e.com/b", "https://e.com/b-near", 0.97, "near"),
        DuplicatePair("https://e.com/b", "https://e.com/c", 0.85, "near"),
        DuplicatePair("https://e.com/c", "https://e.com/c-canon", 0.9, "near", canonicalized=True),
        DuplicatePair("https://e.com/d", "https://e.com/d-noindex", 1.0, "exact", noindex=True),
    ]
    thin = [_page("https://e.com/tiny", "few words")]
    actions, clusters = recommend(_report(pages, pairs, thin))
    assert len(clusters) == 3
    by_change = {a.change_url: a for a in actions}

    # Every non-primary URL gets exactly one action, always pointing at the primary.
    assert set(by_change) == {
        "https://e.com/a-copy",
        "https://e.com/b",
        "https://e.com/b-near",
        "https://e.com/c-canon",
        "https://e.com/d-noindex",
        "https://e.com/tiny",
    }
    assert len(actions) == 6

    assert by_change["https://e.com/a-copy"].code == "redirect"
    assert by_change["https://e.com/a-copy"].priority == "high"
    assert by_change["https://e.com/a-copy"].keep_url == "https://e.com/a"

    # c is the primary of {b, b-near, c, c-canon} because c-canon votes for it.
    assert (
        by_change["https://e.com/b"].code == "differentiate"
        and by_change["https://e.com/b"].keep_url == "https://e.com/c"
    )
    b_near = by_change["https://e.com/b-near"]
    assert b_near.code == "consolidate" and b_near.priority == "high" and b_near.keep_url == "https://e.com/c"
    assert "flagged through another page" in b_near.why  # no direct edge to the primary
    assert by_change["https://e.com/c-canon"].code == "verify-canonical"
    assert by_change["https://e.com/c-canon"].priority == "low"

    assert by_change["https://e.com/d-noindex"].code == "verify-noindex"
    assert by_change["https://e.com/tiny"].code == "thin" and by_change["https://e.com/tiny"].keep_url is None

    prios = [a.priority for a in actions]
    assert prios == sorted(prios, key=["high", "medium", "low"].index)
    assert all(a.cluster_id for a in actions if a.code != "thin")


def test_recommend_empty_report():
    actions, clusters = recommend(_report([], []))
    assert actions == [] and clusters == []


def test_actions_in_json_and_html(simple_site, tmp_path):
    from duplicatedcontentchecker.report import to_dict, write_html

    report = ContentDuplicateChecker(
        config=CrawlConfig("https://example.com", max_depth=3, threshold=0.7, min_words=20),
        fetcher=FakeFetcher(simple_site),
    ).run_report()
    data = to_dict(report)
    assert data["summary"]["actions"]["high"] >= 1
    assert data["clusters"] and data["actions"]
    out = write_html(report, tmp_path / "r.html")
    html = out.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert '<script id="report-data" type="application/json">' in html
    assert "__DATA__" not in html and "__LIVE__" not in html and "const LIVE = false" in html
    assert "\\u003c" in html or "<" not in data["base_url"]  # embedded JSON never contains a raw "<"
    assert "https://example.com/blog/post-1-copy" in html
