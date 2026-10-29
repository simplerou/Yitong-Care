import pytest
from app.services.chat.evidence_limits import evidence_scope_issues


@pytest.mark.parametrize('text',[
 '在继续有效文件目录中未列明杭民发〔2024〕142号。',
 '该完整目录没有包含该文件。',
 '当前片段未见该文件，因此完整目录未收录该文件。',
])
def test_excerpt_does_not_support_document_wide_absence(text):
    assert 'unverified_document_absence' in evidence_scope_issues(text,[{'text':'目录前20项。'}])


@pytest.mark.parametrize('text',[
 '当前片段未列明该文号，不能据此判断完整目录是否包含。',
 '当前片段未见该条目。',
 '无法确认该完整目录是否未列明该文件。',
])
def test_qualified_fragment_observations_and_uncertainty_are_allowed(text):
    assert not evidence_scope_issues(text,[{'text':'目录前20项。'}])


def test_explicit_document_statement_is_not_inferred_absence():
    text='本目录不包含部门联合发文。'
    assert not evidence_scope_issues(text,[{'text':text}])


def test_universal_group_must_be_explicit_in_cited_text():
    claim='该津贴面向全体户籍高龄老人。'
    assert evidence_scope_issues(claim,[{'text':'100周岁及以上老人的高龄津贴调整为每月800元。'}])==['unsupported_universal_scope']
    assert not evidence_scope_issues(claim,[{'text':claim}])
    assert not evidence_scope_issues('这不代表所有户籍老人都符合条件。',[{'text':'符合条件才能申请。'}])


def test_actual_report_scope_errors_are_reproducible_without_network():
    import json
    from pathlib import Path
    data=json.loads((Path(__file__).parents[1]/'fixtures/policy_scope_limits.json').read_text())
    for case in data:
        issues=evidence_scope_issues(case['answer'],case['evidence'])
        assert ('unsupported_universal_scope' if case['case']=='W01' else 'unverified_document_absence') in issues
