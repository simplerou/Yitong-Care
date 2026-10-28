from math import log
import pytest
from app.services.retrieval.bm25 import bm25, rrf, tokenize


def test_okapi_formula_and_length_normalization():
    scores = bm25('care', [(1, 'care'), (2, 'care care'), (3, 'other')])
    average = 4/3
    expected = log(1+(3-2+.5)/(2+.5))*2.5/(1+1.5*(.25+.75/average))
    assert scores[1] == pytest.approx(expected)
    assert scores[2] > scores[1]
    assert 3 not in scores
    scores = bm25('care', [(1, 'care'), (2, 'care other other other')])
    assert scores[1] > scores[2]
    assert bm25('care care', [(1, 'care')]) == bm25('care', [(1, 'care')])


def test_chinese_empty_and_full_corpus_ranking():
    assert '护理' in tokenize('护理服务')
    assert list(bm25('护理', [(1, '护理服务'), (2, '助餐服务')])) == [1]
    assert bm25('？！', [(1, '护理')]) == {}
    assert bm25('护理', []) == {}
    corpus = [(i, '其他内容') for i in range(100)] + [(101, '护理')]
    assert list(bm25('护理', corpus, limit=1)) == [101]


def test_rrf_overlap_duplicate_and_scale_independence():
    scores = rrf([1, 2, 2], [3, 2])
    assert scores[2] == pytest.approx(2/62)
    assert scores[2] > scores[1] == scores[3]
    assert scores[1] == pytest.approx(1/61)
    assert rrf({1:.9, 2:.1}, {2:100, 3:5}) == rrf({1:900, 2:100}, {2:.001, 3:.0005})
