# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] - 2026-09-15

### Changed
- HTTPS only. Start URLs must use `https://` and plain-http links found on the
  site are never followed; there is no opt-out. `CrawlStats` gains `skipped_http`.
- README security section explains why a local tool must treat crawled data as
  untrusted (XSS) and how the localhost-service risk is handled.

## [2.1.0] - 2026-09-15

### Added
- **Interactive HTML dashboard** (`--html report.html`): a self-contained page with
  stat tiles, a similarity histogram, a pages-by-state chart, and an action plan
  that can be filtered by priority, action type, minimum similarity and free text,
  sorted by any column, and ticked off as done (stored in the browser). Clicking a
  histogram bar filters the plan to that range. Exports: CSV, JSON and a Markdown
  checklist on the clipboard. Light and dark themes.
- **Action engine**: every duplicate page gets one concrete recommendation aimed
  at its group's primary URL (301 redirect, consolidate, differentiate, verify
  canonical, verify noindex), plus thin-page actions. Duplicate groups are built
  with union-find and the primary is chosen by canonical votes, depth, URL length
  and word count. Actions and clusters are included in the JSON report.
- **`dupcheck serve`**: a local server (standard library only, bound to
  127.0.0.1) that hosts the same dashboard with a form to launch new scans with
  custom parameters, live progress and log, cancel, and CSV/JSON/HTML downloads.
  Bare `dupcheck` opens it. Every finished scan is saved as JSON, CSV and HTML
  under `--output-dir` (default `dupcheck-reports/`) and listed in the dashboard
  under "Previous scans" for reopening. `--load report.json` opens a saved report.
- **Saved HTML reports are the app**: opened from disk, a report connects to
  the local engine when it is running and can launch scans, show progress,
  replace its results and save, all from that file. If the engine is down, the
  page explains how to start it and builds the equivalent command.
- Engine token: API calls require a per-machine secret stored in
  `~/.dupcheck/token`; the engine embeds it in the pages it serves and in the
  reports written locally. Prevents other websites from driving the crawler.
  `--portable` writes a report without the token for sharing. The engine refuses
  localhost and private-network targets unless started with
  `--allow-private-hosts`. `dupcheck-reports/` is git-ignored.
- Crawler accepts a `should_stop` callback and exposes `queued_count` for progress.

## [2.0.0] - 2026-09-15

Full rewrite as an installable package with a CLI. The v1 Python API
(`ContentDuplicateChecker(base_url, max_depth).run()`) is preserved.

### Added
- `dupcheck` command-line tool with crawl-scope, network, analysis and output options.
- `CrawlConfig` dataclass and `run_report()` returning a structured `Report`.
- URL normalization: fragments, tracking parameters (`utm_*`, `fbclid`, `gclid`, …),
  default ports and duplicate slashes no longer create false duplicates. Trailing
  slashes are preserved so `/a` and `/a/` served separately are reported as a real duplicate.
- Main-content extraction that drops navigation, header, footer, sidebar, forms and
  scripts, preferring `<main>`/`<article>`. `--full-page` restores v1 behavior.
- Exact-duplicate detection by SHA-256 of folded text, separate from near-duplicate scoring.
- TF-IDF (unigram + bigram, sublinear) cosine similarity instead of raw term counts.
- `robots.txt` support, real User-Agent, per-request timeout, retries with backoff for
  429/5xx, Content-Type check, response size cap and optional inter-request delay.
- Breadth-first crawl with `--max-pages`, `--include`/`--exclude` regex filters,
  `--include-subdomains` and `--strip-query`.
- `--sitemap` seeds the crawl from `sitemap.xml`, sitemap indexes and robots.txt sitemaps.
- Redirect handling: pages are indexed under their final URL.
- Canonical and `noindex` awareness: pairs are annotated when already handled.
- Thin-page listing (`--min-words`).
- JSON report with pages, pairs, statistics and the configuration used.
- Markdown summary printed to stdout; `--fail-on-duplicates` for CI.
- Test suite (46 tests) with an in-memory fake site, no network required.
- GitHub Actions CI on Python 3.10–3.13 with ruff and pytest.
- `pyproject.toml` packaging; `pip install git+https://…` works.

### Changed
- Default near-duplicate threshold raised from 0.7 to 0.8, since boilerplate no longer inflates scores.
- CSV report gains `Type` and `Note` columns after the original three.
- Logging goes to stderr; use `-q`/`-v` to control verbosity.
- `readme.md` → `README.md`, `license` → `LICENSE`; broken Markdown fences fixed.

### Removed
- `pandas` dependency; the CSV is written with the standard library.
- Pinned 2023 dependency versions that failed to build on current Python.
- Hard-coded third-party domain in `run_checker.py`; it is now an example.

### Fixed
- Unbounded depth-first recursion that could exhaust the recursion limit on large sites.
- Requests without timeouts that could hang the crawl.
- Attempting to parse PDFs, images and other non-HTML resources.
- Changelog referencing a test file that did not exist.

## [1.0.0] - 2024-08-29

### Added
- Initial release: crawl a site, extract page text, compare with cosine similarity
  and write `duplicate_report.csv`.
