"""Deterministic nutrition risk triage. The model never sets the level."""
import re

from app.schemas.diet import DietProfile, DietTriage, NutritionAssessment
from app.services.diet import foods as food_rules

NEGATION = re.compile(r'(?:没有|没|无|未|不|否认|并非)[^。；\n]{0,4}$')

ALLERGY_WORDS = ('皮疹', '风团', '起疹子', '过敏', '瘙痒')
AIRWAY_WORDS = ('呼吸困难', '喘不上气', '喉咙紧', '嗓子紧', '嘴唇肿', '脸肿', '舌头肿', '说不出话')
CHOKE_WORDS = ('呛', '噎', '卡住')
BREATH_WORDS = ('呼吸困难', '喘不上气', '面色发紫', '憋气', '说不出话')
CONSCIOUS = ('意识模糊', '意识不清', '晕倒', '叫不醒', '昏迷')
FEVER = ('发热', '发烧', '体温高')
WEIGHT_WORDS = ('瘦了', '体重下降', '掉秤', '轻了', '裤子松了')
HYPO_WORDS = ('心慌', '出汗', '手抖', '冷汗', '头晕')
SKIP_MEAL = ('不吃饭', '不吃主食', '断食', '跳过一餐', '空腹不吃')
APPETITE = ('吃不下', '没胃口', '食欲差', '不想吃')


def _present(text: str, words) -> list[str]:
    found = []
    for word in words:
        for match in re.finditer(re.escape(word), text):
            if NEGATION.search(text[max(0, match.start() - 8):match.start()]): continue
            found.append(word); break
    return found


