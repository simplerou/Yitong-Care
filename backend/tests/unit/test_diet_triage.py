from app.schemas.diet import DietProfile
from app.services.diet import foods, nutrition, triage


def run(question, profile=None):
    profile = profile or DietProfile()
    mentions, unknown = foods.extract(question, [])
    assessment = nutrition.assess(question, mentions, unknown, profile)
    return triage.triage(question, assessment, profile)


def test_anaphylaxis_and_choking_are_emergency():
    result = run('吃虾后嘴唇肿，喘不上气')
    assert result.level == 'L1' and 'anaphylaxis_food' in result.rule_ids
    assert result.required_action == 'call_120'
    choking = run('吃饭时呛到了，现在呼吸困难')
    assert choking.level == 'L1' and 'choking_respiratory' in choking.rule_ids


def test_negative_allergy_words_do_not_trigger():
    assert run('吃完没有起疹子也没有呼吸困难').level == 'L4'


def test_weight_loss_and_malnutrition_referral():
    assert run('最近三个月瘦了 6 斤').level == 'L2'
    malnourished = run('最近吃不下饭', DietProfile(weight_kg=40, height_cm=165))
    assert malnourished.level == 'L2' and 'malnutrition' in malnourished.rule_ids


def test_aspiration_fever_is_l2():
    result = run('前两天吃饭呛到，现在有点发热')
    assert result.level == 'L2' and 'aspiration_fever' in result.rule_ids


def test_ckd_heart_failure_gout_are_l2():
    assert run('慢性肾脏病想加蛋白粉').level == 'L2'
    assert run('心衰，爱吃咸菜').level == 'L2'
    assert run('痛风，想吃海鲜火锅').level == 'L2'


def test_drug_food_questions_are_l3_not_emergency():
    result = run('我在吃华法林，能多吃菠菜吗')
    assert result.level == 'L3' and 'warfarin_vitamin_k' in result.rule_ids


def test_salt_and_pattern_risks_are_l3():
    assert run('高血压，顿顿咸菜').level == 'L3'
    assert run('只喝粥，吃不了肉').level == 'L3'


def test_normal_meal_question_is_l4():
    assert run('晚饭吃米饭、鱼和青菜').level == 'L4'


def test_hypoglycemia_with_skipped_meal_is_emergency():
    result = run('打了胰岛素不吃饭，现在意识模糊')
    assert result.level == 'L1' and 'hypoglycemia_severe' in result.rule_ids


def test_red_flags_are_readable():
    result = run('吃虾后嘴唇肿，喘不上气')
    assert result.red_flags and '过敏' in result.red_flags[0]
    assert result.table_version == foods.TABLE_VERSION
