from duplicatedcontentchecker.analyzer import analyze, find_exact_duplicates, find_near_duplicates
from duplicatedcontentchecker.extractor import extract_page

from .conftest import LOREM_A, LOREM_B, page


def _p(url, body, title="Same title", **kw):
    return extract_page(page(title, body, **kw), url)


def test_exact_duplicates_grouped():
    pages = [_p("https://e.com/a", LOREM_A), _p("https://e.com/b", LOREM_A), _p("https://e.com/c", LOREM_B)]
    pairs = find_exact_duplicates(pages)
    assert [(p.url_1, p.url_2, p.kind) for p in pairs] == [("https://e.com/a", "https://e.com/b", "exact")]
    assert pairs[0].similarity == 1.0


def test_near_duplicates_respect_threshold():
    pages = [
        _p("https://e.com/a", LOREM_B),
        _p("https://e.com/b", LOREM_B + " One extra sentence about tripods, reflectors and stands."),
        _p("https://e.com/c", LOREM_A),
    ]
    high = find_near_duplicates(pages, threshold=0.8)
    assert [(p.url_1, p.url_2) for p in high] == [("https://e.com/a", "https://e.com/b")]
    assert 0.8 <= high[0].similarity < 1.0
    assert find_near_duplicates(pages, threshold=0.999) == []


def test_analyze_separates_thin_pages_and_annotates():
    pages = [
        _p("https://e.com/a", LOREM_A, canonical="https://e.com/b"),
        _p("https://e.com/b", LOREM_A, noindex=True),
        _p("https://e.com/tiny", "just a few words"),
    ]
    pairs, thin = analyze(pages, threshold=0.8, min_words=20)
    assert [p.url for p in thin] == ["https://e.com/tiny"]
    assert len(pairs) == 1
    assert pairs[0].kind == "exact"
    assert pairs[0].canonicalized is True
    assert pairs[0].noindex is True
    assert "canonical" in pairs[0].note and "noindex" in pairs[0].note


def test_analyze_handles_empty_and_single():
    assert analyze([], 0.8, 10) == ([], [])
    pairs, thin = analyze([_p("https://e.com/a", LOREM_A)], 0.8, 10)
    assert pairs == [] and thin == []
