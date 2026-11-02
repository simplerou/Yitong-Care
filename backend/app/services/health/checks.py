"""Deterministic answer checks and fixed safety copy for the health agent.

The model composes explanations; this module owns every claim that must not depend on
model compliance: disclaimers, emergency wording, referral blocks and dose refusals.
"""
import re
import unicodedata
from decimal import Decimal

from app.schemas.health import HealthParagraph, Triage, VitalsAssessment

DISCLAIMER = '以上为健康科普信息，不构成诊断或处方，不能替代医生面诊；如症状加重请及时就医。'
MEDICATION_BOUNDARY = '请勿自行加量、减量或停药；用药调整请咨询医生或使用用药管家。'
EMERGENCY_CHECKLIST = ('出现胸痛或胸闷持续不缓解、呼吸困难、意识改变、单侧肢体无力、口角歪斜、'
                       '言语不清、呕血黑便、晕厥跌倒后不能站立等情况，请立即拨打 120。')

UNIT_ALIASES = {
    'mmhg': 'mmHg', 'mm hg': 'mmHg', '毫米汞柱': 'mmHg',
    'mmol/l': 'mmol/L', 'mmol': 'mmol/L', '毫摩尔/升': 'mmol/L',
    'mg/dl': 'mg/dL', 'mgdl': 'mg/dL',
    '次/分': '次/分', '次／分': '次/分', 'bpm': '次/分',
    '%': '%', '％': '%', '℃': '℃', '摄氏度': '℃',
    'kg': 'kg', '公斤': 'kg', 'kg/m2': 'kg/m²', 'kg/m²': 'kg/m²',
    'g': 'g', '克': 'g', 'mg': 'mg', '毫克': 'mg',
}
UNIT_PATTERN = r'(mmhg|mm hg|毫米汞柱|mmol/l|mmol|毫摩尔/升|mg/dl|mgdl|次/分|次／分|bpm|%|％|℃|摄氏度|kg/m²|kg/m2|kg|公斤|g|克|mg|毫克)'
ALLOWED_UNITS = set(UNIT_ALIASES.values())

NEGATION_TAIL = re.compile(r'(?:不要|不得|不可|请勿|切勿|禁止|避免|不应|不能|勿|别|不)[^。；\n]{0,8}$')
DIAGNOSIS = re.compile(
    r'(?:诊断|确诊)(?:为|是)|可以确诊|就是(?:高血压|糖尿病|冠心病|肾病|心衰|慢阻肺)|'
    r'您患有(?:高血压|糖尿病|冠心病|肾病)')
MEDICATION = re.compile(r'(?:加量|减量|停药|停掉|换药|改用|加倍|减半|自行服药|自己加药|'
                        r'(?:加|减|吃|改|换)(?:到|至|成)?\s*[0-9一二三四五六七八九十两半]+\s*(?:片|粒|mg|毫克))')
DOSAGE = re.compile(
    r'(?:(?:每次|每顿|每日|每天|一日)\s*[0-9一二三四五两半]+\s*(?:片|粒|袋|毫升|ml|mg|毫克))'
    r'|(?:[0-9]+\s*(?:片|粒|mg|毫克)\s*(?:每天|一日|一天|每次)?)')
ABSOLUTE = re.compile(
    r'(?:肯定没事|完全没问题|完全正常|不用担心|不用管|不需要就医|无需就医|不用去医院|不必就医|'
    r'可以替代(?:就诊|医生|面诊)|保证(?:治好|有效)|一定能治好)')
SUPPRESS_EMERGENCY = re.compile(r'(?:在家观察|先观察观察|自行服药|吃点药就行|明天再看|问题不大)')


def normalize(text: str) -> str:
    return unicodedata.normalize('NFKC', text or '')


def _clean_number(value: str) -> Decimal:
    return Decimal(value)


def _unit(raw: str) -> str:
    key = raw.strip().lower()
    return UNIT_ALIASES.get(key, UNIT_ALIASES.get(raw.strip(), raw.strip()))


def numeric_units(text: str) -> set[tuple[str, str]]:
    """Numbers with clinical units. Unit-less numbers (levels, days) are not constrained."""
    text = normalize(text)
    found: set[tuple[str, str]] = set()
    for match in re.finditer(r'(\d{2,3})\s*/\s*(\d{2,3})\s*(mmHg|毫米汞柱)?', text, re.I):
        systolic, diastolic = _clean_number(match[1]), _clean_number(match[2])
        unit = 'mmHg'
        found.add((f'{systolic}/{diastolic}', unit))
        found.add((str(systolic), unit))
        found.add((str(diastolic), unit))
    for match in re.finditer(r'(\d+(?:\.\d+)?)\s*' + UNIT_PATTERN, text, re.I):
        unit = _unit(match[2])
        if unit not in ALLOWED_UNITS: continue
        found.add((str(_clean_number(match[1])), unit))
    return found


def _has_negation(text: str, start: int) -> bool:
    return bool(NEGATION_TAIL.search(text[max(0, start - 14):start]))


def medication_issues(text: str) -> list[str]:
    text = normalize(text)
    issues = []
    for match in MEDICATION.finditer(text):
        if _has_negation(text, match.start()): continue
        issues.append(match.group(0))
    for match in DOSAGE.finditer(text):
        if _has_negation(text, match.start()): continue
        issues.append(match.group(0).strip())
    return list(dict.fromkeys(issues))


