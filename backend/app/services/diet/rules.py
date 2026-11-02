"""Disease x food, drug x food, allergy, texture and food-safety findings.

All findings defer the final decision to a doctor or dietitian; none is a prescription.
"""
import re

from app.schemas.diet import DietProfile, FoodMention, NutritionFinding

DEFER = '请让医生或营养师核对，不要自行长期严格限制或大量补充。'
DIETITIAN = '建议到营养科或门诊评估，带上近期体重变化和检验结果。'

DRUG_ALIASES = {
    'warfarin': ('华法林',),
    'statin': ('他汀', '阿托伐他汀', '瑞舒伐他汀', '辛伐他汀', '普伐他汀', '匹伐他汀'),
    'levothyroxine': ('左甲状腺素', '优甲乐', '雷替斯'),
    'iron': ('铁剂', '硫酸亚铁', '琥珀酸亚铁', '多糖铁', '补铁'),
    'quinolone': ('左氧氟沙星', '莫西沙星', '环丙沙星', '四环素', '多西环素'),
    'insulin': ('胰岛素',),
    'sulfonylurea': ('格列美脲', '格列齐特', '格列吡嗪', '格列本脲', '格列喹酮', '磺脲'),
}
HYPOGLYCEMIA_RISK = {'insulin', 'sulfonylurea'}


def _has(text: str, words) -> bool:
    return any(word in text for word in words)


def _tags(foods: list[FoodMention]) -> set[str]:
    tags: set[str] = set()
    for food in foods: tags.update(food.flags)
    return tags


def _names(foods: list[FoodMention], flags) -> list[str]:
    return [food.name for food in foods if set(food.flags) & set(flags)]


def condition_findings(foods: list[FoodMention], profile: DietProfile, text: str) -> list[NutritionFinding]:
    conditions = set(profile.conditions)
    tags = _tags(foods)
    findings: list[NutritionFinding] = []
    protein_foods = _names(foods, {'protein'})
    if 'ckd' in conditions:
        if 'supplement' in tags or len(protein_foods) >= 3 or _has(text, ('蛋白粉', '多吃蛋白', '高蛋白', '大量吃肉')):
            findings.append(NutritionFinding(
                id='ckd_high_protein', severity='moderate', title='慢性肾脏病与高蛋白摄入',
                foods=protein_foods[:4],
                detail='肾功能下降时，蛋白质摄入总量需要由医生或营养师根据肾功能分期确定；自行加蛋白粉或大量吃肉可能加重负担。',
                action=DIETITIAN + ' 不要自行使用蛋白粉。'))
        if 'high_potassium' in tags:
            findings.append(NutritionFinding(
                id='ckd_high_potassium', severity='moderate', title='慢性肾脏病与含钾较高食物',
                foods=_names(foods, {'high_potassium'})[:4],
                detail='肾功能下降时排钾能力减弱，香蕉、橙子、土豆、菌菇和低钠盐等含钾较高的食物需要按检验结果控制。',
                action=DIETITIAN + ' 蔬菜可先切小块焯水再烹调，具体限制量由医生确定。'))
    if 'heart_failure' in conditions:
        if 'high_salt' in tags or _has(text, ('喝水多', '喝很多水', '大量饮水', '一天喝')):
            findings.append(NutritionFinding(
                id='heart_failure_salt_water', severity='moderate', title='心力衰竭与盐、水摄入',
                foods=_names(foods, {'high_salt'})[:4],
                detail='心衰患者通常需要限制盐和液体总量，但具体限量必须由医生根据心功能和用药确定。',
                action=DIETITIAN + ' 每日体重和尿量变化也要记录。'))
    if 'gout' in conditions and 'high_purine' in tags:
        findings.append(NutritionFinding(
            id='gout_high_purine', severity='moderate', title='痛风或高尿酸与高嘌呤食物',
            foods=_names(foods, {'high_purine'})[:4],
            detail='动物内脏、浓肉汤、部分海鲜和啤酒嘌呤含量高，痛风急性期尤其需要避免。',
            action='急性期请就医；平时避免上述食物，多饮水，具体由医生指导。'))
    if 'diabetes' in conditions and 'high_sugar' in tags:
        findings.append(NutritionFinding(
            id='diabetes_high_sugar', severity='note', title='糖尿病与高糖食物',
            foods=_names(foods, {'high_sugar'})[:4],
            detail='含糖饮料、甜点和蜂蜜升糖快，容易造成血糖波动。',
            action='优先白水或无糖饮品；水果分次、随餐或两餐之间吃，具体份量按血糖情况调整。'))
    if 'hypertension' in conditions and 'high_salt' in tags:
        findings.append(NutritionFinding(
            id='hypertension_salt', severity='note', title='高血压与高盐食物',
            foods=_names(foods, {'high_salt'})[:4],
            detail='腌制品、酱料和加工肉的钠含量高，不利于血压控制。',
            action='用葱姜蒜、醋、柠檬汁替代部分酱油和盐；购买包装食品时看营养成分表的钠含量。'))
    if 'peptic_ulcer' in conditions and (_has(text, ('辛辣', '浓茶', '咖啡', '酒')) or 'alcohol' in tags):
        findings.append(NutritionFinding(
            id='peptic_ulcer_irritant', severity='note', title='消化性溃疡与刺激性饮食',
            foods=_names(foods, {'alcohol'})[:3],
            detail='辛辣、浓茶、咖啡和酒精可能刺激胃黏膜，加重不适。',
            action='症状期尽量避免，规律进餐、少食多餐，具体用药按医嘱。'))
    if 'liver_disease' in conditions and 'alcohol' in tags:
        findings.append(NutritionFinding(
            id='liver_disease_alcohol', severity='moderate', title='肝病与饮酒',
            foods=_names(foods, {'alcohol'})[:3],
            detail='任何含酒精饮品都会增加肝脏负担。',
            action='建议戒酒；营养方案请由医生或营养师制定。'))
    return findings


