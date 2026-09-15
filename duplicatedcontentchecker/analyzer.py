"""Exact and near-duplicate detection over extracted pages."""

from __future__ import annotations

import logging
from collections import defaultdict
from itertools import combinations

from .models import DuplicatePair, Page

log = logging.getLogger(__name__)


def _annotate(pair: DuplicatePair, a: Page, b: Page) -> DuplicatePair:
    pair.canonicalized = (
        a.canonical == b.url or b.canonical == a.url or (a.canonical is not None and a.canonical == b.canonical)
    )
    pair.noindex = a.noindex or b.noindex
    return pair


def find_exact_duplicates(pages: list[Page]) -> list[DuplicatePair]:
    """Pages whose folded text hashes are identical."""
    groups: dict[str, list[Page]] = defaultdict(list)
    for page in pages:
        if page.content_hash:
            groups[page.content_hash].append(page)
    pairs: list[DuplicatePair] = []
    for group in groups.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda p: p.url)
        for a, b in combinations(group, 2):
            pairs.append(_annotate(DuplicatePair(a.url, b.url, 1.0, "exact"), a, b))
    return pairs


def find_near_duplicates(
    pages: list[Page],
    threshold: float = 0.8,
    *,
    exclude_pairs: set[tuple[str, str]] | None = None,
) -> list[DuplicatePair]:
    """Pages whose TF-IDF cosine similarity is at or above ``threshold``.

    v1 used raw term counts, which let long pages dominate and made the
    threshold hard to reason about. TF-IDF with sublinear term frequency and
    word bigrams gives a score that behaves consistently across page sizes.
    """
    if len(pages) < 2:
        return []
    # Imported lazily so ``--help`` and exact-only runs stay fast.
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    exclude_pairs = exclude_pairs or set()
    texts = [p.text for p in pages]
    try:
        vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            sublinear_tf=True,
            min_df=1,
            strip_accents="unicode",
            lowercase=True,
        )
        matrix = vectorizer.fit_transform(texts)
    except ValueError as exc:  # e.g. only stop words
        log.warning("Could not vectorize pages: %s", exc)
        return []

    sim = cosine_similarity(matrix, dense_output=False)
    pairs: list[DuplicatePair] = []
    coo = sim.tocoo()
    for i, j, score in zip(coo.row, coo.col, coo.data, strict=True):
        if i >= j or score < threshold:
            continue
        a, b = pages[i], pages[j]
        key = (a.url, b.url) if a.url < b.url else (b.url, a.url)
        if key in exclude_pairs:
            continue
        first, second = (a, b) if a.url < b.url else (b, a)
        pairs.append(_annotate(DuplicatePair(first.url, second.url, float(round(score, 4)), "near"), first, second))
    return pairs


def analyze(pages: list[Page], threshold: float = 0.8, min_words: int = 50) -> tuple[list[DuplicatePair], list[Page]]:
    """Run both detectors. Returns ``(pairs, thin_pages)``.

    Pages under ``min_words`` are excluded from near-duplicate comparison
    (short pages score high for trivial reasons) but still take part in exact
    matching, and are returned separately so the report can list them.
    """
    thin = [p for p in pages if p.word_count < min_words]
    substantial = [p for p in pages if p.word_count >= min_words and p.text]

    exact = find_exact_duplicates(pages)
    exact_keys = {(p.url_1, p.url_2) for p in exact}
    near = find_near_duplicates(substantial, threshold, exclude_pairs=exact_keys)

    pairs = exact + near
    pairs.sort(key=lambda p: (-p.similarity, p.url_1, p.url_2))
    log.info("Found %d exact and %d near-duplicate pairs (threshold %.2f)", len(exact), len(near), threshold)
    return pairs, thin
