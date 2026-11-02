from app.schemas.health import HealthProfile
from app.services.health import triage, vitals


def run(question, profile=None):
    assessment = vitals.assess(question, [], [], profile or HealthProfile())
    return triage.triage_of(assessment, question, profile)


def test_chest_pain_is_emergency():
    result = run('我爸胸口压得慌，出冷汗，十几分钟了')
    assert result.level == 'L1'
    assert 'chest_pain_15min' in result.rule_ids
    assert result.required_action == 'call_120'


def test_relieved_chest_pain_is_not_emergency():
    assert run('胸口疼，休息后已经好多了').level != 'L1'


def test_stroke_and_consciousness_and_bleeding():
    assert run('我妈突然口角歪斜，说话不清').level == 'L1'
    assert run('老人刚才晕倒了，叫不醒').level == 'L1'
    assert run('早上呕血两次').level == 'L1'
    assert run('大便发黑好几天了').level == 'L1'
    assert run('摔了一跤，髋部疼站不起来').level == 'L1'


def test_self_harm_gets_crisis_route():
    result = run('我不想活了，活着没意思')
    assert result.level == 'L1' and 'self_harm' in result.rule_ids


def test_negated_symptoms_do_not_trigger():
    assert run('没有胸痛，就是有点累').level == 'L4'
    assert run('否认黑便，胃口一般').level == 'L4'


def test_conceptual_questions_do_not_trigger_symptom_rules():
    assert run('胸痛是什么感觉').level == 'L4'
    assert run('什么是高血压').level == 'L4'


def test_crisis_values_with_and_without_symptoms():
    with_symptom = run('血压 182/122，头痛得厉害')
    assert with_symptom.level == 'L1' and 'bp_crisis_symptom' in with_symptom.rule_ids
    without = run('血压 182/122，没什么感觉')
    assert without.level == 'L2' and 'bp_crisis_no_symptom' in without.rule_ids


def test_glucose_severity_levels():
    assert run('空腹血糖 2.6，出汗心慌').level == 'L1'
    assert run('空腹血糖 3.5').level == 'L2'
    assert run('空腹血糖 7.4').level == 'L3'
    assert run('空腹血糖 12.0').level == 'L2'


def test_oxygen_and_temperature_rules():
    assert run('血氧 88%').level == 'L1'
    assert run('血氧 92%').level == 'L2'
    assert run('体温 41.2 度').level == 'L1'
    assert run('体温 38.6 度').level == 'L3'


def test_heart_rate_extremes_need_symptoms_to_be_emergency():
    assert run('心率 38，头晕眼前发黑').level == 'L1'
    assert run('心率 38，没什么感觉').level == 'L2'
    assert run('心率 45').level == 'L2'


def test_stage_one_is_outpatient_review_not_emergency():
    result = run('早上 150/95，有点头晕')
    assert result.level == 'L3' and result.required_action == 'clinic_visit'


def test_normal_reading_and_missing_reading_are_self_care():
    assert run('血压 118/76').level == 'L4'
    assert run('最近睡不好').level == 'L4'
    assert triage.triage_of(vitals.assess('血压高怎么办', [], [], HealthProfile()), '血压高怎么办').level == 'L4'


def test_rule_ids_map_to_readable_flags():
    result = run('血氧 92%')
    assert result.red_flags and '血氧' in result.red_flags[0]
    assert result.table_version == vitals.TABLE_VERSION
