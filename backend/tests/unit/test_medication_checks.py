from app.schemas.medication import MedicationParagraph, MedicationTriage
from app.services.medication import checks, drugs


def test_numeric_doses_are_always_blocked():
    assert checks.dosage_issues('每次 5 mg，每日两次') == ['5 mg']
    assert checks.dosage_issues('每天吃 2 片') == ['2 片']
    assert checks.dosage_issues('血糖 150/95') == []
    assert checks.dosage_issues('每天测量 2 次') == []


def test_dose_change_requests_are_blocked_but_negations_allowed():
    assert checks.dose_change_issues('可以把氨氯地平加到两片吗') == ['加到两片']
    assert checks.dose_change_issues('建议先停药观察') == ['停药']
    assert checks.dose_change_issues('请勿自行加量、减量或停药') == []


def test_interaction_assertions_are_blocked():
    for text in ('这两种药可以一起吃', '没有相互作用', '同时服用没问题', '绝对安全'):
        assert checks.interaction_assertions(text), text
    assert checks.interaction_assertions('存在出血风险，需让医生或药师核对') == []


def test_substitution_and_diagnosis_patterns():
    assert checks.substitution_issues('可以用布洛芬代替阿司匹林')
    assert checks.diagnosis_issues('您患有高血压')
    assert checks.diagnosis_issues('不能确诊为药物性肝损伤') == []


def test_paragraph_gate_combines_checks():
    unsafe = MedicationParagraph(text='建议每天 2 片，可以和华法林一起吃。', sources=[1])
    issues = checks.paragraph_issues(unsafe, 'L3')
    assert {'dose_number', 'interaction_claim'} <= set(issues)
    safe = MedicationParagraph(text='华法林与阿司匹林同用会增加出血风险，请让医生或药师核对。', sources=[1])
    assert checks.paragraph_issues(safe, 'L3') == []


def test_low_urgency_suppression_adds_missing_referral():
    paragraph = MedicationParagraph(text='先在家观察观察再看。', sources=[1])
    assert 'missing_referral' in checks.paragraph_issues(paragraph, 'L2')
    assert 'missing_referral' not in checks.paragraph_issues(paragraph, 'L4')


def test_blocks_and_fixed_copy():
    assessment = drugs.assess('华法林和阿司匹林', [])
    block = checks.interaction_block(assessment)
    assert '需尽快核对' in block and '华法林' in block
    assert '让医生或药师核对' in block or '联系开药医生或药师' in block
    assert '二甲双胍' in checks.drug_block(drugs.assess('二甲双胍', []))
    assert '常见服用时间' in checks.drug_block(drugs.assess('二甲双胍', []))
    assert '120' in checks.EMERGENCY_CHECKLIST
    assert '不构成处方' in checks.DISCLAIMER
    assert '不能提供加量' in checks.boundary_text('dose_change')
    assert '是否停药' in checks.boundary_text('stop_or_switch')


def test_emergency_text_is_deterministic():
    assessment = drugs.assess('吃了阿莫西林后喘不上气', [])
    triage = MedicationTriage(level='L1', rule_ids=['airway_swelling'], required_action='call_120',
                              red_flags=['过敏伴呼吸困难'], table_version=drugs.TABLE_VERSION)
    text = checks.emergency_text(triage, assessment)
    assert '120' in text and '带上所有正在服用的药物' in text and '不构成处方' in text


def test_insufficient_text_keeps_deterministic_parts():
    assessment = drugs.assess('华法林和阿司匹林', [])
    triage = drugs.triage(assessment, '华法林和阿司匹林')
    text = checks.insufficient_text(assessment, triage, 'no_hits')
    assert '相互作用' in text and '120' in text and '不构成处方' in text


def test_missing_labels_cover_all_gaps():
    labels = checks.missing_labels(['drug_list', 'dose_frequency', 'full_medication_scope'])
    assert all(labels) and len(labels) == 3
