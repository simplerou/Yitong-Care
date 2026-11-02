from app.schemas.mind import MindProfile
from app.services.mind import emotions, risk


def run(text, profile=None):
    profile = profile or MindProfile()
    assessment = emotions.assessment(text, profile)
    return risk.triage(text, assessment, profile)


def test_crisis_requires_hotline_not_diagnosis():
    result = run('我不想活了')
    assert result.level == 'L1' and result.required_action == 'crisis_line'
    text = risk.crisis_text(result)
    assert '12356' in text and '120' in text
    assert '不需要一个人扛' in text
    assert '你现在安全吗' in text


def test_immediate_danger_prefers_emergency():
    result = run('我已经吃了一瓶药')
    assert result.level == 'L1' and result.required_action == 'emergency_120'


def test_depression_screen_is_l2():
    result = run('最近两周心情低落，什么都不想做')
    assert result.level == 'L2' and 'screening_positive' in result.rule_ids
    assert result.required_action == 'mental_health_referral'


def test_normal_grief_is_l3_and_prolonged_grief_is_l2():
    assert run('老伴走了以后，一直高兴不起来').level == 'L3'
    assert 'grief_prolonged' in run('老伴走了一年，还是吃不下睡不着').rule_ids


def test_loneliness_is_l3_and_sleep_ladder():
    assert run('一个人住，没人说话').level == 'L3'
    assert run('最近睡不好').level == 'L3'
    assert run('整夜睡不着，白天没精神').level == 'L2'


def test_education_question_is_l4():
    assert run('老年人为什么容易失眠').level == 'L4'


def test_safety_plan_and_referral_text():
    plan = risk.safety_plan_text()
    assert any('12356' in step for step in plan)
    triage = run('最近两周心情低落，什么都不想做')
    referral = risk.referral_text(triage)
    assert '精神科' in referral or '心理科' in referral
    assert '12356' in risk.referral_text(run('我不想活了'))
