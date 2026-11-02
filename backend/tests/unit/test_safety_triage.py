from app.schemas.safety import SafetyAssessment, SafetyProfile
from app.services.safety import hazards, postfall, triage


def run(question, profile=None):
    profile = profile or SafetyProfile()
    found, factors, level = hazards.assess(question, profile)
    assessment = SafetyAssessment(hazards=found, risk_factors=factors, risk_level=level,
                                  post_fall=postfall.assess_post_fall(question, profile),
                                  table_version=hazards.TABLE_VERSION)
    return triage.triage(question, assessment, profile)


def test_post_fall_high_overrides_risk_level():
    result = run('我爸摔倒了，髋部疼得站不起来')
    assert result.level == 'L1' and result.required_action == 'call_120'
    assert 'hip_fracture' in result.rule_ids


def test_post_fall_moderate_is_l2():
    result = run('独居老人摔倒起不来')
    assert result.level == 'L2' and 'alone_cannot_rise' in result.rule_ids


def test_high_risk_without_fall_is_l2():
    result = run('怎么防跌倒', SafetyProfile(previous_falls=2, living_alone=True))
    assert result.level == 'L2' and 'high_fall_risk' in result.rule_ids


def test_medium_risk_is_l3():
    result = run('最近走路不稳，需要拄拐')
    assert result.level == 'L3' and 'moderate_fall_risk' in result.rule_ids


def test_environment_question_is_l4():
    assert run('卫生间装扶手大概多高').level == 'L4'
    assert run('家里怎么防跌倒').level == 'L4'


def test_minor_fall_is_l3_with_readable_flag():
    result = run('老人跌倒怎么办')
    assert result.level == 'L3' and result.red_flags
    assert result.table_version == hazards.TABLE_VERSION
