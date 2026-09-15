"""HttpFetcher tests using a mocked requests session (no network)."""

from __future__ import annotations

from io import BytesIO
from unittest import mock

import requests

from duplicatedcontentchecker.fetcher import HttpFetcher


class _Raw(BytesIO):
    """urllib3's HTTPResponse.read accepts decode_content; BytesIO does not."""

    def read(self, amt=-1, decode_content=None):  # noqa: ARG002
        return super().read(amt)


class _Resp:
    def __init__(self, status=200, content_type="text/html; charset=utf-8", body=b"<html></html>", url=None, text=""):
        self.status_code = status
        self.headers = {"Content-Type": content_type}
        self.raw = _Raw(body)
        self.url = url or "https://example.com/"
        self.encoding = "utf-8"
        self.text = text or body.decode("utf-8", "replace")

    def close(self):
        pass


def _fetcher(**kw) -> HttpFetcher:
    return HttpFetcher(respect_robots=False, **kw)


def test_fetch_returns_html():
    f = _fetcher()
    with mock.patch.object(f.session, "get", return_value=_Resp(body=b"<html><body>hi</body></html>")) as get:
        result = f.fetch("https://example.com/")
    assert result is not None
    assert "hi" in result.html
    assert result.status == 200
    _, kwargs = get.call_args
    assert kwargs["timeout"] == 15.0


def test_fetch_skips_non_html_and_errors():
    f = _fetcher()
    with mock.patch.object(f.session, "get", return_value=_Resp(content_type="application/pdf")):
        assert f.fetch("https://example.com/x.pdf") is None
    with mock.patch.object(f.session, "get", return_value=_Resp(status=404)):
        assert f.fetch("https://example.com/missing") is None
    with mock.patch.object(f.session, "get", side_effect=requests.ConnectionError("boom")):
        assert f.fetch("https://example.com/") is None


def test_robots_disallow_is_honoured():
    f = HttpFetcher(respect_robots=True, user_agent="TestBot/1.0")
    robots = _Resp(
        content_type="text/plain", body=b"User-agent: *\nDisallow: /private\nSitemap: https://example.com/sm.xml\n"
    )
    with mock.patch.object(f.session, "get", return_value=robots) as get:
        assert f.allowed("https://example.com/public") is True
        assert f.allowed("https://example.com/private/x") is False
        assert f.sitemaps_from_robots("https://example.com/") == ["https://example.com/sm.xml"]
    # robots.txt fetched once per origin
    assert get.call_count == 1


def test_missing_robots_allows_everything():
    f = HttpFetcher(respect_robots=True)
    with mock.patch.object(f.session, "get", return_value=_Resp(status=404, content_type="text/plain")):
        assert f.allowed("https://example.com/anything") is True


def test_delay_throttles(monkeypatch):
    f = _fetcher(delay=0.5)
    sleeps: list[float] = []
    clock = iter([100.0, 100.0, 100.1, 100.1, 100.6])
    monkeypatch.setattr("duplicatedcontentchecker.fetcher.time.monotonic", lambda: next(clock))
    monkeypatch.setattr("duplicatedcontentchecker.fetcher.time.sleep", lambda s: sleeps.append(s))
    with mock.patch.object(f.session, "get", return_value=_Resp()):
        f.fetch("https://example.com/a")
        f.fetch("https://example.com/b")
    assert sleeps and abs(sleeps[0] - 0.4) < 1e-6
