"""Deterministic diet safety checks and fixed copy.

Portions, prescriptions, allergy conflicts and emergency wording are owned by code,
so a model failure can never turn a menu into a diet prescription.
"""
import re
import unicodedata

from app.schemas.diet import DietParagraph, DietTriage, NutritionAssessment, PortionReference

DISCLAIMER = ('以上为膳食营养建议，不构成疾病治疗饮食处方，不能替代营养科或医生面诊；'
              '慢病、肾功能异常或吞咽困难者的份量与质地需个体化确定。')
EMERGENCY_CHECKLIST = ('进食后如出现呼吸困难、喉头或口唇肿胀、面色发紫、说不出话、意识改变，'
                       '请立即拨打 120；进食呛咳后发热、咳嗽反复，请尽快就医。')
PORTION_DISCLAIMER = '以上份量为一般参考区间，需按体重、病情、咀嚼与吞咽能力调整，不是疾病治疗饮食处方。'
REFERRAL_L2 = '建议近期（最好 1–2 周内）到营养科或门诊评估，带上近三个月的体重变化、检验结果和正在服用的药物。'
REFERRAL_L3 = '可以先按上面的替换方案调整 2–4 周，复查时把饮食记录带给医生或营养师。'
SEVERITY_LABELS = {'high': '需尽快核对', 'moderate': '需要关注', 'note': '饮食提示'}

PORTION_UNITS = re.compile(
    r'(\d+(?:\.\d+)?)\s*(g|克|kg|公斤|ml|毫升|千卡|kcal|大卡)'
    r'|([0-9一二三四五六七八九十半])\s*(两|斤)')
UNIT_NORMAL = {'克': 'g', '公斤': 'kg', '毫升': 'ml', '千卡': 'kcal', '大卡': 'kcal', '两': '两', '斤': '斤'}
PRESCRIPTION = re.compile(r'(?:治疗|处方|治好|治愈|替代药物|可以停药|不用吃药|食疗(?:可以|能)治)')
PRESCRIPTION_NEG = re.compile(r'(?:不能|无法|不可|不要|不得|并非|不是|不能靠|不能替代)[^。；\n]{0,10}$')
ABSOLUTE = re.compile(r'(?:绝对|肯定能|百分之百|完全不能吃|必须吃|一定要吃|包治)')
EXTREME = re.compile(r'(?:生酮|断食|辟谷|排毒|单一饮食|只吃一种)')
DIAGNOSIS = re.compile(r'(?:诊断|确诊)(?:为|是)|您患有')
DRUG_FOOD_CLAIM = re.compile(r'(?:可以|能)[^。；\n]{0,8}(?:一起|大量)(?:吃|同食)|不影响(?:药效|药物)')


def normalize(text: str) -> str:
    return unicodedata.normalize('NFKC', text or '')


def _negated(text: str, start: int, pattern=PRESCRIPTION_NEG) -> bool:
    return bool(pattern.search(text[max(0, start - 14):start]))


def portion_units(text: str) -> set[str]:
    """Normalised "number+unit" pairs, e.g. 5克 -> 5g, 二两 -> 二两."""
    found: set[str] = set()
    for match in PORTION_UNITS.finditer(normalize(text)):
        if match[1] is not None:
            unit = UNIT_NORMAL.get(match[2], match[2])
            value = match[1].rstrip('0').rstrip('.') if '.' in match[1] else match[1]
            found.add(f'{value}{unit}')
        else:
            found.add(f'{match[3]}{match[4]}')
    return found


def portion_issues(text: str, support: str = '') -> list[str]:
    """A model may quote a guideline quantity, but may not invent a personalised portion.

    Any number+unit in model prose must appear in the cited evidence or the code-owned
    portion table; otherwise it is treated as an invented portion and blocked.
    """
    if not support:
        return sorted(portion_units(text))
    return sorted(portion_units(text) - portion_units(support))


def prescription_issues(text: str) -> list[str]:
    text = normalize(text)
    return [match.group(0) for match in PRESCRIPTION.finditer(text) if not _negated(text, match.start())]


def absolute_issues(text: str) -> list[str]:
    return [match.group(0) for match in ABSOLUTE.finditer(normalize(text))]


def extreme_issues(text: str) -> list[str]:
    return [match.group(0) for match in EXTREME.finditer(normalize(text))]


def diagnosis_issues(text: str) -> list[str]:
    return [match.group(0) for match in DIAGNOSIS.finditer(normalize(text))]


def drug_food_claims(text: str) -> list[str]:
    return [match.group(0) for match in DRUG_FOOD_CLAIM.finditer(normalize(text))]


def paragraph_issues(paragraph: DietParagraph, level: str, allergies: list[str] | None = None,
                     support: str = '') -> list[str]:
    text = paragraph.text
    issues = []
    if prescription_issues(text): issues.append('diet_prescription')
    if portion_issues(text, support): issues.append('portion_invention')
    if absolute_issues(text): issues.append('unsafe_advice')
    if extreme_issues(text): issues.append('extreme_diet')
    if diagnosis_issues(text): issues.append('overreach_diagnosis')
    if drug_food_claims(text): issues.append('drug_food_claim')
    for allergy in allergies or []:
        if allergy and allergy.strip() and allergy.strip() in text:
            issues.append('unsafe_food')
            break
    if level in {'L1', 'L2'} and re.search(r'(?:在家观察|先观察观察|不用去医院|问题不大)', text):
        issues.append('missing_referral')
    return list(dict.fromkeys(issues))


def food_block(assessment: NutritionAssessment) -> str:
    if not assessment.foods: return ''
    lines = []
    for food in assessment.foods:
        line = f'· {food.name}：{food.label}'
        lines.append(line)
    if assessment.unknown_foods:
        lines.append('· 未收录：' + '、'.join(assessment.unknown_foods) + '（暂无法判断成分，请核对配料表）')
    return '本次提到的食物：\n' + '\n'.join(lines)


