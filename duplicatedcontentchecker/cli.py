"""Command-line interface: ``dupcheck https://example.com``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .checker import ContentDuplicateChecker
from .models import DEFAULT_USER_AGENT, CrawlConfig
from .report import markdown_summary, write_csv, write_html, write_json


def build_serve_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dupcheck serve",
        description="Start a local dashboard where you can run scans with custom parameters.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--host", default="127.0.0.1", help="Interface to bind (keep it local; API calls need the per-machine token)"
    )
    p.add_argument("--port", type=int, default=8765, help="Port to listen on (0 picks a free port)")
    p.add_argument("--no-open", action="store_true", help="Do not open the browser automatically")
    p.add_argument(
        "--output-dir",
        default="dupcheck-reports",
        metavar="DIR",
        help="Where every finished scan is saved as JSON, CSV and HTML; previous scans are listed in the dashboard",
    )
    p.add_argument("--load", metavar="REPORT.json", help="Open this saved JSON report when the dashboard starts")
    p.add_argument("-q", "--quiet", action="store_true", help="Only log warnings and errors")
    p.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    return p


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dupcheck",
        description="Crawl a website and report exact and near-duplicate pages.",
        epilog="Run 'dupcheck' with no arguments (or 'dupcheck serve') to open the interactive dashboard "
        "and launch scans from the browser.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("url", help="Absolute URL to start crawling from, e.g. https://example.com")
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")

    scope = p.add_argument_group("crawl scope")
    scope.add_argument("-d", "--max-depth", type=int, default=2, help="How many link hops to follow from the start URL")
    scope.add_argument("-n", "--max-pages", type=int, default=500, help="Stop after this many pages")
    scope.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="REGEX",
        help="Only crawl URLs matching this pattern (repeatable)",
    )
    scope.add_argument(
        "--exclude", action="append", default=[], metavar="REGEX", help="Skip URLs matching this pattern (repeatable)"
    )
    scope.add_argument("--include-subdomains", action="store_true", help="Treat subdomains as part of the site")
    scope.add_argument("--sitemap", action="store_true", help="Seed the crawl from sitemap.xml and robots.txt sitemaps")
    scope.add_argument(
        "--strip-query", action="store_true", help="Ignore query strings entirely when deduplicating URLs"
    )

    net = p.add_argument_group("network")
    net.add_argument("--delay", type=float, default=0.0, help="Seconds to wait between requests")
    net.add_argument("--timeout", type=float, default=15.0, help="Per-request timeout in seconds")
    net.add_argument("--retries", type=int, default=2, help="Retries for transient HTTP errors")
    net.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="User-Agent header to send")
    net.add_argument("--ignore-robots", action="store_true", help="Do not honor robots.txt (use only on sites you own)")

    ana = p.add_argument_group("analysis")
    ana.add_argument(
        "-t",
        "--threshold",
        type=float,
        default=0.8,
        help="Cosine similarity at or above which pages are near-duplicates",
    )
    ana.add_argument(
        "--min-words", type=int, default=50, help="Pages shorter than this are reported as thin and not compared"
    )
    ana.add_argument(
        "--full-page",
        action="store_true",
        help="Compare the whole page instead of the main content area (v1 behavior)",
    )

    out = p.add_argument_group("output")
    out.add_argument("-o", "--output", default="duplicate_report.csv", metavar="CSV", help="CSV report path")
    out.add_argument("--json", metavar="PATH", help="Also write a JSON report with pages, stats and config")
    out.add_argument("--html", metavar="PATH", help="Also write a self-contained HTML dashboard with an action plan")
    out.add_argument(
        "--portable",
        action="store_true",
        help="Write the HTML without the local engine token (for sharing; it then cannot launch scans)",
    )
    out.add_argument("--no-summary", action="store_true", help="Do not print the Markdown summary to stdout")
    out.add_argument(
        "--fail-on-duplicates", action="store_true", help="Exit with status 1 when any duplicate pair is found (for CI)"
    )
    out.add_argument("-q", "--quiet", action="store_true", help="Only log warnings and errors")
    out.add_argument("-v", "--verbose", action="store_true", help="Log every extracted page and skipped link")
    return p


def config_from_args(args: argparse.Namespace) -> CrawlConfig:
    return CrawlConfig(
        base_url=args.url,
        max_depth=args.max_depth,
        max_pages=args.max_pages,
        threshold=args.threshold,
        min_words=args.min_words,
        delay=args.delay,
        timeout=args.timeout,
        retries=args.retries,
        user_agent=args.user_agent,
        respect_robots=not args.ignore_robots,
        include_subdomains=args.include_subdomains,
        include_patterns=tuple(args.include),
        exclude_patterns=tuple(args.exclude),
        use_sitemap=args.sitemap,
        full_page=args.full_page,
        strip_query=args.strip_query,
    )


def serve_main(argv: list[str], *, serve_fn=None) -> int:
    parser = build_serve_parser()
    args = parser.parse_args(argv)
    level = logging.DEBUG if args.verbose else logging.WARNING if args.quiet else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)
    for handler in logging.getLogger().handlers:
        handler.setLevel(level)  # the scan thread raises the package logger to INFO for the dashboard
    from .server import ScanRunner, serve  # local import keeps plain runs light

    runner = ScanRunner(output_dir=args.output_dir)
    if args.load:
        try:
            runner.load(args.load)
        except (OSError, ValueError) as exc:
            parser.error(f"could not load {args.load}: {exc}")
    (serve_fn or serve)(args.host, args.port, open_browser=not args.no_open, runner=runner)
    return 0


def main(argv: list[str] | None = None, *, fetcher=None, serve_fn=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        return serve_main([], serve_fn=serve_fn)  # bare `dupcheck` opens the dashboard
    if argv[0] == "serve":
        return serve_main(argv[1:], serve_fn=serve_fn)
    parser = build_parser()
    args = parser.parse_args(argv)

    level = logging.DEBUG if args.verbose else logging.WARNING if args.quiet else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)

    try:
        config = config_from_args(args)
    except ValueError as exc:
        parser.error(str(exc))

    checker = ContentDuplicateChecker(config=config, fetcher=fetcher)
    report = checker.run_report()

    csv_path = write_csv(report, args.output)
    logging.getLogger(__name__).info("CSV report written to %s", Path(csv_path).resolve())
    if args.json:
        write_json(report, args.json)
        logging.getLogger(__name__).info("JSON report written to %s", Path(args.json).resolve())
    if args.html:
        from .engine_token import get_or_create_token

        write_html(report, args.html, token=None if args.portable else get_or_create_token())
        logging.getLogger(__name__).info("HTML dashboard written to %s", Path(args.html).resolve())

    if not args.no_summary:
        sys.stdout.write(markdown_summary(report))

    if args.fail_on_duplicates and report.pairs:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
