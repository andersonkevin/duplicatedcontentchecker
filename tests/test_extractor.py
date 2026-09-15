from duplicatedcontentchecker.extractor import extract_links, extract_page

from .conftest import LOREM_A, page


def test_main_content_excludes_nav_and_footer():
    html = page("Hello", LOREM_A)
    p = extract_page(html, "https://example.com/hello")
    assert p.title == "Hello"
    assert p.h1 == "Hello"
    assert "Copyright Example" not in p.text
    assert "Contact" not in p.text
    assert p.word_count > 50
    assert p.language == "en"
    assert p.content_hash


def test_full_page_keeps_chrome():
    html = page("Hello", LOREM_A)
    p = extract_page(html, "https://example.com/hello", full_page=True)
    assert "Copyright Example" in p.text


def test_canonical_and_noindex():
    html = page("X", LOREM_A, canonical="/canonical-target/", noindex=True)
    p = extract_page(html, "https://example.com/x")
    assert p.canonical == "https://example.com/canonical-target/"
    assert p.noindex is True


def test_hash_ignores_case_and_whitespace():
    a = extract_page(page("T", "Hello   World"), "https://e.com/a")
    b = extract_page(page("T", "hello world"), "https://e.com/b")
    assert a.content_hash == b.content_hash


def test_noise_hint_divs_are_removed():
    html = (
        '<html><body><div class="site-sidebar">Sidebar junk</div>'
        '<div id="content"><p>Real text here</p></div></body></html>'
    )
    p = extract_page(html, "https://e.com/")
    assert "Sidebar junk" not in p.text
    assert "Real text here" in p.text


def test_extract_links_resolves_and_filters():
    html = (
        '<html><head><base href="https://example.com/dir/"></head><body>'
        '<a href="page">p</a><a href="/abs">a</a><a href="#frag">f</a>'
        '<a href="mailto:x@y.z">m</a><a href="javascript:void(0)">j</a>'
        '<a href="https://other.org/x?utm_campaign=q">o</a></body></html>'
    )
    links = extract_links(html, "https://example.com/other/")
    assert links == [
        "https://example.com/dir/page",
        "https://example.com/abs",
        "https://other.org/x",
    ]
