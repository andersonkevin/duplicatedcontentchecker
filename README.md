# Content Duplicate Checker

[![CI](https://github.com/andersonkevin/duplicatedcontentchecker/actions/workflows/ci.yml/badge.svg)](https://github.com/andersonkevin/duplicatedcontentchecker/actions/workflows/ci.yml)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

Crawl a website and find pages that repeat each other. Duplicate content splits
ranking signals between URLs and wastes crawl budget; this tool finds both exact
copies and near-duplicates so you can consolidate, canonicalize or rewrite them.

```bash
pip install git+https://github.com/andersonkevin/duplicatedcontentchecker.git
dupcheck
```

`dupcheck` with no arguments opens the dashboard in your browser. Enter a URL,
adjust the crawl parameters, press **Run scan**, and watch the results appear.
Every finished scan is saved as JSON, CSV and HTML under `dupcheck-reports/`
(change it with `--output-dir`), and the dashboard lists previous scans so you
can reopen them. Everything runs locally.

For scripts and CI, the same tool works as a plain command:

```bash
dupcheck https://example.com --max-depth 3 --html report.html
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
5. **Recommends an action for every duplicate page.** Pages are grouped into
   duplicate clusters, one primary URL is picked per cluster (canonical target,
   then shallowest, shortest, longest content), and each other member gets a
   concrete to-do: 301 redirect, consolidate, differentiate, or verify an
   existing canonical/noindex. Thin pages get their own action.
6. **Reports** a CSV, a JSON file with every page, pair, action and crawl
   statistic, a Markdown summary on stdout, and an interactive HTML dashboard.

## The dashboard

`dupcheck` (or `dupcheck serve`) starts the engine on your machine and opens
the dashboard. Every saved HTML report is the same dashboard: open the file
and, while the engine is running, it connects to it and you can run new scans
from that file, with progress, results and saving, exactly like the live page.
If the engine is not running, the page says so and builds the equivalent
command instead.

### How the local engine works and what it exposes

- The engine is the `dupcheck` process on your computer. It listens only on
  `127.0.0.1`, so nothing on your network or the internet can reach it. This is
  the same model Jupyter uses.
- Browsers let any website you visit send requests to `127.0.0.1`. To stop a
  malicious page from driving your crawler, every API call must carry a random
  token that lives in `~/.dupcheck/token` (owner-only permissions, created on
  first run). The engine embeds that token in the dashboard it serves and in
  the HTML reports it writes on this machine, and nowhere else.
- A report that carries your token is harmless elsewhere: the token only works
  against an engine on the same computer. To share a report without it, use
  `--portable`; the file then shows results but cannot launch scans. Saved
  reports live in `dupcheck-reports/`, which is git-ignored, so they are not
  committed by accident.
- Defense in depth: the engine refuses to scan localhost or private networks
  (10/8, 172.16/12, 192.168/16, link-local, `.local` names, and anything that
  resolves there). Even a leaked token cannot turn it into a scanner for your
  LAN. Start it with `--allow-private-hosts` if you audit an intranet site.
- To revoke the token, delete `~/.dupcheck/token`; a new one is generated on
  the next start and older reports stop being able to command the engine.
- HTTPS only: start URLs must be `https://`, and plain-http links found on
  the site are never followed. Crawl traffic is never sent unencrypted or
  exposed to tampering in transit. There is no opt-out; a site without TLS
  cannot be audited with this tool.

### Why a local tool still has to be careful

"Local" protects the program, not the data it processes. Everything the
crawler brings back (titles, URLs, canonical tags) was written by someone
else, and a hostile site can plant content designed to run inside whatever
displays it. That family of attack is cross-site scripting (XSS). The
dashboard therefore treats crawled data as untrusted: every value is escaped
before it is placed in the page, only `http(s)` URLs are rendered as links
(a canonical of `javascript:` or `data:` is shown as plain text and ignored by
the extractor), and links open with `rel="noopener noreferrer"`. The
localhost-service risk is a different family (any website you visit can send
requests to `127.0.0.1`); the per-machine token and the private-host block
close that door. The rule behind both: treat all input as untrusted, even
when the program runs on your own machine.
- No accounts, no telemetry, no cloud. Nothing is uploaded anywhere; the only
  outbound traffic is the crawl of the site you asked for.

### What is in it

- **At a glance**: high-priority count, pages crawled, exact and near pairs,
  clusters, thin pages; a similarity histogram and a pages-by-state chart.
- **Action plan**: filter by priority, action type, minimum similarity or free
  text; click a histogram bar to jump to that range; sort by any column; tick
  actions off as you go (kept in your browser); expand a row for the reasoning.
- **Exports**: CSV, JSON, and a Markdown checklist copied to the clipboard.
- **Clusters and pages**: every duplicate group with its primary, and the full
  crawled page list with word counts, canonical targets and noindex flags.
- **Live mode** (`dupcheck` / `dupcheck serve`): start URL, depth, page cap,
  threshold, min words, delay, include/exclude patterns, sitemap seeding and
  more; watch progress and the crawl log; cancel; download results. Finished
  scans are saved automatically to the output directory and listed under
  **Previous scans**. The engine binds to 127.0.0.1 and every API call needs the
  per-machine token described above.

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
dupcheck HTTPS_URL [options]

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
  --ignore-robots          do not honor robots.txt (only on sites you own)

analysis:
  -t, --threshold FLOAT    near-duplicate cosine threshold (default 0.8)
  --min-words N            pages shorter than this are listed as thin, not compared (default 50)
  --full-page              compare the whole page including nav/footer (v1 behavior)

output:
  -o, --output CSV         CSV path (default duplicate_report.csv)
  --json PATH              also write a JSON report
  --html PATH              also write the interactive HTML dashboard
  --portable               write the HTML without the local engine token (for sharing)
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

# Interactive dashboard on http://127.0.0.1:8765 (opens your browser)
dupcheck
dupcheck serve --port 9000 --no-open --output-dir ~/audits
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
match v1, so existing spreadsheets keep working. The JSON report adds `actions`
(one per duplicate page, with `priority`, `code`, `keep_url`, `change_url` and
`why`) and `clusters` (each group with its `primary` and `members`).

| Action | Priority | When |
| --- | --- | --- |
| `redirect` | high | Main content identical: 301 the duplicate to the primary, or canonicalize if both must stay |
| `consolidate` | high | ≥ 95% similar: merge unique bits into the primary, then redirect or canonicalize |
| `differentiate` | medium | Above threshold but below 95%: give the page a distinct purpose, or canonicalize variants |
| `verify-canonical` | low | The page already canonicalizes to the primary: confirm it is not indexed separately |
| `verify-noindex` | low | The page is noindex: consider a redirect so links still count |
| `thin` | low | Under `--min-words`: expand, merge, or noindex |

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
