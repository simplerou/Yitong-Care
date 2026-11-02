from app.schemas.diet import DietParagraph, DietTriage
from app.services.diet import checks, foods, nutrition


def test_numeric_portions_are_blocked_in_model_prose():
    assert checks.portion_issues('每天吃 200 克米饭') == ['200g']
    assert checks.portion_issues('早餐吃二两主食') == ['二两']
    assert checks.portion_issues('多吃蔬菜和优质蛋白') == []


def test_guideline_quantities_quoted_from_evidence_are_allowed():
    evidence = '食盐每日不超过 5 克，烹调油每日 25 至 30 克。'
    assert checks.portion_issues('每日食盐控制在 5 克以内', evidence) == []
    assert checks.portion_issues('每天吃 200 克米饭', evidence) == ['200g']


def test_prescription_and_extreme_diet_are_blocked():
    assert checks.prescription_issues('这个食谱能治好糖尿病') == ['治好']
    assert checks.prescription_issues('饮食不能替代药物治疗') == []
    assert checks.extreme_issues('试试生酮饮食') == ['生酮']


def test_absolute_and_diagnosis_phrases():
    assert checks.absolute_issues('必须吃蛋白粉')
    assert checks.diagnosis_issues('您患有糖尿病')


def test_paragraph_gate_combines_checks_and_allergies():
    paragraph = DietParagraph(text='每天吃 200 克米饭，这个食谱能治好糖尿病。', sources=[1])
    issues = checks.paragraph_issues(paragraph, 'L3', ['虾'])
    assert {'portion_invention', 'diet_prescription'} <= set(issues)
    allergy = DietParagraph(text='晚餐可以吃虾和青菜。', sources=[1])
    assert 'unsafe_food' in checks.paragraph_issues(allergy, 'L3', ['虾'])
    safe = DietParagraph(text='主食粗细搭配，多吃蔬菜和优质蛋白，少吃腌制品。', sources=[1])
    assert checks.paragraph_issues(safe, 'L4', []) == []


def test_low_urgency_suppression_adds_missing_referral():
    paragraph = DietParagraph(text='先在家观察观察再说。', sources=[1])
    assert 'missing_referral' in checks.paragraph_issues(paragraph, 'L2')
    assert 'missing_referral' not in checks.paragraph_issues(paragraph, 'L4')


def test_blocks_and_fixed_copy():
    assessment = nutrition.assess('咸菜配粥', *foods.extract('咸菜配粥', []), profile=__import__('app.schemas.diet', fromlist=['DietProfile']).DietProfile())
    assert '咸菜' in checks.food_block(assessment)
    assert '高盐' in checks.food_block(assessment)
    reference = foods.portion_reference()
    block = checks.portion_block(reference)
    assert '谷类' in block and '不是疾病治疗饮食处方' in block
    assert '120' in checks.EMERGENCY_CHECKLIST and '不构成疾病治疗饮食处方' in checks.DISCLAIMER
    assert '治疗饮食处方' in checks.boundary_text('prescription_diet')
    assert '生酮' in checks.boundary_text('extreme_diet')
    assert '不能替代药物' in checks.boundary_text('replace_medication')
    assert '补充剂' in checks.boundary_text('supplement_dose')


def test_emergency_text_is_deterministic_for_choking_and_allergy():
    assessment = nutrition.assess('吃虾后嘴唇肿', *foods.extract('吃虾后嘴唇肿', []), profile=__import__('app.schemas.diet', fromlist=['DietProfile']).DietProfile())
    choking = DietTriage(level='L1', rule_ids=['choking_respiratory'], required_action='call_120',
                         red_flags=['进食呛咳伴呼吸困难'], table_version=foods.TABLE_VERSION)
    text = checks.emergency_text(choking, assessment)
    assert '120' in text and '不要强行喂水' in text
    allergy = DietTriage(level='L1', rule_ids=['anaphylaxis_food'], required_action='call_120',
                         red_flags=['过敏'], table_version=foods.TABLE_VERSION)
    assert '停止进食可疑食物' in checks.emergency_text(allergy, assessment)


def test_insufficient_text_keeps_deterministic_parts():
    assessment = nutrition.assess('咸菜', *foods.extract('咸菜', []), profile=__import__('app.schemas.diet', fromlist=['DietProfile']).DietProfile())
    triage = DietTriage(level='L3', rule_ids=['hypertension_salt'], required_action='dietitian_referral',
                        red_flags=['高血压与高盐饮食'], table_version=foods.TABLE_VERSION)
    text = checks.insufficient_text(assessment, triage, 'no_hits')
    assert '咸菜' in text and '120' in text and '不构成疾病治疗饮食处方' in text


def test_missing_labels_cover_all_gaps():
    labels = checks.missing_labels(['condition_list', 'chewing_swallowing', 'full_diet_scope'])
    assert all(labels) and len(labels) == 3
