from app.schemas.safety import SafetyProfile
from app.services.safety import postfall


def ids(text, profile=None):
    return {item.id for item in postfall.assess_post_fall(text, profile or SafetyProfile())}


def test_prevention_question_is_not_a_fall_event():
    assert postfall.is_fall_event('家里怎么防跌倒') is False
    assert postfall.assess_post_fall('家里怎么防跌倒', SafetyProfile()) == []
    assert postfall.is_fall_event('老人跌倒怎么办') is True


def test_consciousness_and_breathing_are_high():
    assert 'altered_consciousness' in ids('摔倒后叫不醒')
    assert 'breathing_difficulty' in ids('摔了一跤后喘不上气')


def test_head_injury_warning_signs():
    assert 'head_injury' in ids('摔倒撞到头，后来吐了一次')
    assert 'head_injury' not in ids('摔倒撞到头，没有呕吐')


def test_anticoagulant_head_strike_is_high():
    result = postfall.assess_post_fall('吃华法林摔了一跤撞到头', SafetyProfile())
    assert any(item.id == 'anticoagulant_head_strike' and item.severity == 'high' for item in result)


def test_hip_and_spine_do_not_move():
    hip = postfall.assess_post_fall('我爸摔倒了，髋部疼得站不起来', SafetyProfile())
    assert any(item.id == 'hip_fracture' and item.severity == 'high' for item in hip)
    spine = postfall.assess_post_fall('摔了一跤，腰疼得动不了，腿还发麻', SafetyProfile())
    assert any(item.id == 'spine_injury' and item.severity == 'high' for item in spine)


def test_alone_cannot_rise_and_long_lie_are_moderate():
    assert 'alone_cannot_rise' in ids('独居老人摔倒起不来')
    assert 'long_lie' in ids('在地上躺了两个小时起不来')


def test_syncope_and_recurrent_falls_are_moderate():
    assert 'syncope_fall' in ids('头晕眼前发黑摔倒了')
    assert 'recurrent_falls' in ids('最近又摔了一次')


def test_minor_fall_is_only_a_note():
    result = postfall.assess_post_fall('刚才在客厅滑了一下，没受伤', SafetyProfile())
    assert [item.id for item in result] == ['minor_fall']
    assert postfall.level_of(result) == 'L3'


def test_fixed_advice_says_do_not_lift_first():
    advice = postfall.POST_FALL_ADVICE
    assert '先不要急着把人扶起来' in advice
    assert '不要搬动' in advice and '120' in advice
