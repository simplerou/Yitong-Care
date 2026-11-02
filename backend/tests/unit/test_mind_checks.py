from app.schemas.mind import MindParagraph, MindTriage
from app.services.mind import checks, emotions


def triage(level='L2'):
    return MindTriage(level=level, rule_ids=[], required_action='mental_health_referral',
                      red_flags=[], table_version=emotions.TABLE_VERSION)


def test_toxic_positivity_is_blocked():
    for text in ('想开点就好了', '别想太多', '比你惨的人多了', '坚强点'):
        assert checks.toxic_issues(text), text
    assert checks.toxic_issues('听起来你最近真的很不容易') == []


def test_diagnosis_and_medication_are_blocked():
    assert checks.diagnosis_issues('你就是抑郁症')
    assert checks.medication_issues('吃点安眠药就好了')
    assert checks.medication_issues('不要自行停药') == []
    assert checks.medication_issues('安眠药需要医生开') == []


def test_method_and_absolute_promises_are_blocked():
    assert checks.method_issues('跳楼最省事')
    assert checks.absolute_issues('一定会好，我保证')
    assert checks.absolute_issues('绝对保密，不会告诉任何人')


def test_empathy_paragraph_needs_no_citation_and_advice_needs_one():
    empathy = MindParagraph(text='听到你这么说，我很心疼。', sources=[], kind='empathy')
    assert empathy.sources == []
    try:
        MindParagraph(text='建议你每天散步。', sources=[], kind='advice')
        raise AssertionError('advice without sources must fail')
    except ValueError:
        pass


def test_paragraph_gate_blocks_unsafe_advice():
    toxic = MindParagraph(text='想开点，别想太多。', sources=[], kind='empathy')
    assert 'toxic_positivity' in checks.paragraph_issues(toxic, 'L3')
    unsafe = MindParagraph(text='吃点安眠药就行。', sources=[1], kind='advice')
    assert 'medication_advice' in checks.paragraph_issues(unsafe, 'L3')
    safe = MindParagraph(text='可以试着把担心的事写下来，分成现在能做的和做不了的。', sources=[1], kind='advice')
    assert checks.paragraph_issues(safe, 'L3') == []


def test_fixed_copy_contains_hotline_and_limits():
    text = checks.crisis_block(triage('L1'))
    assert '12356' in text and '120' in text
    assert '不能提供' in checks.boundary_text('therapy_request')
    assert '精神科医生' in checks.boundary_text('medication_request')
    assert '12356' in checks.EMERGENCY_CHECKLIST
    assert '不构成诊断' in checks.DISCLAIMER


def test_screening_block_only_for_positive_screen():
    from app.schemas.mind import MindAssessment, ScreeningResult
    positive = MindAssessment(screening=ScreeningResult(positive=True), table_version=emotions.TABLE_VERSION)
    assert '不是诊断' in checks.screening_block(positive)
    negative = MindAssessment(screening=ScreeningResult(positive=False), table_version=emotions.TABLE_VERSION)
    assert checks.screening_block(negative) == ''
