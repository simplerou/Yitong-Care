"""User-only diet dialogue state. Conditions and allergies are inferred only from user words."""
import re

from app.schemas.diet import DietDialogueState, DietProfile

CONDITION_WORDS = {
    '高血压': 'hypertension', '血压高': 'hypertension',
    '糖尿病': 'diabetes', '血糖高': 'diabetes',
    '肾病': 'ckd', '肾衰': 'ckd', '肾功能不全': 'ckd', '透析': 'ckd',
    '慢性肾脏病': 'ckd', 'CKD': 'ckd', 'ckd': 'ckd',
    '心衰': 'heart_failure', '心功能不全': 'heart_failure',
    '痛风': 'gout', '尿酸高': 'gout',
    '慢阻肺': 'copd', '中风': 'stroke_history', '脑梗': 'stroke_history',
    '胃溃疡': 'peptic_ulcer', '消化性溃疡': 'peptic_ulcer',
    '肝病': 'liver_disease', '肝硬化': 'liver_disease',
}
DRUG_WORDS = {
    '华法林': '华法林', '他汀': '他汀', '阿托伐他汀': '他汀', '瑞舒伐他汀': '他汀',
    '优甲乐': '左甲状腺素', '左甲状腺素': '左甲状腺素',
    '铁剂': '铁剂', '补铁': '铁剂', '硫酸亚铁': '铁剂',
    '左氧氟沙星': '左氧氟沙星', '莫西沙星': '莫西沙星',
    '胰岛素': '胰岛素', '格列': '磺脲类降糖药',
}
TOPICS = {
    '一日三餐': 'meal_plan', '怎么搭配': 'meal_plan', '吃什么': 'meal_plan', '食谱': 'meal_plan',
    '蛋白质': 'protein', '蛋白': 'protein', '补钙': 'protein',
    '盐': 'salt_control', '咸': 'salt_control', '油': 'salt_control',
    '水果': 'fruit_staple', '主食': 'fruit_staple', '粗粮': 'fruit_staple',
    '牙口': 'texture', '嚼': 'texture', '吞咽': 'texture', '呛': 'texture',
    '剩菜': 'food_safety', '隔夜': 'food_safety', '生食': 'food_safety',
}
ALLERGY_HINT = re.compile(r'(?:对)?([\u4e00-\u9fff]{1,6})(?:过敏|不能吃|吃了不舒服)')


def infer_profile(profile: DietProfile, text: str) -> DietProfile:
    """Merge conditions/allergies/texture/drug names stated in free text into the profile."""
    text = text or ''
    conditions = list(profile.conditions)
    for word, code in CONDITION_WORDS.items():
        if word in text and code not in conditions: conditions.append(code)
    allergies = list(profile.allergies)
    for match in ALLERGY_HINT.finditer(text):
        value = match.group(1).strip()
        if value and value not in allergies: allergies.append(value)
    chewing = profile.chewing
    if re.search(r'牙口不好|嚼不动|咬不动|假牙|牙齿不好', text): chewing = 'difficult'
    swallowing = profile.swallowing
    if re.search(r'吞咽困难|喝水呛|老是呛|反复呛', text): swallowing = 'choking_history'
    medications = list(profile.medications)
    for word, canonical in DRUG_WORDS.items():
        if word in text and canonical not in medications: medications.append(canonical)
    return profile.model_copy(update={'conditions': conditions, 'allergies': allergies,
                                      'chewing': chewing, 'swallowing': swallowing,
                                      'medications': medications})


def advance(state: DietDialogueState, text: str, profile: DietProfile | None = None) -> DietDialogueState:
    state = state.model_copy(deep=True)
    if re.search(r'换个人|重新开始|换个话题', text): state = DietDialogueState()
    for word, topic in TOPICS.items():
        if word in text: state.topic = topic
    effective = infer_profile(profile or DietProfile(), text)
    for condition in effective.conditions:
        if condition not in state.conditions: state.conditions.append(condition)
    for allergy in effective.allergies:
        if allergy not in state.allergies: state.allergies.append(allergy)
    state.chewing = effective.chewing
    state.swallowing = effective.swallowing
    return state


def build_dialogue(texts, base: DietDialogueState | None = None,
                   profile: DietProfile | None = None) -> DietDialogueState:
    state = base or DietDialogueState()
    for text in texts:
        state = advance(state, text, profile)
    return state
