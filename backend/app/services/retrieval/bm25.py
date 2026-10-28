"""Scoped BM25 Okapi and reciprocal rank fusion (one-based ranks)."""
from collections import Counter
from math import log
import re
import jieba


def tokenize(text: str) -> list[str]:
    return [word for word in jieba.cut(text.lower(), HMM=False)
            if re.search(r"[a-z0-9\u4e00-\u9fff]", word)]


def bm25(query: str, corpus: list[tuple[int, str]], limit: int = 60,
         k1: float = 1.5, b: float = .75) -> dict[int, float]:
    terms = set(tokenize(query))
    documents = [(key, Counter(tokenize(text))) for key, text in corpus]
    count = len(documents)
    average = sum(sum(tokens.values()) for _, tokens in documents) / count if count else 0
    if not average or not terms: return {}
    frequency = Counter(term for _, tokens in documents for term in terms if term in tokens)
    scores = {}
    for key, tokens in documents:
        length = sum(tokens.values())
        score = 0.
        for term in terms:
            tf = tokens[term]
            if tf:
                idf = log(1 + (count - frequency[term] + .5) / (frequency[term] + .5))
                score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * length / average))
        if score > 0: scores[key] = score
    return dict(sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit])


def rrf(*rankings, k: int = 60) -> dict[int, float]:
    scores = Counter()
    for ranking in rankings:
        for rank, key in enumerate(dict.fromkeys(ranking), 1):
            scores[key] += 1 / (k + rank)
    return dict(scores)
