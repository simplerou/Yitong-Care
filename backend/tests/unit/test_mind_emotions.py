from app.schemas.mind import MindProfile
from app.services.mind import emotions


def assess(text, profile=None):
    return emotions.assessment(text, profile or MindProfile())


def ids(result):
    return {signal.id for signal in result.signals}


def test_risk_levels_for_ideation_plan_and_act():
    assert assess('我不想活了').risk_level == 'high'
    assert assess('我已经想好方法，也写了遗书').risk_level == 'critical'
    assert assess('我已经吃药了').risk_level == 'critical'


def test_negated_risk_words_do_not_raise_risk():
    assert assess('我没有想死，就是最近很累').risk_level == 'low'
    assert assess('不会自杀的，只是睡不着').risk_level == 'low'


def test_phq2_style_screen_needs_mood_and_anhedonia():
    positive = assess('最近两周心情低落，什么都不想做')
    assert positive.screening.positive is True
    assert positive.risk_level == 'medium'
    partial = assess('最近心情不太好')
    assert partial.screening.positive is False


def test_triggers_and_protective_factors():
    result = assess('老伴走了以后，孩子常来看我，还有只猫')
    labels = {signal.label for signal in result.signals}
    assert '丧偶或亲友离世' in labels
    assert '有家人或朋友可依靠' in labels or '有宠物或爱好' in labels


def test_recent_loss_profile_counts_as_trigger():
    result = assess('最近总是高兴不起来', MindProfile(recent_loss=True))
    assert 'loss' in ids(result)


def test_risk_labels_are_readable():
    labels = emotions.risk_labels(assess('我不想活了'))
    assert any('自杀' in label for label in labels)