def findings_block(assessment: NutritionAssessment) -> str:
    if not assessment.findings: return ''
    lines = []
    for finding in assessment.findings:
        label = SEVERITY_LABELS[finding.severity]
        foods = f'（{"、".join(finding.foods)}）' if finding.foods else ''
        lines.append(f'· 【{label}】{finding.title}{foods}\n  {finding.detail}\n  {finding.action}')
    return '需要留意的饮食问题：\n' + '\n'.join(lines)


def risk_block(assessment: NutritionAssessment) -> str:
    from app.services.diet.nutrition import risk_labels
    labels = risk_labels(assessment)
    if not labels: return ''
    return '膳食模式提示：' + '、'.join(labels) + '。'


def portion_block(reference: PortionReference) -> str:
    lines = [f'· {item.name}：{item.range_text}' + (f'（{item.note}）' if item.note else '') for item in reference.items]
    return ('每日膳食构成参考（' + reference.table_version + '）：\n' + '\n'.join(lines) + '\n' + PORTION_DISCLAIMER)


def referral_text(triage: DietTriage) -> str:
    if triage.level == 'L1': return '请立即拨打 120 或前往急诊。'
    if triage.level == 'L2': return REFERRAL_L2
    if triage.level == 'L3': return REFERRAL_L3
    return ''


def emergency_text(triage: DietTriage, assessment: NutritionAssessment) -> str:
    parts = ['这可能属于需要紧急处理的情况。请立即拨打 120，或让家人陪同前往最近医院急诊。']
    block = food_block(assessment)
    if block: parts.append(block)
    if 'choking_respiratory' in triage.rule_ids:
        parts.append('进食呛咳窒息时：让患者身体前倾、用力咳嗽；不能说话或面色发紫时立即拨打 120，'
                     '不要强行喂水或用手抠喉咙。')
    else:
        parts.append('等待救护时：停止进食可疑食物，保留食物包装或照片；不要自行服用抗过敏药掩盖症状；'
                     '如意识清醒可坐位休息，出现呕吐时侧卧防止误吸。')
    parts.append(DISCLAIMER)
    return '\n\n'.join(parts)


def boundary_text(intent: str) -> str:
    if intent == 'supplement_dose':
        return ('我不能提供营养补充剂（蛋白粉、肠内营养液等）的品牌、剂量或使用方案。'
                '补充剂需要根据体重、肾功能、进食量和检验结果确定，用错可能加重肾脏负担或引起不适。'
                '请让医生或营养师开具并随访。')
    if intent == 'extreme_diet':
        return ('我不推荐生酮、断食、辟谷、单一食物或“排毒”这类方案。老年人肌肉量本就下降，'
                '长期极低碳水或断食容易引起低血糖、乏力和营养不良，正在用降糖药或胰岛素时风险更高。'
                '如果需要控制体重，请由医生或营养师制定缓慢、可坚持的方案。')
    if intent == 'replace_medication':
        return ('食物不能替代药物。调整或停用降压药、降糖药、抗凝药必须由医生决定；'
                '可以讨论的是怎样把饮食配合到治疗方案里。')
    return ('疾病治疗饮食处方（例如肾病、肝病、肿瘤营养方案）需要营养师结合检验结果、体重和用药制定，'
            '我不能替代。我可以先给出一般性的饮食原则和需要避免的食物，具体份量与禁忌请到营养科门诊确定。')


def insufficient_text(assessment: NutritionAssessment, triage: DietTriage, reason: str) -> str:
    head = {
        'no_vectors': '营养知识库当前没有可用于该向量模型的片段，暂不能给出有依据的膳食建议。',
        'no_hits': '已执行检索，但没有召回与本次问题相关的资料，暂不能给出有依据的膳食建议。',
        'model_insufficient': '当前知识库资料不足以支持对该问题的可靠解释。',
        'invalid_output': '已检索到资料，但回答格式或膳食安全校验未通过，本次不展示草稿。',
        'invalid_citations': '已检索到资料，但引用或份量未通过校验，本次不展示草稿。',
        'unsupported_diet_claim': '草稿中的份量、禁忌或食疗结论未通过原文一致性检查，已拦截。',
        'grounding_review_failed': '已检索到资料，但本次答案与原文的一致性检查未能完成，暂不展示草稿。',
        'unsafe_paragraph': '草稿包含份量处方、过敏食物或绝对化表述，已拦截，不展示。',
    }.get(reason, '本次未能形成有依据的回答。')
    parts = [part for part in (food_block(assessment), findings_block(assessment), head) if part]
    if assessment.foods:
        parts.append(portion_block_reference())
    if triage.level in {'L2', 'L3'}:
        parts.append(referral_text(triage))
    parts.append(EMERGENCY_CHECKLIST)
    parts.append(DISCLAIMER)
    return '\n\n'.join(parts)


def portion_block_reference() -> str:
    from app.services.diet.foods import portion_reference
    return portion_block(portion_reference())


def missing_labels(keys) -> list[str]:
    labels = {
        'condition_list': '老人的慢病情况（高血压、糖尿病、肾病等）',
        'chewing_swallowing': '咀嚼和吞咽情况',
        'weight_trend': '近三个月的体重变化',
        'allergy_list': '是否有食物过敏',
        'medication_list': '正在服用的药物名称',
        'portion_evidence': '份量的资料依据',
        'menu_evidence': '食谱搭配的资料依据',
        'full_diet_scope': '问题涉及的完整膳食范围',
    }
    return [labels.get(key, key) for key in keys]
