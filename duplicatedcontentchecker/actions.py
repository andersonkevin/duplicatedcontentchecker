"""Turn duplicate pairs into a prioritized list of concrete actions.

A similarity score tells you *that* two pages overlap. This module says *what
to do about it*: which URL to keep, which to redirect or canonicalize, and
which pairs are already handled and only need verification.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

from .models import DuplicatePair, Page, Report

Priority = Literal["high", "medium", "low"]
PRIORITY_RANK: dict[str, int] = {"high": 0, "medium": 1, "low": 2}

NEAR_IDENTICAL = 0.95


@dataclass(slots=True)
class Cluster:
    """A connected group of duplicate pages with one recommended primary URL."""

    id: int
    primary: str
    members: list[str]
    kind: str  # "exact" if every edge is exact, otherwise "near"
    min_similarity: float

    @property
    def duplicates(self) -> list[str]:
        return [m for m in self.members if m != self.primary]


@dataclass(slots=True)
class Action:
    """One thing the operator should do."""

    priority: Priority
    code: str
    title: str
    why: str
    keep_url: str | None = None
    change_url: str | None = None
    similarity: float | None = None
    urls: list[str] = field(default_factory=list)
    cluster_id: int | None = None

    def to_dict(self) -> dict:
        return {
            "priority": self.priority,
            "code": self.code,
            "title": self.title,
            "why": self.why,
            "keep_url": self.keep_url,
            "change_url": self.change_url,
            "similarity": self.similarity,
            "urls": self.urls,
            "cluster_id": self.cluster_id,
        }


# -- clustering ---------------------------------------------------------------


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _primary_score(page: Page, canonical_votes: dict[str, int]) -> tuple:
    """Lower sorts first. Prefer: canonical target of others, no noindex,
    shallower, shorter URL, more words, alphabetical."""
    return (
        -canonical_votes.get(page.url, 0),
        1 if page.noindex else 0,
        page.depth,
        len(page.url),
        -page.word_count,
        page.url,
    )


def build_clusters(pages: list[Page], pairs: list[DuplicatePair]) -> list[Cluster]:
    if not pairs:
        return []
    by_url = {p.url: p for p in pages}
    uf = _UnionFind()
    for pair in pairs:
        uf.union(pair.url_1, pair.url_2)

    groups: dict[str, list[str]] = defaultdict(list)
    for url in {u for p in pairs for u in (p.url_1, p.url_2)}:
        groups[uf.find(url)].append(url)

    canonical_votes: dict[str, int] = defaultdict(int)
    for page in pages:
        if page.canonical and page.canonical != page.url and page.canonical in by_url:
            canonical_votes[page.canonical] += 1

    edge_kind: dict[str, list[DuplicatePair]] = defaultdict(list)
    for pair in pairs:
        edge_kind[uf.find(pair.url_1)].append(pair)

    clusters: list[Cluster] = []
    for root, members in groups.items():
        member_pages = [by_url[u] for u in members if u in by_url]
        if not member_pages:
            continue
        primary = min(member_pages, key=lambda p: _primary_score(p, canonical_votes)).url
        edges = edge_kind[root]
        kind = "exact" if all(e.kind == "exact" for e in edges) else "near"
        clusters.append(
            Cluster(
                id=0,
                primary=primary,
                members=sorted(members),
                kind=kind,
                min_similarity=min(e.similarity for e in edges),
            )
        )
    clusters.sort(key=lambda c: (-len(c.members), c.kind != "exact", c.primary))
    for i, cluster in enumerate(clusters, start=1):
        cluster.id = i
    return clusters


# -- recommendations ------------------------------------------------------------


def _member_action(
    member: Page,
    primary: Page,
    *,
    kind: str,
    similarity: float,
    canonicalized: bool,
    noindex: bool,
    transitive: bool,
    cluster_id: int,
) -> Action:
    """One concrete action for a duplicate page, always aimed at the cluster primary."""
    keep, change = primary.url, member.url
    urls = [keep, change]
    same_title = bool(member.title) and member.title.strip().lower() == primary.title.strip().lower()
    title_hint = " Both pages also share the same <title>." if same_title else ""
    via_hint = (
        " This page was flagged through another page in the same group; the similarity shown is to that page."
        if transitive
        else ""
    )
    common = {
        "keep_url": keep,
        "change_url": change,
        "similarity": similarity,
        "urls": urls,
        "cluster_id": cluster_id,
    }

    if canonicalized:
        return Action(
            priority="low",
            code="verify-canonical",
            title="Verify the existing canonical is respected",
            why=(
                "This page already declares the primary as canonical. Confirm in Search Console that it "
                "is not indexed separately; if it is, prefer a 301 redirect." + via_hint
            ),
            **common,
        )
    if noindex:
        return Action(
            priority="low",
            code="verify-noindex",
            title="Duplicate is noindex; consider a redirect instead",
            why=(
                "A noindex page still consumes crawl budget and can keep receiving links. If it has no "
                "standalone purpose, a 301 redirect to the primary passes signals along." + via_hint
            ),
            **common,
        )
    if kind == "exact":
        return Action(
            priority="high",
            code="redirect",
            title="301 redirect the duplicate to the primary URL",
            why=(
                "The main content is identical. Search engines split ranking signals between the two "
                "URLs. If both must stay reachable (print view, tracking variant), add rel=canonical on "
                "the duplicate instead." + title_hint + via_hint
            ),
            **common,
        )
    if similarity >= NEAR_IDENTICAL:
        return Action(
            priority="high",
            code="consolidate",
            title="Consolidate: redirect or canonicalize the near-identical page",
            why=(
                f"Similarity {similarity:.0%}. The pages differ only in details. Merge the unique bits into "
                "the primary, then 301 redirect this page, or keep both with rel=canonical if they serve "
                "different audiences." + title_hint + via_hint
            ),
            **common,
        )
    return Action(
        priority="medium",
        code="differentiate",
        title="Differentiate the content or canonicalize",
        why=(
            f"Similarity {similarity:.0%}. Give this page a distinct purpose: unique intro, title and H1, "
            "and sections the primary lacks. If it is a variant of the primary (color, size, region), "
            "canonicalize it to the primary." + title_hint + via_hint
        ),
        **common,
    )


def recommend(report: Report) -> tuple[list[Action], list[Cluster]]:
    """Build the action plan and clusters for a report.

    Every duplicate page gets exactly one action pointing at its cluster's
    primary URL, so the list reads as a to-do list rather than a list of pairs.
    Thin pages that are not part of any cluster get their own action.
    """
    by_url = {p.url: p for p in report.pages}
    clusters = build_clusters(report.pages, report.pairs)
    cluster_of: dict[str, Cluster] = {u: c for c in clusters for u in c.members}
    edges: dict[frozenset[str], DuplicatePair] = {frozenset((p.url_1, p.url_2)): p for p in report.pairs}

    actions: list[Action] = []
    for cluster in clusters:
        primary = by_url.get(cluster.primary)
        if primary is None:
            continue
        for url in cluster.members:
            member = by_url.get(url)
            if member is None or url == cluster.primary:
                continue
            direct = edges.get(frozenset((url, cluster.primary)))
            if direct is not None:
                pair, transitive = direct, False
            else:
                candidates = [p for key, p in edges.items() if url in key]
                pair, transitive = max(candidates, key=lambda p: p.similarity), True
            canonicalized = member.canonical == primary.url or (
                member.canonical is not None and member.canonical == primary.canonical
            )
            actions.append(
                _member_action(
                    member,
                    primary,
                    kind=pair.kind,
                    similarity=pair.similarity,
                    canonicalized=canonicalized,
                    noindex=member.noindex,
                    transitive=transitive,
                    cluster_id=cluster.id,
                )
            )

    for page in report.thin_pages:
        if page.url in cluster_of:
            continue  # already covered by a duplicate action
        actions.append(
            Action(
                priority="low",
                code="thin",
                title="Expand, merge or noindex this thin page",
                why=(
                    f"Only {page.word_count} words of main content (threshold {report.config.min_words}). "
                    "Either add substantive content, merge it into a related page with a redirect, or "
                    "noindex it if it exists for navigation only."
                ),
                change_url=page.url,
                urls=[page.url],
            )
        )

    actions.sort(key=lambda x: (PRIORITY_RANK[x.priority], -(x.similarity or 0), x.change_url or "", x.title))
    return actions, clusters
