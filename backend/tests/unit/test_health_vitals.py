import pytest

from app.schemas.health import HealthProfile, VitalsInput
from app.services.health import vitals


def assess(question, provided=None, profile=None):
    return vitals.assess(question, [], provided or [], profile or HealthProfile())


def test_blood_pressure_parsing_and_office_classification():
    result = assess('医院量的血压 160/100')
    reading = result.readings[0]
    assert reading.systolic == 160 and reading.diastolic == 100
    assert reading.context == 'clinic'
    assert reading.category_code == 'stage2'
    assert result.missing == []


def test_home_threshold_is_lower_than_clinic():
    home = assess('在家里量的血压 138/86').readings[0]
    clinic = assess('诊室血压 138/86').readings[0]
    assert home.category_code == 'stage1'
    assert clinic.category_code == 'elevated'
    assert '家庭标准低于诊室' in home.reference_basis


def test_unknown_context_is_disclosed_not_invented():
    reading = assess('早上 150/95').readings[0]
    assert reading.context == 'unknown'
    assert '测量情境未说明' in reading.display
    assert reading.category_code == 'stage1'
    # Not near a threshold that flips between home and clinic: do not stall the answer.
    assert 'measurement_context' not in assess('早上 150/95').missing
    assert 'measurement_context' in assess('135/85 算高吗').missing


def test_context_only_asked_where_it_changes_the_category():
    assert vitals.context_matters(130, 82) is True
    assert vitals.context_matters(120, 80) is False
    assert vitals.context_matters(150, 95) is False


def test_single_systolic_value_is_flagged_instead_of_guessed():
    result = assess('血压 170')
    reading = result.readings[0]
    assert reading.diastolic is None
    assert reading.category_code == 'stage2'
    assert 'diastolic_value' in result.missing
    assert '—' in reading.display


def test_glucose_units_and_conditions():
    fasting = assess('空腹血糖 7.2 mmol/L').readings[0]
    assert fasting.metric == 'fasting_glucose' and fasting.condition == 'fasting'
    assert fasting.category_code == 'diabetes_range'
    converted = assess('血糖 126 mg/dL').readings[0]
    assert converted.value == 7.0 and 'unit_converted' in converted.flags
    assert converted.unit == 'mmol/L'
    assert 'fasting_status' in assess('血糖 126 mg/dL').missing
    postprandial = assess('餐后两小时血糖 8.2').readings[0]
    assert postprandial.condition == 'postprandial_2h' and postprandial.category_code == 'igt'


def test_low_glucose_is_severe_range():
    assert assess('空腹血糖 2.8').readings[0].category_code == 'severe_low'
    assert assess('血糖 3.5').readings[0].category_code == 'low'


def test_implausible_value_is_not_classified():
    result = assess('血压 900/60')
    reading = result.readings[0]
    assert reading.category_code == 'unverified'
    assert 'implausible' in reading.flags
    assert result.implausible is True
    assert 'explicit_value' in result.missing


def test_other_metrics_and_weight_conversion():
    assert assess('血氧 88%').readings[0].category_code == 'low'
    assert assess('体温 38.6 度').readings[0].category_code == 'moderate_fever'
    assert assess('心率 45 次/分').readings[0].category_code == 'low'
    weight = assess('体重 130 斤').readings[0]
    assert weight.value == 65 and weight.unit == 'kg'


def test_provided_vitals_take_precedence_and_are_validated():
    provided = [VitalsInput(metric='blood_pressure', systolic=150, diastolic=95, unit='mmHg', context='home')]
    result = assess('今天有点头晕', provided)
    assert result.readings[0].source == 'provided'
    assert result.readings[0].category_code == 'stage1'
    assert '家庭自测' in result.readings[0].display
    with pytest.raises(ValueError):
        VitalsInput(metric='blood_pressure', systolic=90, unit='mmHg')
    with pytest.raises(ValueError):
        VitalsInput(metric='blood_pressure', systolic=90, diastolic=100, unit='mmHg')


def test_history_is_used_only_when_current_turn_has_no_reading():
    result = vitals.assess('那晚上呢', ['早上血压 150/95'], [], HealthProfile())
    assert result.readings and result.readings[0].systolic == 150


def test_clarification_asks_for_the_decisive_gap_only():
    assert '低压' in vitals.clarification(assess('血压 170'))
    assert '空腹还是餐后' in vitals.clarification(assess('血糖 8.1'))
    assert vitals.clarification(assess('血压 170/100')) is None


def test_table_version_is_stamped_on_every_reading():
    reading = assess('血压 170/100').readings[0]
    assert reading.table_version == vitals.TABLE_VERSION
    assert reading.reference_basis
