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

TOKEN = "test-token"
HEADERS = {"X-Dupcheck-Token": TOKEN}


@pytest.fixture(autouse=True)
def _isolated_token_file(tmp_path, monkeypatch):
    """Never touch the real ~/.dupcheck/token from tests."""
    monkeypatch.setenv("DUPCHECK_TOKEN_FILE", str(tmp_path / "token"))


@pytest.fixture
def server(simple_site):
    runner = ScanRunner(fetcher_factory=lambda cfg: FakeFetcher(simple_site), token=TOKEN)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(runner))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        yield base, runner
    finally:
        httpd.shutdown()
        httpd.server_close()


def _get(url, raw=False, headers=HEADERS):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=5) as r:
        body = r.read()
        return (r.status, r.headers, body) if raw else json.loads(body)


def _post(url, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", **HEADERS}, method="POST"
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
    assert b'<meta name="dupcheck-mode" content="live">' in body
    assert f'<meta name="dupcheck-token" content="{TOKEN}">'.encode() in body

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
    assert b'content="static"' in body and b"https://example.com/blog/post-1-copy" in body
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


def test_bare_dupcheck_opens_dashboard_and_load_preloads(simple_site, tmp_path):
    """`dupcheck` with no arguments serves the dashboard; --load preloads a JSON report."""
    from duplicatedcontentchecker import ContentDuplicateChecker, CrawlConfig
    from duplicatedcontentchecker.cli import main
    from duplicatedcontentchecker.report import write_json

    calls = []

    def fake_serve(host, port, *, open_browser, runner):
        calls.append((host, port, open_browser, runner))

    assert main([], serve_fn=fake_serve) == 0
    assert calls[0][:3] == ("127.0.0.1", 8765, True)
    assert calls[0][3].s.state == "idle"

    report = ContentDuplicateChecker(
        config=CrawlConfig("https://example.com", max_depth=3, threshold=0.7, min_words=20),
        fetcher=FakeFetcher(simple_site),
    ).run_report()
    path = write_json(report, tmp_path / "r.json")
    assert main(["serve", "--no-open", "--port", "0", "--load", str(path)], serve_fn=fake_serve) == 0
    runner = calls[1][3]
    assert runner.s.state == "done" and runner.s.report_dict["base_url"] == "https://example.com"
    assert runner.s.report_dict["actions"]

    with pytest.raises(SystemExit):
        main(["serve", "--load", str(tmp_path / "missing.json")], serve_fn=fake_serve)


def test_loaded_report_serves_csv(simple_site, tmp_path):
    from duplicatedcontentchecker import ContentDuplicateChecker, CrawlConfig
    from duplicatedcontentchecker.report import write_json

    report = ContentDuplicateChecker(
        config=CrawlConfig("https://example.com", max_depth=3, threshold=0.7, min_words=20),
        fetcher=FakeFetcher(simple_site),
    ).run_report()
    runner = ScanRunner(token=TOKEN)
    runner.load(str(write_json(report, tmp_path / "r.json")))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(runner))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        assert _get(base + "/api/status")["state"] == "done"
        assert _get(base + "/api/report")["summary"]["exact_duplicate_pairs"] == 1
        _, _, body = _get(base + "/api/report.csv", raw=True)
        assert b"exact" in body and body.startswith(b"URL_1,URL_2,Similarity,Type,Note")
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_scans_are_saved_and_listed(simple_site, tmp_path):
    """A finished scan writes JSON/CSV/HTML into output_dir; history lists it; open reloads it."""
    out = tmp_path / "reports"
    runner = ScanRunner(fetcher_factory=lambda cfg: FakeFetcher(simple_site), output_dir=out, token=TOKEN)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(runner))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        assert _get(base + "/api/history") == {"output_dir": str(out), "reports": []}
        _post(base + "/api/scan", {"url": "https://example.com", "max_depth": 3, "threshold": 0.7, "min_words": 20})
        st = _wait_done(base)
        assert st["state"] == "done" and st["output_dir"] == str(out)
        assert sorted(st["saved"]) == ["csv", "html", "json"]
        files = sorted(p.name for p in out.iterdir())
        assert len(files) == 3 and all(f.startswith("example.com-") for f in files)
        assert (
            (out / [f for f in files if f.endswith(".html")][0])
            .read_text(encoding="utf-8")
            .startswith("<!doctype html>")
        )

        hist = _get(base + "/api/history")["reports"]
        assert len(hist) == 1 and hist[0]["base_url"] == "https://example.com" and hist[0]["pages"] == 7

        # Open the saved report by name; path traversal is refused.
        runner.s = type(runner.s)()  # reset to idle
        code, resp = _post(base + "/api/open", {"file": hist[0]["file"]})
        assert code == 200 and _get(base + "/api/report")["summary"]["pages_crawled"] == 7
        code, resp = _post(base + "/api/open", {"file": "../" + hist[0]["file"]})
        assert code == 400
        code, resp = _post(base + "/api/open", {"file": "nope.json"})
        assert code == 400
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_api_requires_token_and_answers_cors_preflight(server):
    """Pages opened from disk call the engine cross-origin; only the token opens the door."""
    base, _ = server
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(base + "/api/status", headers={})
    assert exc.value.code == 401
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(base + "/api/status", headers={"X-Dupcheck-Token": "wrong"})
    assert exc.value.code == 401
    # Query-string token works for download links.
    assert _get(base + "/api/status?token=" + TOKEN, headers={})["state"] == "idle"
    # The dashboard page itself needs no token (it embeds one).
    status, _, _ = _get(base + "/", raw=True, headers={})
    assert status == 200

    req = urllib.request.Request(base + "/api/scan", method="OPTIONS", headers={"Origin": "null"})
    with urllib.request.urlopen(req, timeout=5) as r:
        assert r.status == 204
        assert r.headers["Access-Control-Allow-Origin"] == "null"
        assert "X-Dupcheck-Token" in r.headers["Access-Control-Allow-Headers"]
    status, headers, _ = _get(base + "/api/status", raw=True)
    assert headers["Access-Control-Allow-Origin"] == "*"


