# Contributing

Thanks for helping improve the Content Duplicate Checker. Bug reports, feature
requests, documentation fixes and pull requests are all welcome.

## Reporting issues

Open an issue with the command you ran, the site type (static, WordPress, SPA…),
the relevant part of the output or traceback, and your Python version. Do not
paste private URLs or reports you cannot share.

## Development setup

```bash
git clone https://github.com/andersonkevin/duplicatedcontentchecker.git
cd duplicatedcontentchecker
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check . && ruff format --check .
```

Tests must not touch the network. Use the `FakeFetcher` and `page()` helpers in
`tests/conftest.py` to build an in-memory site.

## Making changes

1. Create a branch with a descriptive name, for example `fix-canonical-detection`.
2. Keep the public API stable: `ContentDuplicateChecker(base_url, max_depth).run()`
   and the first three CSV columns are relied on by existing users.
3. Add or update tests for the behaviour you change.
4. Run `pytest` and `ruff` before opening the pull request.
5. Add a line under **Unreleased** in `CHANGELOG.md`.

## Code layout

| Module | Responsibility |
| --- | --- |
| `models.py` | Dataclasses: `CrawlConfig`, `Page`, `DuplicatePair`, `Report` |
| `urlutils.py` | URL normalization and scope checks |
| `fetcher.py` | HTTP session, robots.txt, retries, throttling |
| `extractor.py` | HTML → main text, links, canonical, noindex |
| `sitemap.py` | Sitemap discovery and parsing |
| `crawler.py` | Breadth-first crawl loop |
| `analyzer.py` | Exact and TF-IDF near-duplicate detection |
| `report.py` | CSV, JSON and Markdown output |
| `checker.py` | Facade and v1-compatible API |
| `cli.py` | `dupcheck` command |
