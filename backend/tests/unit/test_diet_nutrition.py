from app.schemas.diet import DietProfile
from app.services.diet import foods, nutrition


def assess(question, profile=None):
    profile = profile or DietProfile()
    mentions, unknown = foods.extract(question, [])
    return nutrition.assess(question, mentions, unknown, profile)


def test_salt_load_from_pickles_and_habit_words():
    assert assess('顿顿咸菜配粥').salt_load == 'high'
    assert assess('我口味重，爱吃咸').salt_load == 'high'
    assert assess('平时吃得很清淡').salt_load == 'low'


def test_single_food_question_does_not_flag_pattern_risks():
    result = assess('糖尿病能吃香蕉吗', DietProfile(conditions=['diabetes']))
    assert result.protein_risk is False and result.produce_risk is False


def test_pattern_risks_need_multiple_foods_or_explicit_words():
    result = assess('只喝粥，吃不了肉')
    assert result.protein_risk is True
    result = assess('早饭白粥、咸菜、馒头')
    assert result.produce_risk is True and result.salt_load == 'high'
    result = assess('不吃蔬菜水果')
    assert result.produce_risk is True


def test_calcium_hydration_and_monotony_flags():
    assert assess('不喝牛奶，怕骨质疏松').calcium_risk is True
    assert assess('喝水少，一天喝不到').hydration_risk is True
    assert assess('每天就吃白粥和咸菜').monotony_risk is True


def test_bmi_is_computed_only_with_both_numbers():
    profile = DietProfile(weight_kg=40, height_cm=165)
    assert assess('最近没胃口', profile).bmi == 14.7
    assert assess('最近没胃口', DietProfile(weight_kg=40)).bmi is None


def test_risk_labels_are_human_readable():
    result = assess('顿顿咸菜，只喝粥，吃不了肉')
    labels = nutrition.risk_labels(result)
    assert '盐摄入偏高' in labels and '蛋白质可能不足' in labels
