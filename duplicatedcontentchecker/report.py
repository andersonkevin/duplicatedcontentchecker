"""Write results as CSV, JSON or a Markdown summary."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

from . import __version__
from .models import Report

# The first three columns match v1 so existing spreadsheets keep working.
CSV_COLUMNS = ("URL_1", "URL_2", "Similarity", "Type", "Note")


def write_csv(report: Report, path: str | Path) -> Path:
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_COLUMNS)
        for pair in report.pairs:
            writer.writerow([pair.url_1, pair.url_2, f"{pair.similarity:.4f}", pair.kind, pair.note])
    return path


def to_dict(report: Report) -> dict:
    return {
        "tool": "duplicatedcontentchecker",
        "version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base_url": report.base_url,
        "config": asdict(report.config),
        "stats": asdict(report.stats),
        "summary": {
            "pages_crawled": len(report.pages),
            "pages_compared": len([p for p in report.pages if p.word_count >= report.config.min_words]),
            "thin_pages": len(report.thin_pages),
            "exact_duplicate_pairs": len(report.exact_pairs),
            "near_duplicate_pairs": len(report.near_pairs),
        },
        "pairs": [
            {
                "url_1": p.url_1,
                "url_2": p.url_2,
                "similarity": p.similarity,
                "type": p.kind,
                "canonicalized": p.canonicalized,
                "noindex": p.noindex,
            }
            for p in report.pairs
        ],
        "thin_pages": [{"url": p.url, "word_count": p.word_count, "title": p.title} for p in report.thin_pages],
        "pages": [
            {
                "url": p.url,
                "depth": p.depth,
                "title": p.title,
                "h1": p.h1,
                "word_count": p.word_count,
                "canonical": p.canonical,
                "noindex": p.noindex,
                "language": p.language,
                "content_hash": p.content_hash,
            }
            for p in report.pages
        ],
    }


def write_json(report: Report, path: str | Path) -> Path:
    path = Path(path)
    path.write_text(json.dumps(to_dict(report), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def markdown_summary(report: Report, limit: int = 20) -> str:
    out = StringIO()
    s = report.stats
    out.write(f"# Duplicate content report for {report.base_url}\n\n")
    out.write(f"- Pages crawled: {len(report.pages)}\n")
    out.write(f"- Fetch failures: {s.failed}\n")
    out.write(f"- Blocked by robots.txt: {s.skipped_robots} · skipped by pattern: {s.skipped_pattern}\n")
    out.write(f"- Thin pages (< {report.config.min_words} words): {len(report.thin_pages)}\n")
    out.write(f"- Exact duplicate pairs: {len(report.exact_pairs)}\n")
    out.write(f"- Near duplicate pairs (≥ {report.config.threshold:.2f}): {len(report.near_pairs)}\n")

    if report.pairs:
        out.write("\n| Similarity | Type | URL 1 | URL 2 | Note |\n|---:|---|---|---|---|\n")
        for pair in report.pairs[:limit]:
            out.write(f"| {pair.similarity:.3f} | {pair.kind} | {pair.url_1} | {pair.url_2} | {pair.note} |\n")
        if len(report.pairs) > limit:
            out.write(f"\n… and {len(report.pairs) - limit} more pairs in the full report.\n")
    else:
        out.write("\nNo duplicate content found above the threshold.\n")

    if report.thin_pages:
        out.write("\n## Thin pages\n\n")
        for page in report.thin_pages[:limit]:
            out.write(f"- {page.url} ({page.word_count} words)\n")
        if len(report.thin_pages) > limit:
            out.write(f"- … and {len(report.thin_pages) - limit} more\n")
    return out.getvalue()
