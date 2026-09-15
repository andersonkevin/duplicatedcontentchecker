"""The local dashboard server, exercised over real HTTP on a random port."""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from duplicatedcontentchecker.server import ScanRunner, config_from_payload, make_handler

from .conftest import FakeFetcher


@pytest.fixture
def server(simple_site):
    runner = ScanRunner(fetcher_factory=lambda cfg: FakeFetcher(simple_site))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(runner))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        yield base, runner
    finally:
        httpd.shutdown()
        httpd.server_close()


def _get(url, raw=False):
    with urllib.request.urlopen(url, timeout=5) as r:
        body = r.read()
        return (r.status, r.headers, body) if raw else json.loads(body)


def _post(url, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _wait_done(base, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = _get(base + "/api/status")
        if st["state"] in ("done", "error"):
            return st
        time.sleep(0.05)
    raise AssertionError("scan did not finish")


def test_config_from_payload_parses_form_values():
    cfg = config_from_payload(
        {
            "url": " https://e.com ",
            "max_depth": "3",
            "max_pages": "",
            "threshold": "0.9",
            "include": "/blog/|/docs/",
            "exclude": "",
            "use_sitemap": True,
            "ignore_robots": False,
        }
    )
    assert cfg.base_url == "https://e.com" and cfg.max_depth == 3 and cfg.max_pages == 200
    assert cfg.threshold == 0.9 and cfg.include_patterns == ("/blog/", "/docs/") and cfg.exclude_patterns == ()
    assert cfg.use_sitemap is True and cfg.respect_robots is True
    with pytest.raises(ValueError):
        config_from_payload({"url": "not a url"})


def test_dashboard_and_scan_lifecycle(server):
    base, _ = server
    status, headers, body = _get(base + "/", raw=True)
    assert status == 200 and "text/html" in headers["Content-Type"]
    assert b"const LIVE = true" in body and b"__DATA__" not in body

    assert _get(base + "/api/status")["state"] == "idle"
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(base + "/api/report")
    assert exc.value.code == 404

    code, resp = _post(
        base + "/api/scan", {"url": "https://example.com", "max_depth": 3, "threshold": 0.7, "min_words": 20}
    )
    assert code == 202 and resp["state"] == "running"
    st = _wait_done(base)
    assert st["state"] == "done", st
    assert st["progress"]["fetched"] == 7 and st["progress"]["phase"] == "finished"
    assert any("Fetching" in line for line in st["log"])

    report = _get(base + "/api/report")
    assert report["summary"]["pages_crawled"] == 7
    assert report["summary"]["exact_duplicate_pairs"] == 1
    assert report["actions"] and report["clusters"]

    status, headers, body = _get(base + "/api/report.csv", raw=True)
    assert body.startswith(b"URL_1,URL_2,Similarity,Type,Note") and "attachment" in headers["Content-Disposition"]
    status, headers, body = _get(base + "/api/report.html", raw=True)
    assert b"const LIVE = false" in body and b"https://example.com/blog/post-1-copy" in body
    status, headers, body = _get(base + "/api/report.json", raw=True)
    assert json.loads(body)["base_url"] == "https://example.com"


def test_scan_rejects_bad_input_and_double_start(server):
    base, runner = server
    code, resp = _post(base + "/api/scan", {"url": "nope"})
    assert code == 400 and "base_url" in resp["error"]
    code, resp = _post(base + "/api/scan", {"url": "https://example.com", "threshold": "5"})
    assert code == 400

    # Simulate a running scan and make sure a second one is refused.
    runner.s.state = "running"
    code, resp = _post(base + "/api/scan", {"url": "https://example.com"})
    assert code == 400 and "already running" in resp["error"]
    runner.s.state = "idle"

    code, resp = _post(base + "/api/cancel", {})
    assert code == 200 and resp["ok"] is True
    status, _, _ = _get(base + "/nope", raw=True) if False else (404, None, None)
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(base + "/nope")
    assert exc.value.code == 404


def test_cancel_stops_crawl(simple_site):
    """A crawler whose should_stop fires immediately returns without fetching."""
    from duplicatedcontentchecker.crawler import Crawler
    from duplicatedcontentchecker.models import CrawlConfig

    crawler = Crawler(
        CrawlConfig("https://example.com", max_depth=3), FakeFetcher(simple_site), should_stop=lambda: True
    )
    assert crawler.crawl() == [] and crawler.stopped_early is True