def drug_food_findings(foods: list[FoodMention], profile: DietProfile, text: str) -> list[NutritionFinding]:
    tags = _tags(foods)
    drugs = profile.medications
    findings: list[NutritionFinding] = []

    def taking(key: str) -> bool:
        return any(any(alias in drug for alias in DRUG_ALIASES[key]) for drug in drugs)

    if taking('warfarin') and 'vitamin_k' in tags:
        findings.append(NutritionFinding(
            id='warfarin_vitamin_k', severity='moderate', title='华法林与维生素 K 食物',
            foods=_names(foods, {'vitamin_k'})[:4],
            detail='绿叶菜、纳豆、动物肝脏含维生素 K，会减弱华法林的抗凝作用；关键是保持摄入量稳定，而不是完全不吃。',
            action='保持每天蔬菜量相对稳定，不要突然大量增加或完全停止；药物是否调整请咨询医生或药师。'))
    if taking('statin') and 'grapefruit' in tags:
        findings.append(NutritionFinding(
            id='statin_grapefruit', severity='moderate', title='他汀与西柚类水果',
            foods=_names(foods, {'grapefruit'})[:3],
            detail='西柚、柚子会影响部分他汀的代谢，使药物浓度升高。',
            action='服药期间避免大量同食，具体是否可用请咨询药师。'))
    if taking('levothyroxine') and tags & {'calcium', 'plant_protein'}:
        findings.append(NutritionFinding(
            id='levothyroxine_soy_calcium', severity='moderate', title='左甲状腺素与豆制品、钙',
            foods=_names(foods, {'calcium', 'plant_protein'})[:4],
            detail='豆制品和钙剂会影响左甲状腺素吸收，降低药效。',
            action='两类食物与药物间隔约 4 小时，固定服药时间，具体按说明书和医嘱。'))
    if taking('iron') and tags & {'caffeine', 'calcium'}:
        findings.append(NutritionFinding(
            id='iron_tea_calcium', severity='note', title='铁剂与浓茶、钙剂',
            foods=_names(foods, {'caffeine', 'calcium'})[:3],
            detail='浓茶、咖啡和钙剂会降低铁吸收。',
            action='铁剂与它们间隔 1–2 小时，可搭配富含维生素 C 的蔬菜水果。'))
    if taking('quinolone') and tags & {'calcium', 'iron'}:
        findings.append(NutritionFinding(
            id='quinolone_calcium_iron', severity='moderate', title='部分抗菌药与钙、铁',
            foods=_names(foods, {'calcium', 'iron'})[:3],
            detail='喹诺酮类和四环素类抗菌药与钙、铁同服会明显降低吸收。',
            action='与奶制品、钙铁剂间隔约 2 小时，具体按说明书。'))
    if (taking('insulin') or taking('sulfonylurea')) and _has(text, ('不吃饭', '不吃主食', '断食', '空腹不吃', '跳过一餐')):
        findings.append(NutritionFinding(
            id='glucose_lowering_skip_meal', severity='high', title='降糖药与不进食',
            foods=[],
            detail='使用胰岛素或磺脲类降糖药时不进食，可能出现低血糖。',
            action='不要自行断食或跳过正餐；如进食明显减少，请联系医生调整用药，不要自行停药。'))
    return findings


