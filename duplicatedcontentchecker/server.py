"""``dupcheck serve``: a local dashboard that can run new scans.

Standard library only. Binds to localhost by default; it has no
authentication, so do not expose it on a public interface.
"""

from __future__ import annotations

import json
import logging
import threading
import webbrowser
from collections import deque
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .analyzer import analyze
from .crawler import Crawler
from .fetcher import Fetcher
from .models import DEFAULT_USER_AGENT, CrawlConfig, Report
from .report import csv_text, render_html, to_dict

log = logging.getLogger(__name__)


class _RingHandler(logging.Handler):
    def __init__(self, lines: deque[str]) -> None:
        super().__init__(level=logging.INFO)
        self.lines = lines
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


@dataclass
class ScanState:
    state: str = "idle"  # idle | running | done | error
    error: str | None = None
    crawler: Crawler | None = None
    config: CrawlConfig | None = None
    report: Report | None = None
    report_dict: dict | None = None
    phase: str = ""
    log: deque[str] = field(default_factory=lambda: deque(maxlen=200))
    cancel: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)


def config_from_payload(payload: dict[str, Any]) -> CrawlConfig:
    """Build a CrawlConfig from the JSON the dashboard form posts."""

    def num(key: str, default: float, cast=float):
        raw = payload.get(key, default)
        if raw in ("", None):
            return cast(default)
        return cast(raw)

    def patterns(key: str) -> tuple[str, ...]:
        raw = payload.get(key) or ""
        if isinstance(raw, list):
            return tuple(str(p) for p in raw if p)
        return tuple(p.strip() for p in str(raw).split("|") if p.strip())

    return CrawlConfig(
        base_url=str(payload.get("url", "")).strip(),
        max_depth=num("max_depth", 2, int),
        max_pages=num("max_pages", 200, int),
        threshold=num("threshold", 0.8),
        min_words=num("min_words", 50, int),
        delay=num("delay", 0.2),
        timeout=num("timeout", 15.0),
        retries=num("retries", 2, int),
        user_agent=str(payload.get("user_agent") or DEFAULT_USER_AGENT),
        respect_robots=not bool(payload.get("ignore_robots", False)),
        include_subdomains=bool(payload.get("include_subdomains", False)),
        include_patterns=patterns("include"),
        exclude_patterns=patterns("exclude"),
        use_sitemap=bool(payload.get("use_sitemap", False)),
        full_page=bool(payload.get("full_page", False)),
        strip_query=bool(payload.get("strip_query", False)),
    )


class ScanRunner:
    """Owns one scan at a time and exposes its status."""

    def __init__(self, fetcher_factory=None) -> None:
        self.s = ScanState()
        self._fetcher_factory = fetcher_factory  # tests inject a FakeFetcher

    def status(self) -> dict:
        s = self.s
        crawler = s.crawler
        progress = {
            "fetched": crawler.stats.fetched if crawler else 0,
            "failed": crawler.stats.failed if crawler else 0,
            "queued": crawler.queued_count if crawler else 0,
            "pages": len(crawler.pages) if crawler else 0,
            "max_pages": s.config.max_pages if s.config else 0,
            "phase": s.phase,
        }
        return {"state": s.state, "error": s.error, "progress": progress, "log": list(s.log)}

    def start(self, payload: dict[str, Any]) -> None:
        with self.s.lock:
            if self.s.state == "running":
                raise RuntimeError("A scan is already running")
            config = config_from_payload(payload)  # raises ValueError on bad input
            self.s = ScanState(state="running", config=config, phase="starting")
        thread = threading.Thread(target=self._run, name="dupcheck-scan", daemon=True)
        thread.start()

    def cancel(self) -> None:
        self.s.cancel.set()

    def _run(self) -> None:
        s = self.s
        handler = _RingHandler(s.log)
        pkg_logger = logging.getLogger("duplicatedcontentchecker")
        pkg_logger.addHandler(handler)
        # The progress panel needs INFO lines even when the console is quieter.
        # Console handlers keep their own level, so this does not make them noisier.
        previous_level = pkg_logger.level
        if pkg_logger.getEffectiveLevel() > logging.INFO:
            pkg_logger.setLevel(logging.INFO)
        try:
            fetcher: Fetcher | None = self._fetcher_factory(s.config) if self._fetcher_factory else None
            s.crawler = Crawler(s.config, fetcher=fetcher, should_stop=s.cancel.is_set)
            s.phase = "crawling"
            pages = s.crawler.crawl()
            s.phase = "comparing"
            pairs, thin = analyze(pages, s.config.threshold, s.config.min_words)
            s.report = Report(
                base_url=s.config.base_url,
                pages=pages,
                pairs=pairs,
                stats=s.crawler.stats,
                config=s.config,
                thin_pages=thin,
            )
            s.phase = "building report"
            s.report_dict = to_dict(s.report)
            s.phase = "canceled" if s.cancel.is_set() else "finished"
            s.state = "done"
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI
            log.exception("Scan failed")
            s.error = f"{type(exc).__name__}: {exc}"
            s.state = "error"
        finally:
            pkg_logger.removeHandler(handler)
            pkg_logger.setLevel(previous_level)


