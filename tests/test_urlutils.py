import pytest

from duplicatedcontentchecker.urlutils import in_scope, is_internal, looks_like_html, normalize_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://Example.com/About/", "https://example.com/About/"),
        ("https://example.com/about#team", "https://example.com/about"),
        ("https://example.com/dir/./sub/../", "https://example.com/dir/"),
        ("https://example.com:443/about", "https://example.com/about"),
        ("http://example.com:8080/about", "http://example.com:8080/about"),
        ("https://example.com//a//b/../c", "https://example.com/a/c"),
        ("https://example.com/?utm_source=x&b=2&a=1", "https://example.com/?a=1&b=2"),
        ("https://example.com/p?fbclid=abc", "https://example.com/p"),
        ("https://example.com", "https://example.com/"),
        ("https://example.com/", "https://example.com/"),
    ],
)
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected


def test_normalize_relative_against_base():
    assert normalize_url("../x?z=1", base="https://example.com/a/b/") == "https://example.com/a/x?z=1"


def test_normalize_strip_query():
    assert normalize_url("https://example.com/p?page=2", strip_query=True) == "https://example.com/p"


def test_is_internal_ignores_www_and_scheme():
    base = "https://www.example.com"
    assert is_internal("http://example.com/x", base)
    assert is_internal("https://www.example.com/y", base)
    assert not is_internal("https://blog.example.com/y", base)
    assert is_internal("https://blog.example.com/y", base, include_subdomains=True)
    assert not is_internal("https://example.org", base)
    assert not is_internal("mailto:hi@example.com", base)


def test_looks_like_html():
    assert looks_like_html("https://example.com/page")
    assert looks_like_html("https://example.com/page.html")
    assert not looks_like_html("https://example.com/file.PDF")
    assert not looks_like_html("https://example.com/img.png?x=1")


def test_in_scope_patterns():
    assert in_scope("https://example.com/blog/x", ("/blog/",), ())
    assert not in_scope("https://example.com/shop/x", ("/blog/",), ())
    assert not in_scope("https://example.com/blog/tag/x", (), (r"/tag/",))
    assert in_scope("https://example.com/anything", (), ())
