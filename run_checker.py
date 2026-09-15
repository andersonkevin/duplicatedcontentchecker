"""Minimal example. Prefer the ``dupcheck`` command for day-to-day use.

python run_checker.py https://example.com
"""

import sys

from duplicatedcontentchecker import ContentDuplicateChecker, CrawlConfig

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    config = CrawlConfig(base_url=url, max_depth=3, max_pages=200, threshold=0.8, delay=0.2)
    report = ContentDuplicateChecker(config=config).run_report()

    print(f"Crawled {len(report.pages)} pages from {report.base_url}")
    for pair in report.pairs:
        print(f"{pair.similarity:.2f}  {pair.kind:5}  {pair.url_1}  <->  {pair.url_2}  {pair.note}")
    if not report.pairs:
        print("No duplicate content found.")
