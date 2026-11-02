from app.schemas.diet import DietProfile
from app.services.diet import foods, rules


def findings(question, profile=None):
    profile = profile or DietProfile()
    mentions, _ = foods.extract(question, [])
    return {item.id for item in rules.all_findings(mentions, profile, question)}


def test_ckd_limits_protein_and_potassium():
    assert 'ckd_high_protein' in findings('想每天加两勺蛋白粉', DietProfile(conditions=['ckd']))
    assert 'ckd_high_potassium' in findings('每天吃香蕉和土豆', DietProfile(conditions=['ckd']))
    assert 'ckd_high_potassium' not in findings('每天吃香蕉', DietProfile())


def test_heart_failure_gout_and_liver_rules():
    assert 'heart_failure_salt_water' in findings('爱吃咸菜', DietProfile(conditions=['heart_failure']))
    assert 'gout_high_purine' in findings('吃动物内脏和浓肉汤', DietProfile(conditions=['gout']))
    assert 'liver_disease_alcohol' in findings('每天喝白酒', DietProfile(conditions=['liver_disease']))


def test_diabetes_and_hypertension_food_rules():
    assert 'diabetes_high_sugar' in findings('爱喝含糖饮料', DietProfile(conditions=['diabetes']))
    assert 'hypertension_salt' in findings('顿顿咸菜', DietProfile(conditions=['hypertension']))


def test_drug_food_rules_only_fire_with_the_drug():
    warfarin = DietProfile(medications=['华法林'])
    assert 'warfarin_vitamin_k' in findings('多吃菠菜', warfarin)
    assert 'warfarin_vitamin_k' not in findings('多吃菠菜', DietProfile())
    assert 'statin_grapefruit' in findings('吃他汀，能喝柚子汁吗', DietProfile(medications=['他汀']))
    assert 'levothyroxine_soy_calcium' in findings('优甲乐和豆浆一起喝', DietProfile(medications=['左甲状腺素']))
    assert 'iron_tea_calcium' in findings('铁剂和浓茶一起', DietProfile(medications=['铁剂']))


def test_glucose_lowering_drug_with_skipped_meal_is_high():
    result = rules.all_findings([], DietProfile(medications=['胰岛素']), '打了胰岛素不吃饭行吗')
    assert any(item.id == 'glucose_lowering_skip_meal' and item.severity == 'high' for item in result)


def test_declared_allergy_is_flagged():
    result = rules.all_findings(foods.extract('晚饭吃虾', [])[0], DietProfile(allergies=['虾']), '晚饭吃虾')
    assert any(item.id == 'allergy_declared' and item.severity == 'high' for item in result)


def test_texture_and_food_safety_rules():
    profile = DietProfile(chewing='difficult', swallowing='choking_history')
    result = rules.all_findings(foods.extract('吃坚果和汤圆', [])[0], profile, '牙口不好，还老是呛')
    ids = {item.id for item in result}
    assert 'swallow_difficulty' in ids and 'texture_risk' in ids
    safety = rules.all_findings(foods.extract('昨天的剩菜还能吃吗', [])[0], DietProfile(), '昨天的剩菜还能吃吗')
    assert any(item.id == 'food_safety' for item in safety)


def test_supplement_note_is_not_a_recommendation():
    result = rules.all_findings(foods.extract('每天喝蛋白粉', [])[0], DietProfile(), '每天喝蛋白粉')
    note = next(item for item in result if item.id == 'supplement_note')
    assert '不能替代' in note.detail