def diagnosis_issues(text: str) -> list[str]:
    text = normalize(text)
    return [match.group(0) for match in DIAGNOSIS.finditer(text) if not _has_negation(text, match.start())]


def absolute_issues(text: str) -> list[str]:
    return [match.group(0) for match in ABSOLUTE.finditer(normalize(text))]


def suppression_issues(text: str, level: str) -> list[str]:
    if level not in {'L1', 'L2'}: return []
    return [match.group(0) for match in SUPPRESS_EMERGENCY.finditer(normalize(text))]


def context_claim_issues(text: str, assessment: VitalsAssessment) -> list[str]:
    """Do not let the model claim a measurement setting the parser never saw."""
    readings = [item for item in assessment.readings if item.metric == 'blood_pressure']
    if not readings: return []
    # A claim about this reading, not a comparison such as "家庭自测标准低于诊室".
    home_claim = bool(re.search(r'(?:家庭自测|在家测|家里量|在家量|自测)[^。；\n]{0,12}(?:血压|结果|读数|数值)'
                                r'|(?:血压|结果|读数|数值)[^。；\n]{0,8}(?:家庭自测|在家测)', text))
    if home_claim and any(item.context != 'home' for item in readings): return ['wrong_category']
    return []


def paragraph_issues(paragraph: HealthParagraph, level: str) -> list[str]:
    issues = []
    if medication_issues(paragraph.text): issues.append('medication_instruction')
    if diagnosis_issues(paragraph.text): issues.append('overreach_diagnosis')
    if absolute_issues(paragraph.text): issues.append('unsafe_advice')
    if suppression_issues(paragraph.text, level): issues.append('missing_referral')
    return issues


def numeric_support_issues(paragraphs: list[HealthParagraph], evidence_by_index: dict[int, str],
                           assessment_texts: list[str]) -> list[dict]:
    issues = []
    for index, paragraph in enumerate(paragraphs, 1):
        support = '\n'.join([evidence_by_index.get(source, '') for source in paragraph.sources] + assessment_texts)
        allowed = numeric_units(support)
        for value, unit in numeric_units(paragraph.text):
            if (value, unit) not in allowed:
                issues.append({'paragraph': index, 'type': 'unsupported_number', 'number': f'{value}{unit}'})
    return issues


def assessment_block(assessment: VitalsAssessment | None) -> str:
    if assessment is None: return ''
    return '\n\n'.join(assessment.summary_lines())


def referral_text(triage: Triage) -> str:
    if triage.level == 'L1': return '请立即拨打 120 或前往急诊。'
    if triage.level == 'L2': return '请在 24 小时内联系家庭医生或前往门诊，并告知测量值、测量时间与情境、正在服用的药物。'
    if triage.level == 'L3': return '建议近期到门诊复查，把这段时间的测量记录带给医生。'
    return ''


def emergency_text(triage: Triage, assessment: VitalsAssessment | None) -> str:
    parts = ['这可能属于需要紧急处理的情况。请立即拨打 120，或让家人陪同前往最近医院急诊。']
    block = assessment_block(assessment)
    if block: parts.append(block)
    if 'self_harm' in triage.rule_ids:
        parts.append('如您有伤害自己的想法，请立即联系家人并拨打心理援助热线（全国 12356），或直接前往急诊。请先不要独处。')
    parts.append('等待救护时：保持安静、不要自行服药或加量；疑似卒中不要喂水喂药；疑似低血糖且意识清醒可含少量糖；'
                 '准备好测量记录和正在服用的药物清单交给医生。即使症状已经缓解，也请尽快就医评估。')
    parts.append(DISCLAIMER)
    return '\n\n'.join(parts)


def insufficient_text(assessment: VitalsAssessment | None, triage: Triage, reason: str) -> str:
    block = assessment_block(assessment)
    head = {
        'no_vectors': '健康知识库当前没有可用于该向量模型的片段，暂不能给出有依据的解释。',
        'no_hits': '已执行检索，但没有召回与本次问题相关的资料，暂不能给出有依据的解释。',
        'model_insufficient': '当前知识库资料不足以支持对该问题的可靠解释。',
        'invalid_output': '已检索到资料，但回答格式未通过校验，本次不展示草稿。',
        'invalid_citations': '已检索到资料，但引用或数值未通过校验，本次不展示草稿。',
        'unsupported_health_claim': '草稿中的阈值、分级或建议未通过原文一致性检查，已拦截。',
        'unsafe_paragraph': '草稿包含剂量、诊断或绝对化表述，已拦截，不展示。',
        'grounding_review_failed': '已检索到资料，但本次答案与原文的一致性检查未能完成，暂不展示草稿。',
        'unsupported_number': '草稿中的数值无法在判读结果或引用原文中找到依据，已拦截。',
    }.get(reason, '本次未能形成有依据的回答。')
    parts = [part for part in (block, head) if part]
    if triage.level in {'L2', 'L3'}:
        parts.append(referral_text(triage))
    parts.append(EMERGENCY_CHECKLIST)
    return '\n\n'.join(parts)