def allergy_findings(foods: list[FoodMention], profile: DietProfile) -> list[NutritionFinding]:
    findings = []
    for allergy in profile.allergies:
        allergy = allergy.strip()
        if not allergy: continue
        hit = [food.name for food in foods if allergy in food.canonical or food.canonical in allergy]
        if hit:
            findings.append(NutritionFinding(
                id='allergy_declared', severity='high', title=f'已声明对「{allergy}」过敏',
                foods=hit, detail='建议中不能出现已明确过敏的食物，也不能用同类食物替代。',
                action='请完全避免该食物及其制品，购买包装食品时核对配料表。'))
    return findings


def texture_findings(foods: list[FoodMention], profile: DietProfile, text: str) -> list[NutritionFinding]:
    findings = []
    if profile.swallowing == 'choking_history' or _has(text, ('呛', '吞咽困难', '咽不下去', '喝水呛')):
        findings.append(NutritionFinding(
            id='swallow_difficulty', severity='moderate', title='吞咽困难或呛咳史',
            foods=_names(foods, {'texture_hard'})[:3],
            detail='稀薄液体和干硬、粘性大的食物容易呛咳，严重时可导致误吸。',
            action='食物做软烂、切碎或打成糊状，必要时用增稠剂；进食坐直、慢咽，反复呛咳请到康复科或营养科评估。'))
    if (profile.chewing != 'normal' or _has(text, ('牙口', '嚼不动', '假牙', '牙齿不好'))) and 'texture_hard' in _tags(foods):
        findings.append(NutritionFinding(
            id='texture_risk', severity='note', title='咀嚼能力下降与偏硬食物',
            foods=_names(foods, {'texture_hard'})[:3],
            detail='坚果整粒、糯米制品、干硬饼和大块肉对咀嚼要求高。',
            action='改为蒸、炖、剁碎或打成泥；坚果可磨粉，肉类切小丁勾芡。'))
    return findings


def safety_findings(foods: list[FoodMention], text: str) -> list[NutritionFinding]:
    findings = []
    if 'raw_risk' in _tags(foods) or _has(text, ('剩菜', '隔夜菜', '溏心蛋', '生的')):
        findings.append(NutritionFinding(
            id='food_safety', severity='note', title='食品安全提醒',
            foods=_names(foods, {'raw_risk'})[:4],
            detail='老年人胃酸分泌减少、免疫力下降，生食和放置过久的食物更容易引起肠道感染。',
            action='食物彻底加热，剩菜冷藏不超过 24 小时并彻底复热；豆角要煮熟，鸡蛋煮至凝固。'))
    if 'supplement' in _tags(foods):
        findings.append(NutritionFinding(
            id='supplement_note', severity='note', title='营养补充剂不能替代食物和药物',
            foods=_names(foods, {'supplement'})[:3],
            detail='蛋白粉、鱼油等属于补充剂，不能替代正常饮食或处方药。',
            action='是否需要补充、补充多少，请让医生或营养师根据饮食和检验结果确定。'))
    return findings


def all_findings(foods: list[FoodMention], profile: DietProfile, text: str) -> list[NutritionFinding]:
    findings = [*condition_findings(foods, profile, text),
                *drug_food_findings(foods, profile, text),
                *allergy_findings(foods, profile),
                *texture_findings(foods, profile, text),
                *safety_findings(foods, text)]
    order = {'high': 0, 'moderate': 1, 'note': 2}
    findings.sort(key=lambda item: (order[item.severity], item.id))
    return findings
