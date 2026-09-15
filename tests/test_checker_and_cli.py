import csv
import json

import pytest

from duplicatedcontentchecker import ContentDuplicateChecker, CrawlConfig
from duplicatedcontentchecker.cli import main

from .conftest import FakeFetcher


def test_v1_api_still_works(simple_site, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    checker = ContentDuplicateChecker(base_url="https://example.com", max_depth=3, fetcher=FakeFetcher(simple_site))
    checker.run()
    assert (tmp_path / "duplicate_report.csv").exists()
    assert checker.visited_urls
    assert checker.content_texts
    assert any(s[2] == 1.0 for s in checker.similarity_scores)
    with (tmp_path / "duplicate_report.csv").open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0].keys() >= {"URL_1", "URL_2", "Similarity"}
    exact = [r for r in rows if r["Type"] == "exact"]
    assert {exact[0]["URL_1"], exact[0]["URL_2"]} == {
        "https://example.com/blog/post-1",
        "https://example.com/blog/post-1-copy",
    }


def test_config_and_run_report(simple_site):
    cfg = CrawlConfig("https://example.com", max_depth=3, threshold=0.7, min_words=20)
    report = ContentDuplicateChecker(config=cfg, fetcher=FakeFetcher(simple_site)).run_report()
    assert len(report.pages) == len(simple_site)
    assert report.exact_pairs and report.near_pairs
    near = report.near_pairs[0]
    assert {near.url_1, near.url_2} == {"https://example.com/about", "https://example.com/photo"}
    assert [p.url for p in report.thin_pages] == ["https://example.com/short"]


def test_constructor_rejects_mixed_arguments():
    with pytest.raises(TypeError):
        ContentDuplicateChecker("https://example.com", config=CrawlConfig("https://example.com"))
    with pytest.raises(TypeError):
        ContentDuplicateChecker()


def test_config_validation():
    with pytest.raises(ValueError):
        CrawlConfig("example.com")
    with pytest.raises(ValueError):
        CrawlConfig("https://example.com", threshold=1.5)
    with pytest.raises(ValueError):
        CrawlConfig("https://example.com", max_pages=0)


def test_cli_writes_reports_and_summary(simple_site, tmp_path, capsys):
    csv_path = tmp_path / "out.csv"
    json_path = tmp_path / "out.json"
    code = main(
        ["https://example.com", "-d", "3", "-o", str(csv_path), "--json", str(json_path), "-q"],
        fetcher=FakeFetcher(simple_site),
    )
    assert code == 0
    assert csv_path.exists()
    data = json.loads(json_path.read_text())
    assert data["version"]
    assert data["summary"]["pages_crawled"] == len(simple_site)
    assert data["summary"]["exact_duplicate_pairs"] == 1
    assert data["config"]["max_depth"] == 3
    out = capsys.readouterr().out
    assert "Duplicate content report for https://example.com" in out
    assert "Exact duplicate pairs: 1" in out


def test_cli_fail_on_duplicates(simple_site, tmp_path):
    code = main(
        ["https://example.com", "-d", "3", "-o", str(tmp_path / "r.csv"), "-q", "--no-summary", "--fail-on-duplicates"],
        fetcher=FakeFetcher(simple_site),
    )
    assert code == 1


def test_cli_rejects_bad_threshold(tmp_path):
    with pytest.raises(SystemExit) as exc:
        main(["https://example.com", "-t", "2", "-o", str(tmp_path / "r.csv")], fetcher=FakeFetcher({}))
    assert exc.value.code == 2


def test_cli_html_embeds_token_unless_portable(simple_site, tmp_path, monkeypatch):
    monkeypatch.setenv("DUPCHECK_TOKEN_FILE", str(tmp_path / "token"))
    html_path = tmp_path / "r.html"
    main(
        ["https://example.com", "-o", str(tmp_path / "r.csv"), "--html", str(html_path), "-q", "--no-summary"],
        fetcher=FakeFetcher(simple_site),
    )
    token = (tmp_path / "token").read_text().strip()
    assert f'content="{token}"' in html_path.read_text(encoding="utf-8")
    main(
        [
            "https://example.com",
            "-o",
            str(tmp_path / "r.csv"),
            "--html",
            str(html_path),
            "--portable",
            "-q",
            "--no-summary",
        ],
        fetcher=FakeFetcher(simple_site),
    )
    assert '<meta name="dupcheck-token" content="">' in html_path.read_text(encoding="utf-8")
