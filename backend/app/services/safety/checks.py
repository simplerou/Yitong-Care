"""Deterministic safety checks and fixed copy.

"Don't lift them up" and "call 120" are code-owned: a model must never talk a family
member into standing someone up after a fall, or into watching at home.
"""
import re
import unicodedata

from app.schemas.safety import SafetyAssessment, SafetyParagraph, SafetyTriage
from app.services.safety.postfall import POST_FALL_ADVICE

DISCLAIMER = ('以上为居家安全与跌倒预防建议，不构成医疗诊断或康复训练处方，'
              '不能替代医生、康复治疗师或适老化改造人员的现场评估。')
EMERGENCY_CHECKLIST = ('跌倒后出现意识不清、叫不醒、呕吐或嗜睡、呼吸困难、大量出血、'
                       '髋部或腰背疼痛无法站立时，请立即拨打 120，不要搬动。')
BOUNDARY_REHAB = ('康复训练处方（具体的动作、组数、疗程）需要康复治疗师评估肌力、平衡和心肺情况后制定，'
                  '我不能替代。可以先做的是：把跌倒经过、用药、视力和居家环境整理好，带去康复科或老年科评估。')
BOUNDARY_QUOTE = ('我不提供改造报价、施工方案或材料清单。适老化改造建议由社区、专业改造机构或康复治疗师上门评估后确定，'
                  '各地也有不同的补贴政策，可以向社区咨询。')
BOUNDARY_RESTRAINT = ('不推荐用约束带、绑带等方式限制老人活动。约束会增加压疮、谵妄和跌倒风险，'
                      '是否使用必须由医疗机构评估，不能作为家庭防跌倒手段。')
SEVERITY_LABELS = {'high': '需尽快核对', 'moderate': '需要关注', 'note': '安全提示'}

DIMENSION_UNITS = re.compile(r'(\d+(?:\.\d+)?)\s*(cm|厘米|mm|毫米|米|m|度|°)')
MOVE_ADVICE = re.compile(r'(?:马上|立即|赶紧|直接|立刻)扶(?:起|起来|他|她)')
MOVE_NEG = re.compile(r'(?:不要|别|不能|不可|先不|切勿)[^。；\n]{0,10}$')
REHAB_PRESCRIPTION = re.compile(r'康复(?:训练)?处方|训练处方|每天\s*\d+\s*(?:组|次|个)|每次\s*\d+\s*(?:组|个)|疗程')
CONSTRUCTION = re.compile(r'包工包料|报价|材料费|施工队|多少钱|价格|元/米|人工费')
DIAGNOSIS = re.compile(r'(?:诊断|确诊)(?:为|是)|就是骨折|肯定是骨折|已经骨折')
ABSOLUTE = re.compile(r'(?:绝对安全|肯定不会摔|完全没事|保证不会摔)')


def normalize(text: str) -> str:
    return unicodedata.normalize('NFKC', text or '')


def _negated(text: str, start: int) -> bool:
    return bool(MOVE_NEG.search(text[max(0, start - 14):start]))


def dimension_units(text: str) -> set[str]:
    found: set[str] = set()
    for match in DIMENSION_UNITS.finditer(normalize(text)):
        unit = {'厘米': 'cm', '毫米': 'mm', '米': 'm', '度': '°', '°': '°'}.get(match[2], match[2])
        found.add(f'{match[1]}{unit}')
    return found


def dimension_issues(text: str, support: str = '') -> list[str]:
    """Dimensions may be quoted from evidence or the hazard table, never invented."""
    if not support: return sorted(dimension_units(text))
    return sorted(dimension_units(text) - dimension_units(support))


def move_issues(text: str) -> list[str]:
    text = normalize(text)
    return [match.group(0) for match in MOVE_ADVICE.finditer(text) if not _negated(text, match.start())]


def rehab_issues(text: str) -> list[str]:
    return [match.group(0) for match in REHAB_PRESCRIPTION.finditer(normalize(text))]


def construction_issues(text: str) -> list[str]:
    return [match.group(0) for match in CONSTRUCTION.finditer(normalize(text))]


def diagnosis_issues(text: str) -> list[str]:
    return [match.group(0) for match in DIAGNOSIS.finditer(normalize(text))]


def absolute_issues(text: str) -> list[str]:
    return [match.group(0) for match in ABSOLUTE.finditer(normalize(text))]


def paragraph_issues(paragraph: SafetyParagraph, level: str, support: str = '') -> list[str]:
    text = paragraph.text
    issues = []
    if move_issues(text): issues.append('unsafe_move')
    if rehab_issues(text): issues.append('rehab_prescription')
    if construction_issues(text): issues.append('construction_claim')
    if diagnosis_issues(text): issues.append('overreach_diagnosis')
    if absolute_issues(text): issues.append('unsafe_advice')
    if dimension_issues(text, support): issues.append('unsupported_dimension')
    if level in {'L1', 'L2'} and re.search(r'(?:在家观察|先观察观察|不用去医院|问题不大)', text):
        issues.append('missing_referral')
    return list(dict.fromkeys(issues))


