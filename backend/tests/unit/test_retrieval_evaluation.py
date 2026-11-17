import pytest
from scripts.evaluate_retrieval import score

def test_recall_counts_all_relevant_items_and_missing_runs_are_blocked():
    labels=[{'id':'a','split':'holdout','relevant_chunk_ids':[1,2]},{'id':'b','split':'holdout','relevant_chunk_ids':[3]},{'id':'c','split':'holdout','relevant_chunk_ids':[4]}]
    rankings=[{'id':'a','retrieved_chunk_ids':[9,1]},{'id':'b','retrieved_chunk_ids':[]}]
    r=score(labels,rankings)
    assert r['recall_at_k']==.25 and r['micro_recall_at_k']==1/3
    assert r['mrr_at_k']==.25 and r['hit_rate_at_k']==.5
    assert r['blocked']==1 and not r['complete']
    assert score(labels,rankings,split='calibration')['recall_at_k'] is None

def test_retrieval_evaluation_rejects_duplicates_empty_gold_and_unknown_ids():
    labels=[{'id':'a','split':'holdout','relevant_chunk_ids':[]}]
    with pytest.raises(ValueError):score(labels,[])
    labels[0]['relevant_chunk_ids']=[1]
    with pytest.raises(ValueError):score(labels,[{'id':'a','retrieved_chunk_ids':[1,1]}])
    with pytest.raises(ValueError):score(labels,[{'id':'unknown','retrieved_chunk_ids':[1]}])
    assert score(labels,[{'id':'a','retrieved_chunk_ids':[1]}])['recall_at_k']==1