def test_get_or_create_token_is_stable(tmp_path, monkeypatch):
    from duplicatedcontentchecker.engine_token import get_or_create_token, token_path

    monkeypatch.setenv("DUPCHECK_TOKEN_FILE", str(tmp_path / "deep" / "token"))
    first = get_or_create_token()
    assert len(first) == 48 and token_path().read_text().strip() == first
    assert get_or_create_token() == first


def test_engine_refuses_private_hosts_unless_allowed(simple_site):
    runner = ScanRunner(fetcher_factory=lambda cfg: FakeFetcher(simple_site), token=TOKEN)
    for url in (
        "http://localhost:8000/",
        "http://127.0.0.1/",
        "http://192.168.1.1/admin",
        "http://10.0.0.5/",
        "http://[::1]/",
        "http://router.local/",
    ):
        with pytest.raises(ValueError, match="private host"):
            runner.start({"url": url})
        assert runner.s.state == "idle"
    permissive = ScanRunner(fetcher_factory=lambda cfg: FakeFetcher(simple_site), token=TOKEN, allow_private_hosts=True)
    permissive.start({"url": "http://192.168.1.1/"})
    assert permissive.s.state in ("running", "done")


def test_is_private_host():
    from duplicatedcontentchecker.urlutils import is_private_host

    assert is_private_host("localhost") and is_private_host("127.0.0.1") and is_private_host("::1")
    assert is_private_host("10.1.2.3") and is_private_host("172.16.0.9") and is_private_host("192.168.0.1")
    assert is_private_host("169.254.1.1") and is_private_host("printer.local") and is_private_host("")
    assert not is_private_host("8.8.8.8") and not is_private_host("2606:4700::1111")
    assert not is_private_host("this-name-does-not-resolve.invalid")
