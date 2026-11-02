from app.schemas.health import HealthParagraph, Triage, VitalsAssessment
from app.services.health import checks, vitals


def test_medication_instructions_are_detected_but_negations_are_allowed():
    assert checks.medication_issues('可以把氨氯地平加到两片吗') == ['加到两片']
    assert checks.medication_issues('建议每天 2 片') == ['每天 2 片']
    assert checks.medication_issues('请勿自行加量、减量或停药') == []
    assert checks.medication_issues('每天测量血压 2 次') == []


def test_diagnosis_claims_are_detected_but_qualified_statements_are_allowed():
    assert checks.diagnosis_issues('您患有糖尿病')
    assert checks.diagnosis_issues('诊断为糖尿病')
    assert checks.diagnosis_issues('不能确诊为糖尿病，需要医院复核') == []


def test_absolute_and_emergency_suppressing_phrases():
    assert checks.absolute_issues('结果完全正常，不用去医院')
    assert checks.suppression_issues('在家观察两天就行', 'L2')
    assert checks.suppression_issues('在家观察两天就行', 'L4') == []


def test_paragraph_gate_combines_safety_checks():
    unsafe = HealthParagraph(text='可以每天 2 片，基本确诊是糖尿病。', sources=[1])
    found = checks.paragraph_issues(unsafe, 'L2')
    assert 'medication_instruction' in found and 'overreach_diagnosis' in found
    safe = HealthParagraph(text='请勿自行加量、减量或停药；血压达到切点需医院复核。', sources=[1])
    assert checks.paragraph_issues(safe, 'L2') == []


def test_numeric_support_accepts_values_from_assessment_and_evidence():
    assessment = vitals.assess('早上 150/95', [], [], __import__('app.schemas.health', fromlist=['HealthProfile']).HealthProfile())
    texts = []
    for reading in assessment.readings:
        texts.extend([reading.display, reading.category, reading.reference_basis])
    good = HealthParagraph(text='本次测量 150/95 mmHg，属 1 级范围。', sources=[1])
    assert checks.numeric_support_issues([good], {1: '家庭自测血压 ≥135/85 mmHg 视为偏高'}, texts) == []
    bad = HealthParagraph(text='应控制在 120/70 mmHg 以下。', sources=[1])
    issues = checks.numeric_support_issues([bad], {1: '家庭自测血压 ≥135/85 mmHg 视为偏高'}, texts)
    assert issues and issues[0]['type'] == 'unsupported_number'


def test_numeric_support_ignores_unitless_numbers():
    paragraph = HealthParagraph(text='每天复查 2 次，连续 3 天。', sources=[1])
    assert checks.numeric_support_issues([paragraph], {1: '复测并记录'}, []) == []


def test_model_cannot_claim_a_measurement_setting_the_parser_never_saw():
    from app.schemas.health import HealthProfile
    assessment = VitalsAssessment(readings=[], primary=None, table_version=vitals.TABLE_VERSION)
    assert checks.context_claim_issues('家庭自测血压偏高，需要注意。', assessment) == []
    unknown = vitals.assess('早上 150/95', [], [], HealthProfile())
    assert checks.context_claim_issues('家庭自测血压 150/95 偏高。', unknown) == ['wrong_category']
    clinic = vitals.assess('医院血压 150/95', [], [], HealthProfile())
    assert checks.context_claim_issues('家庭自测血压 150/95 偏高。', clinic) == ['wrong_category']
    # Comparing standards is not a claim about this reading's setting.
    assert checks.context_claim_issues('家庭自测标准低于医院诊室测量，您在医院量的 150/95 需要复测。', clinic) == []


def test_emergency_text_and_insufficient_text_are_never_model_dependent():
    from app.schemas.health import Triage
    triage = Triage(level='L1', rule_ids=['chest_pain_15min'], required_action='call_120',
                    red_flags=['胸痛'], table_version=vitals.TABLE_VERSION)
    text = checks.emergency_text(triage, None)
    assert '120' in text and '不要自行服药' in text and '即使症状已经缓解' in text
    insufficient = checks.insufficient_text(None, triage, 'no_hits')
    assert '120' in insufficient and checks.DISCLAIMER not in insufficient


def test_fixed_copy_covers_the_required_sentences():
    assert '不构成诊断或处方' in checks.DISCLAIMER
    assert '请勿自行' in checks.MEDICATION_BOUNDARY
    assert '120' in checks.EMERGENCY_CHECKLIST