def triage(text: str, assessment: NutritionAssessment, profile: DietProfile) -> DietTriage:
    text = text or ''
    from app.services.diet.dialogue_state import infer_profile
    profile = infer_profile(profile, text)
    ids: list[str] = []
    allergy = _present(text, ALLERGY_WORDS)
    airway = _present(text, AIRWAY_WORDS)
    ate_recently = bool(re.search(r'吃|喝|进食', text))
    if airway and (allergy or ate_recently): ids.append('anaphylaxis_food')
    if '过敏性休克' in text: ids.append('anaphylaxis_food')
    if _present(text, CHOKE_WORDS) and _present(text, BREATH_WORDS): ids.append('choking_respiratory')
    if _present(text, CHOKE_WORDS) and _present(text, FEVER): ids.append('aspiration_fever')
    glucose_drug = any(drug in {'胰岛素', '磺脲类降糖药', '格列美脲', '格列齐特'} for drug in profile.medications)
    if glucose_drug and _present(text, CONSCIOUS) and _present(text, SKIP_MEAL):
        # Altered consciousness after a skipped meal on insulin or a sulfonylurea is a
        # hypoglycaemia emergency even without the classic sweating/tremor words.
        ids.append('hypoglycemia_severe')
    if _present(text, WEIGHT_WORDS) or re.search(r'[3三]\s*个?月.{0,6}(?:瘦|下降|掉)', text):
        ids.append('weight_loss')
    if _present(text, APPETITE) and assessment.bmi is not None and assessment.bmi < 18.5:
        ids.append('malnutrition')
    findings = {finding.id for finding in assessment.findings}
    for finding_id in ('ckd_high_protein', 'ckd_high_potassium', 'heart_failure_salt_water',
                       'gout_high_purine', 'liver_disease_alcohol', 'glucose_lowering_skip_meal',
                       'warfarin_vitamin_k', 'statin_grapefruit', 'levothyroxine_soy_calcium',
                       'quinolone_calcium_iron'):
        if finding_id in findings: ids.append(finding_id)
    if 'swallow_difficulty' in findings: ids.append('swallow_difficulty')
    if assessment.salt_load == 'high' and 'hypertension' in profile.conditions: ids.append('hypertension_salt')
    if assessment.sugar_load == 'high' and 'diabetes' in profile.conditions: ids.append('diabetes_high_sugar')
    if assessment.protein_risk: ids.append('protein_risk')
    if assessment.produce_risk: ids.append('produce_risk')
    if assessment.monotony_risk: ids.append('monotony_risk')
    if assessment.hydration_risk: ids.append('hydration_risk')
    if 'texture_risk' in findings: ids.append('texture_risk')
    if 'food_safety' in findings: ids.append('food_safety')
    if 'peptic_ulcer_irritant' in findings: ids.append('peptic_ulcer_irritant')

    order = ['anaphylaxis_food', 'choking_respiratory', 'hypoglycemia_severe', 'aspiration_fever', 'weight_loss',
             'malnutrition', 'ckd_high_protein', 'ckd_high_potassium', 'heart_failure_salt_water',
             'gout_high_purine', 'liver_disease_alcohol', 'swallow_difficulty', 'hypertension_salt',
             'diabetes_high_sugar', 'protein_risk', 'produce_risk', 'monotony_risk', 'hydration_risk',
             'texture_risk', 'food_safety', 'peptic_ulcer_irritant',
             'warfarin_vitamin_k', 'statin_grapefruit', 'levothyroxine_soy_calcium',
             'quinolone_calcium_iron', 'glucose_lowering_skip_meal']
    labels = {
        'anaphylaxis_food': '进食后过敏伴呼吸困难或喉头肿胀',
        'choking_respiratory': '进食呛咳伴呼吸困难', 'hypoglycemia_severe': '不进食后低血糖伴意识改变',
        'aspiration_fever': '呛咳后发热（可能误吸）', 'weight_loss': '近期体重明显下降',
        'malnutrition': '体重偏低且食欲差', 'ckd_high_protein': '慢性肾脏病与高蛋白摄入',
        'ckd_high_potassium': '慢性肾脏病与含钾较高食物', 'heart_failure_salt_water': '心力衰竭与盐、水摄入',
        'gout_high_purine': '痛风与高嘌呤食物', 'liver_disease_alcohol': '肝病与饮酒',
        'swallow_difficulty': '吞咽困难或呛咳史', 'hypertension_salt': '高血压与高盐饮食',
        'diabetes_high_sugar': '糖尿病与高糖食物', 'protein_risk': '蛋白质可能不足',
        'produce_risk': '蔬果与膳食纤维可能不足', 'monotony_risk': '饮食种类单一',
        'hydration_risk': '饮水不足', 'texture_risk': '咀嚼能力下降与偏硬食物',
        'food_safety': '食品安全风险', 'peptic_ulcer_irritant': '消化性溃疡与刺激性饮食',
        'warfarin_vitamin_k': '华法林与维生素 K 食物', 'statin_grapefruit': '他汀与西柚类水果',
        'levothyroxine_soy_calcium': '左甲状腺素与豆制品、钙', 'quinolone_calcium_iron': '抗菌药与钙、铁',
        'glucose_lowering_skip_meal': '降糖药与不进食',
    }
    positive = [rule for rule in order if rule in ids]
    l1 = {'anaphylaxis_food', 'choking_respiratory', 'hypoglycemia_severe'}
    l2 = {'aspiration_fever', 'weight_loss', 'malnutrition', 'ckd_high_protein', 'ckd_high_potassium',
          'heart_failure_salt_water', 'gout_high_purine', 'liver_disease_alcohol', 'swallow_difficulty',
          'glucose_lowering_skip_meal'}
    level = 'L1' if any(rule in l1 for rule in positive) else \
        'L2' if any(rule in l2 for rule in positive) else \
        'L3' if positive else 'L4'
    actions = {'L1': 'call_120', 'L2': 'dietitian_referral', 'L3': 'dietitian_referral', 'L4': 'self_care'}
    return DietTriage(level=level, rule_ids=positive, required_action=actions[level],
                      red_flags=[labels[rule] for rule in positive], table_version=food_rules.TABLE_VERSION)
