"""Write results as CSV, JSON or a Markdown summary."""

from __future__ import annotations

import csv
import html
import json
from dataclasses import asdict
from datetime import datetime, timezone
from importlib import resources
from io import StringIO
from pathlib import Path

from . import __version__
from .actions import recommend
from .models import Report

# The first three columns match v1 so existing spreadsheets keep working.
CSV_COLUMNS = ("URL_1", "URL_2", "Similarity", "Type", "Note")


def _csv_rows(rows: list[tuple[str, str, float, str, str]]) -> str:
    buf = StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for url_1, url_2, similarity, kind, note in rows:
        writer.writerow([url_1, url_2, f"{similarity:.4f}", kind, note])
    return buf.getvalue()


def csv_text(report: Report) -> str:
    return _csv_rows([(p.url_1, p.url_2, p.similarity, p.kind, p.note) for p in report.pairs])


def csv_text_from_pairs(pairs: list[dict]) -> str:
    """CSV from the ``pairs`` list of a JSON report (used when only the JSON was loaded)."""
    rows = []
    for p in pairs:
        notes = []
        if p.get("canonicalized"):
            notes.append("canonical points to the other page")
        if p.get("noindex"):
            notes.append("at least one page is noindex")
        rows.append((p["url_1"], p["url_2"], float(p["similarity"]), p.get("type", ""), "; ".join(notes)))
    return _csv_rows(rows)


def write_csv(report: Report, path: str | Path) -> Path:
    path = Path(path)
    path.write_text(csv_text(report), encoding="utf-8", newline="")
    return path


def to_dict(report: Report) -> dict:
    actions, clusters = recommend(report)
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
            "clusters": len(clusters),
            "actions": {
                "high": sum(1 for a in actions if a.priority == "high"),
                "medium": sum(1 for a in actions if a.priority == "medium"),
                "low": sum(1 for a in actions if a.priority == "low"),
            },
        },
        "actions": [a.to_dict() for a in actions],
        "clusters": [
            {
                "id": c.id,
                "primary": c.primary,
                "members": c.members,
                "kind": c.kind,
                "min_similarity": c.min_similarity,
            }
            for c in clusters
        ],
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


def _json_for_html(data: dict) -> str:
    """Serialize for a <script type=application/json> block without closing it early."""
    return (
        json.dumps(data, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


DEFAULT_ENGINE_URL = "http://127.0.0.1:8765"


def render_html(
    data: dict | None,
    *,
    live: bool = False,
    title: str = "Duplicate content report",
    token: str | None = None,
    engine_url: str = DEFAULT_ENGINE_URL,
) -> str:
    """Render the dashboard template.

    ``data`` is the dict from :func:`to_dict` (embedded for the static report)
    or ``None`` in live mode, where the page fetches it from the local server.
    The template is valid HTML on its own; rendering only fills in the title,
    the meta tags (mode, version, engine URL, token) and the JSON data block.
    ``token`` lets a report opened from disk call the local engine; omit it for
    a report you will share outside this machine.
    """
    template = resources.files("duplicatedcontentchecker.templates").joinpath("dashboard.html").read_text("utf-8")
    payload = _json_for_html(data) if data is not None else "null"
    substitutions = (
        ("<title>Duplicate content report</title>", f"<title>{html.escape(title, quote=False)}</title>"),
        (
            '<meta name="dupcheck-mode" content="static">',
            f'<meta name="dupcheck-mode" content="{"live" if live else "static"}">',
        ),
        ('<meta name="dupcheck-version" content="">', f'<meta name="dupcheck-version" content="{__version__}">'),
        (
            '<meta name="dupcheck-engine" content="">',
            f'<meta name="dupcheck-engine" content="{html.escape(engine_url)}">',
        ),
        (
            '<meta name="dupcheck-token" content="">',
            f'<meta name="dupcheck-token" content="{html.escape(token or "")}">',
        ),
        (
            '<script id="report-data" type="application/json">null</script>',
            f'<script id="report-data" type="application/json">{payload}</script>',
        ),
    )
    for marker, replacement in substitutions:
        assert marker in template, f"dashboard template is missing {marker!r}"
        template = template.replace(marker, replacement, 1)
    return template


def write_html(report: Report, path: str | Path, *, token: str | None = None) -> Path:
    path = Path(path)
    html_text = render_html(to_dict(report), title=f"Duplicate content · {report.base_url}", token=token)
    path.write_text(html_text, encoding="utf-8")
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
