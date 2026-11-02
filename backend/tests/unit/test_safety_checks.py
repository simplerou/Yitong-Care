from app.schemas.safety import SafetyAssessment, SafetyParagraph, SafetyTriage
from app.services.safety import checks, hazards, postfall


def assessment(question, profile=None):
    from app.schemas.safety import SafetyProfile
    profile = profile or SafetyProfile()
    found, factors, level = hazards.assess(question, profile)
    return SafetyAssessment(hazards=found, risk_factors=factors, risk_level=level,
                            post_fall=postfall.assess_post_fall(question, profile),
                            table_version=hazards.TABLE_VERSION)


def test_rushing_to_lift_is_blocked_but_refusal_is_allowed():
    assert checks.move_issues('赶紧扶起来') == ['赶紧扶起']
    assert checks.move_issues('不要马上扶起来，先观察') == []


def test_dimensions_must_be_quoted_from_evidence():
    assert checks.dimension_issues('扶手装在 75 cm 高') == ['75cm']
    assert checks.dimension_issues('扶手常见 70–80 cm', '常见高度 70–80 cm') == []
    assert checks.dimension_issues('把手放在 70 cm', '常见高度 70–80 cm') == ['70cm']


def test_rehab_quote_and_diagnosis_patterns():
    assert checks.rehab_issues('每天做 3 组，每次 20 个')
    assert checks.construction_issues('包工包料报价多少钱')
    assert checks.diagnosis_issues('就是骨折了')
    assert checks.diagnosis_issues('可能提示髋部损伤，需要影像确认') == []


def test_paragraph_gate_combines_checks():
    paragraph = SafetyParagraph(text='赶紧扶起来，肯定就是骨折了。', sources=[1])
    issues = checks.paragraph_issues(paragraph, 'L3')
    assert {'unsafe_move', 'overreach_diagnosis'} <= set(issues)
    safe = SafetyParagraph(text='先不要急着扶起来，观察意识和疼痛部位，怀疑髋部损伤时拨打 120。', sources=[1])
    assert checks.paragraph_issues(safe, 'L1', '') == []


def test_supported_dimension_passes_the_gate():
    paragraph = SafetyParagraph(text='马桶旁扶手常见高度 70–80 cm。', sources=[1])
    support = '常见高度 70–80 cm'
    assert 'unsupported_dimension' not in checks.paragraph_issues(paragraph, 'L4', support)


def test_low_urgency_suppression_adds_missing_referral():
    paragraph = SafetyParagraph(text='先在家观察观察再说。', sources=[1])
    assert 'missing_referral' in checks.paragraph_issues(paragraph, 'L2')
    assert 'missing_referral' not in checks.paragraph_issues(paragraph, 'L4')


def test_blocks_and_fixed_copy():
    data = assessment('卫生间装扶手大概多高')
    assert '卫生间' in checks.hazards_block(data)
    assert '跌倒风险因素' in checks.risk_block(data)
    assert '120' in checks.EMERGENCY_CHECKLIST
    assert '不构成医疗诊断' in checks.DISCLAIMER
    assert '康复训练处方' in checks.boundary_text('rehab_prescription')
    assert '报价' in checks.boundary_text('construction_quote')
    assert '约束' in checks.boundary_text('restraint')


def test_emergency_text_never_tells_family_to_stand_the_person_up():
    data = assessment('我爸摔倒了，髋部疼得站不起来')
    triage = SafetyTriage(level='L1', rule_ids=['hip_fracture'], required_action='call_120',
                          red_flags=['疑似髋部骨折'], table_version=hazards.TABLE_VERSION)
    text = checks.emergency_text(triage, data)
    assert '120' in text and '不要搬动' in text
    assert '先不要急着把人扶起来' in text
    assert '赶紧扶起' not in text


def test_insufficient_text_keeps_deterministic_parts():
    data = assessment('独居老人摔倒起不来')
    triage = SafetyTriage(level='L2', rule_ids=['alone_cannot_rise'], required_action='safety_referral',
                          red_flags=['独居且无法起身'], table_version=hazards.TABLE_VERSION)
    text = checks.insufficient_text(data, triage, 'no_hits')
    assert '不要急着' in text and '120' in text and '不构成医疗诊断' in text