def make_handler(runner: ScanRunner):
    class Handler(BaseHTTPRequestHandler):
        server_version = "dupcheck"

        def log_message(self, fmt, *args):  # quieter than the default
            log.debug("%s " + fmt, self.address_string(), *args)

        def _send(self, status: HTTPStatus, body: bytes, content_type: str, download: str | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{download}"')
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj: Any, status: HTTPStatus = HTTPStatus.OK, download: str | None = None) -> None:
            body = json.dumps(obj, ensure_ascii=False, indent=2 if download else None).encode("utf-8")
            self._send(status, body, "application/json; charset=utf-8", download)

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            s = runner.s
            if path in ("/", "/index.html"):
                html = render_html(None, live=True, title="dupcheck dashboard").encode("utf-8")
                self._send(HTTPStatus.OK, html, "text/html; charset=utf-8")
            elif path == "/api/status":
                self._json(runner.status())
            elif path == "/api/report":
                if s.report_dict is None:
                    self._json({"error": "No report yet"}, HTTPStatus.NOT_FOUND)
                else:
                    self._json(s.report_dict)
            elif path == "/api/report.json":
                if s.report_dict is None:
                    self._json({"error": "No report yet"}, HTTPStatus.NOT_FOUND)
                else:
                    self._json(s.report_dict, download="duplicate_report.json")
            elif path == "/api/report.csv":
                if s.report is None:
                    self._json({"error": "No report yet"}, HTTPStatus.NOT_FOUND)
                else:
                    body = csv_text(s.report).encode("utf-8")
                    self._send(HTTPStatus.OK, body, "text/csv; charset=utf-8", "duplicate_report.csv")
            elif path == "/api/report.html":
                if s.report_dict is None:
                    self._json({"error": "No report yet"}, HTTPStatus.NOT_FOUND)
                else:
                    html = render_html(s.report_dict, title=f"Duplicate content · {s.report_dict['base_url']}")
                    self._send(HTTPStatus.OK, html.encode("utf-8"), "text/html; charset=utf-8", "duplicate_report.html")
            else:
                self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            if path == "/api/scan":
                try:
                    payload = json.loads(raw or b"{}")
                    if not isinstance(payload, dict):
                        raise ValueError("payload must be an object")
                    runner.start(payload)
                except (ValueError, RuntimeError) as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                    return
                self._json({"ok": True, "state": "running"}, HTTPStatus.ACCEPTED)
            elif path == "/api/cancel":
                runner.cancel()
                self._json({"ok": True})
            else:
                self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    return Handler


def serve(
    host: str = "127.0.0.1", port: int = 8765, *, open_browser: bool = True, runner: ScanRunner | None = None
) -> None:
    """Run the dashboard server until interrupted."""
    runner = runner or ScanRunner()
    httpd = ThreadingHTTPServer((host, port), make_handler(runner))
    url = f"http://{host}:{httpd.server_address[1]}/"
    log.info("Dashboard at %s (Ctrl+C to stop)", url)
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        runner.cancel()
        httpd.server_close()


__all__ = ["ScanRunner", "config_from_payload", "make_handler", "serve"]
