from app.schemas.safety import SafetyProfile
from app.services.safety import hazards


def assess(question, profile=None):
    return hazards.assess(question, profile or SafetyProfile())


def test_bathroom_hazard_does_not_leak_into_stairs():
    found, _, _ = assess('卫生间装扶手大概多高')
    assert [item.id for item in found] == ['bath_grab_bar']
    assert found[0].room == '卫生间'


def test_hazards_are_grouped_by_room():
    found, _, _ = assess('卧室光线暗，地上还有地毯')
    ids = {item.id for item in found}
    assert 'home_light' in ids and 'bedroom_clutter' in ids
    assert all(item.room in {'卧室', '全屋'} for item in found)


def test_risk_factors_from_profile_and_text():
    profile = SafetyProfile(previous_falls=2, living_alone=True, mobility='cane')
    _, factors, level = assess('怎么防跌倒', profile)
    ids = {item.id for item in factors}
    assert {'previous_falls', 'living_alone', 'gait_balance'} <= ids
    assert level == 'high'


def test_fall_count_is_parsed_from_text():
    assert hazards.fall_count('去年摔了两次') == 2
    assert hazards.fall_count('上个月摔过一次') == 1
    assert hazards.fall_count('没摔过') == 0
    _, _, level = assess('最近走路不稳，摔过两次')
    assert level == 'high'


def test_medium_risk_from_single_strong_factor():
    _, _, level = assess('最近走路不稳，需要拄拐')
    assert level == 'medium'
    _, factors, level = assess('独居老人起夜')
    assert {'living_alone', 'night_toilet'} <= {item.id for item in factors}
    assert level == 'medium'


def test_low_risk_for_a_simple_environment_question():
    _, _, level = assess('卫生间扶手装在什么位置')
    assert level == 'low'


def test_drug_factors_are_detected_from_profile():
    _, factors, _ = assess('总是头晕', SafetyProfile(medications=['阿普唑仑']))
    ids = {item.id for item in factors}
    assert 'sedative' in ids and 'dizziness' in ids


def test_table_version_is_stamped():
    assert hazards.TABLE_VERSION.startswith('safety-home-')