def hazard_support(assessment: SafetyAssessment) -> str:
    return '\n'.join(f'{item.issue} {item.action} {item.reference}' for item in assessment.hazards)


def hazards_block(assessment: SafetyAssessment) -> str:
    if not assessment.hazards: return ''
    lines = []
    for item in assessment.hazards:
        lines.append(f'· 【{SEVERITY_LABELS[item.severity]}】{item.room}：{item.issue}\n  {item.action}')
    return '本次提到的居家隐患：\n' + '\n'.join(lines)


def risk_block(assessment: SafetyAssessment) -> str:
    if not assessment.risk_factors: return ''
    level = {'low': '较低', 'medium': '中等', 'high': '较高'}[assessment.risk_level]
    lines = [f'· {factor.label}：{factor.action}' for factor in assessment.risk_factors]
    return f'跌倒风险因素（综合评估：{level}）：\n' + '\n'.join(lines)


def postfall_block(findings) -> str:
    if not findings: return ''
    lines = []
    for item in findings:
        lines.append(f'· 【{SEVERITY_LABELS[item.severity]}】{item.title}\n  {item.detail}\n  {item.action}')
    return '跌倒后需要判断的情况：\n' + '\n'.join(lines)


def postfall_advice() -> str:
    return POST_FALL_ADVICE


def referral_text(triage: SafetyTriage) -> str:
    if triage.level == 'L1': return '请立即拨打 120，不要搬动或扶起。'
    if triage.level == 'L2': return '建议尽快就医或联系社区康复/老年科评估，同时按上面的清单改造居家环境。'
    if triage.level == 'L3': return '建议 1–2 个月内做一次跌倒风险评估，并先处理最容易绊倒的地方。'
    return ''


def emergency_text(triage: SafetyTriage, assessment: SafetyAssessment) -> str:
    parts = ['这可能属于需要紧急处理的情况。请立即拨打 120，或让家人陪同前往最近医院急诊。']
    if assessment.hazards:
        parts.append(hazards_block(assessment))
    parts.append(postfall_block(assessment.post_fall))
    parts.append(postfall_advice())
    parts.append(DISCLAIMER)
    return '\n\n'.join(parts)


def boundary_text(intent: str) -> str:
    if intent == 'rehab_prescription': return BOUNDARY_REHAB
    if intent == 'construction_quote': return BOUNDARY_QUOTE
    if intent == 'restraint': return BOUNDARY_RESTRAINT
    return BOUNDARY_QUOTE


def insufficient_text(assessment: SafetyAssessment, triage: SafetyTriage, reason: str) -> str:
    head = {
        'no_vectors': '安全知识库当前没有可用于该向量模型的片段，暂不能给出有依据的建议。',
        'no_hits': '已执行检索，但没有召回与本次问题相关的资料，暂不能给出有依据的建议。',
        'model_insufficient': '当前知识库资料不足以支持对该问题的可靠解释。',
        'invalid_output': '已检索到资料，但回答格式或安全校验未通过，本次不展示草稿。',
        'invalid_citations': '已检索到资料，但引用或尺寸未通过校验，本次不展示草稿。',
        'unsupported_safety_claim': '草稿中的判断未通过原文一致性检查，已拦截。',
        'grounding_review_failed': '已检索到资料，但本次答案与原文的一致性检查未能完成，暂不展示草稿。',
        'unsafe_paragraph': '草稿包含搬动建议、康复处方或改造报价，已拦截，不展示。',
    }.get(reason, '本次未能形成有依据的回答。')
    parts = [part for part in (hazards_block(assessment), risk_block(assessment),
                               postfall_block(assessment.post_fall), head) if part]
    if assessment.post_fall and any(item.severity in {'high', 'moderate'} for item in assessment.post_fall):
        parts.append(postfall_advice())
    if triage.level in {'L2', 'L3'}:
        parts.append(referral_text(triage))
    parts.append(EMERGENCY_CHECKLIST)
    parts.append(DISCLAIMER)
    return '\n\n'.join(parts)


def missing_labels(keys) -> list[str]:
    labels = {
        'fall_history': '过去一年是否跌倒过、跌倒几次',
        'living_situation': '是否独居或有人照看',
        'mobility': '平时走路是否需要扶人或用助行器',
        'medication_list': '正在服用的药物（尤其安眠药、降压药、抗凝药）',
        'home_layout': '家里的房间布局与地面情况',
        'injury_detail': '跌倒后的疼痛部位、能否活动、是否撞到头',
        'environment_evidence': '具体尺寸与环境要求的资料依据',
        'full_safety_scope': '问题涉及的完整安全范围',
    }
    return [labels.get(key, key) for key in keys]
