# Content Duplicate Checker

[![CI](https://github.com/andersonkevin/duplicatedcontentchecker/actions/workflows/ci.yml/badge.svg)](https://github.com/andersonkevin/duplicatedcontentchecker/actions/workflows/ci.yml)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

Crawl a website and find pages that repeat each other. Duplicate content splits
ranking signals between URLs and wastes crawl budget; this tool finds both exact
copies and near-duplicates so you can consolidate, canonicalize or rewrite them.

```bash
pip install git+https://github.com/andersonkevin/duplicatedcontentchecker.git
dupcheck https://example.com --max-depth 3 --json report.json
```

```text
# Duplicate content report for https://example.com

- Pages crawled: 148
- Fetch failures: 2
- Blocked by robots.txt: 4 · skipped by pattern: 0
- Thin pages (< 50 words): 7
- Exact duplicate pairs: 3
- Near duplicate pairs (≥ 0.80): 11

| Similarity | Type  | URL 1                          | URL 2                              | Note |
|-----------:|-------|--------------------------------|------------------------------------|------|
|      1.000 | exact | https://example.com/blog/post  | https://example.com/blog/post-copy |      |
|      0.913 | near  | https://example.com/services   | https://example.com/services-old   | canonical points to the other page |
```

## What it does

1. **Crawls** the site breadth-first from the start URL, following internal links
   up to `--max-depth` hops and `--max-pages` pages. Optionally seeds the crawl
   from `sitemap.xml` so orphan pages are included.
2. **Normalizes URLs** so `/about`, `/about#team` and `/about?utm_source=x`
   count as one page instead of three false duplicates. `/about/` is kept
   distinct on purpose: if a site serves both without redirecting, that is a
   real duplicate and it will be reported as one.
3. **Extracts the main content** from each page. Navigation, header, footer,
   sidebar, forms and scripts are removed; `<main>` or `<article>` is preferred
   when present. Shared site chrome no longer inflates similarity.
4. **Detects duplicates** two ways:
   - **Exact**: SHA-256 of the whitespace- and case-folded text.
   - **Near**: TF-IDF (word unigrams + bigrams, sublinear TF) cosine similarity
     at or above `--threshold` (default 0.8).
5. **Reports** a CSV, an optional JSON file with every page and crawl statistic,
   and a Markdown summary on stdout. Pairs are annotated when one page already
   canonicalizes to the other or is marked `noindex`, so you can tell real
   problems from ones you have already handled.

It respects `robots.txt`, sends a real User-Agent, times out, retries transient
errors, skips non-HTML responses, and can wait between requests.

## Installation

Requires Python 3.10 or newer.

```bash
pip install git+https://github.com/andersonkevin/duplicatedcontentchecker.git
```

Or from a clone:

```bash
git clone https://github.com/andersonkevin/duplicatedcontentchecker.git
cd duplicatedcontentchecker
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Command line

```text
dupcheck URL [options]

crawl scope:
  -d, --max-depth N        link hops to follow from the start URL (default 2)
  -n, --max-pages N        stop after this many pages (default 500)
  --include REGEX          only crawl URLs matching (repeatable)
  --exclude REGEX          skip URLs matching (repeatable)
  --include-subdomains     treat blog.example.com as part of example.com
  --sitemap                seed the crawl from sitemap.xml and robots.txt sitemaps
  --strip-query            ignore query strings when deduplicating URLs

network:
  --delay SECONDS          wait between requests (default 0)
  --timeout SECONDS        per-request timeout (default 15)
  --retries N              retries for 429/5xx (default 2)
  --user-agent UA          User-Agent header
  --ignore-robots          do not honour robots.txt (only on sites you own)

analysis:
  -t, --threshold FLOAT    near-duplicate cosine threshold (default 0.8)
  --min-words N            pages shorter than this are listed as thin, not compared (default 50)
  --full-page              compare the whole page including nav/footer (v1 behaviour)

output:
  -o, --output CSV         CSV path (default duplicate_report.csv)
  --json PATH              also write a JSON report
  --no-summary             do not print the Markdown summary
  --fail-on-duplicates     exit 1 if any pair is found (useful in CI)
  -q / -v                  quieter / more verbose logging
```

Examples:

```bash
# Audit only the blog, politely, and keep the full JSON for later
dupcheck https://example.com --include "/blog/" --delay 0.5 --json blog.json

# Include orphan pages from the sitemap and be stricter about what counts as a duplicate
dupcheck https://example.com --sitemap --threshold 0.9 --max-pages 2000

# Skip tag and pagination archives
dupcheck https://example.com --exclude "/tag/" --exclude "/page/\d+"
```

## Python API

```python
from duplicatedcontentchecker import ContentDuplicateChecker, CrawlConfig

config = CrawlConfig("https://example.com", max_depth=3, threshold=0.85, delay=0.2)
report = ContentDuplicateChecker(config=config).run_report()

print(len(report.pages), "pages crawled")
for pair in report.pairs:
    print(f"{pair.similarity:.2f} {pair.kind:5} {pair.url_1} <-> {pair.url_2} {pair.note}")
for page in report.thin_pages:
    print("thin:", page.url, page.word_count)
```

The v1 interface still works unchanged and writes `duplicate_report.csv`:

```python
from duplicatedcontentchecker import ContentDuplicateChecker

checker = ContentDuplicateChecker(base_url="https://example.com", max_depth=4)
checker.run()
```

## Reading the report

**CSV columns:** `URL_1`, `URL_2`, `Similarity`, `Type`, `Note`. The first three
match v1, so existing spreadsheets keep working.

| Similarity | Meaning | Typical action |
| --- | --- | --- |
| 1.00 (exact) | Same main content byte for byte after folding case and whitespace | Redirect one to the other or add a canonical |
| 0.90 – 0.99 | Near copies: templated pages, old and new versions, print views | Consolidate or differentiate |
| 0.80 – 0.90 | Heavy overlap: shared boilerplate inside the content area, thin variations | Review; often product/category variants |
| Below threshold | Not reported | — |

The `Note` column flags pairs where a page already points its canonical at the
other page, or where a page is `noindex`. Those are usually already handled.

**Thin pages** (under `--min-words`) are listed separately. Very short pages
score high against each other for trivial reasons, so they are excluded from
near-duplicate comparison but still take part in exact matching.

## Limitations

- Content rendered only by JavaScript is not seen. The crawler reads the HTML
  the server returns.
- Similarity is lexical. Two pages saying the same thing in different words are
  not flagged; two pages with the same long legal notice inside `<main>` are.
- The boilerplate heuristics are generic. If a site puts its navigation inside
  `<main>`, use `--exclude` and `--threshold` to tune, or `--full-page` to
  compare everything.
- The full similarity matrix is computed in one pass. Several thousand pages are
  fine; tens of thousands will need a lot of memory.

## Development

```bash
pip install -e ".[dev]"
pytest            # 40+ tests, no network access needed
ruff check .
ruff format .
```

Tests use an in-memory fake site, so they run offline and in CI. See
[CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
