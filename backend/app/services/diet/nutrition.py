"""Dietary pattern assessment: salt/oil/sugar load, protein and produce risks, BMI."""
import re

from app.schemas.diet import DietProfile, FoodMention, NutritionAssessment
from app.services.diet import foods as food_rules
from app.services.diet import rules


def _has(text: str, words) -> bool:
    return any(word in text for word in words)


def _count(foods: list[FoodMention], flags) -> int:
    return sum(1 for food in foods if set(food.flags) & set(flags))


def assess(text: str, mentions: list[FoodMention], unknown: list[str], profile: DietProfile) -> NutritionAssessment:
    # Conditions and drug names stated in the question are part of the profile.
    from app.services.diet.dialogue_state import infer_profile
    profile = infer_profile(profile, text)
    tags = food_rules.flags_of(mentions)
    salt_foods = _count(mentions, {'high_salt'})
    fat_foods = _count(mentions, {'high_fat'})
    sugar_foods = _count(mentions, {'high_sugar'})
    salt_load = 'unknown'
    if salt_foods >= 1 or _has(text, ('口味重', '爱吃咸', '顿顿咸菜', '重口味', '咸一点')):
        salt_load = 'high'
    elif _has(text, ('清淡', '少盐', '控盐')):
        salt_load = 'low'
    oil_load = 'unknown'
    if fat_foods >= 2 or _has(text, ('爱吃肥肉', '经常油炸', '天天油条')):
        oil_load = 'high'
    elif fat_foods == 1:
        oil_load = 'moderate'
    elif _has(text, ('少油', '清淡')):
        oil_load = 'low'
    sugar_load = 'unknown'
    if sugar_foods >= 1 or _has(text, ('含糖饮料', '爱喝可乐', '爱喝甜')):
        sugar_load = 'high'
    elif _has(text, ('无糖', '不加糖')):
        sugar_load = 'low'

    has_food = bool(mentions)
    # A single food question should not be turned into a dietary-pattern verdict.
    protein_risk = bool(len(mentions) >= 3 and 'protein' not in tags) or _has(
        text, ('吃不了肉', '嚼不动肉', '只喝粥', '不吃肉', '很少吃肉', '牙口不好'))
    produce_risk = bool(len(mentions) >= 3 and not ({'vegetable', 'fruit'} & tags)) or _has(
        text, ('不吃菜', '不吃蔬菜', '不吃水果', '很少吃菜'))
    calcium_risk = _has(text, ('不喝奶', '不喝牛奶', '骨质疏松', '补钙', '腿抽筋'))
    hydration_risk = _has(text, ('喝水少', '不爱喝水', '不想喝水', '一天喝不到', '饮水少'))
    monotony_risk = _has(text, ('只吃', '每天都吃', '天天吃', '就吃')) and len(mentions) <= 3

    value = food_rules.bmi(profile.weight_kg, profile.height_cm)
    if value is not None and value < 18.5: monotony_risk = monotony_risk or _has(text, ('瘦', '吃不下', '没胃口'))

    findings = rules.all_findings(mentions, profile, text)
    return NutritionAssessment(foods=mentions, unknown_foods=unknown, findings=findings,
                               salt_load=salt_load, oil_load=oil_load, sugar_load=sugar_load,
                               protein_risk=protein_risk, produce_risk=produce_risk,
                               calcium_risk=calcium_risk, hydration_risk=hydration_risk,
                               monotony_risk=monotony_risk, bmi=value,
                               table_version=food_rules.TABLE_VERSION)


def risk_labels(assessment: NutritionAssessment) -> list[str]:
    labels = []
    if assessment.salt_load == 'high': labels.append('盐摄入偏高')
    if assessment.oil_load == 'high': labels.append('油摄入偏高')
    if assessment.sugar_load == 'high': labels.append('糖摄入偏高')
    if assessment.protein_risk: labels.append('蛋白质可能不足')
    if assessment.produce_risk: labels.append('蔬果可能不足')
    if assessment.calcium_risk: labels.append('钙摄入需关注')
    if assessment.hydration_risk: labels.append('饮水可能不足')
    if assessment.monotony_risk: labels.append('饮食种类单一')
    if assessment.bmi is not None and assessment.bmi < 18.5: labels.append('体重偏低')
    return labels
