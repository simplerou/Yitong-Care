"""Deterministic safety checks and fixed copy for the mind companion.

Toxic positivity, diagnosis, medication advice, method details and absolute promises are
blocked; the crisis hotline and safety-plan steps are injected by code.
"""
import re
import unicodedata

from app.schemas.mind import MindAssessment, MindParagraph, MindTriage
from app.services.mind import risk

DISCLAIMER = ('以上是陪伴与心理教育信息，不构成诊断或治疗建议，也不能替代精神科医生或心理治疗师的评估；'
              '如果出现伤害自己的想法，请立即拨打 120 或心理援助热线 12356。')
EMERGENCY_CHECKLIST = '如果你现在有伤害自己或他人的念头，请立即拨打 120 或 12356，并让身边的人陪着你。'
WARM_OPEN = '谢谢你愿意把这些说出来。'
BOUNDARY_THERAPY = ('我不能提供具体的心理治疗方案（例如认知行为练习的步骤、疗程安排或暴露计划）。'
                    '这些需要精神科医生或心理治疗师在评估后制定。我可以先陪你把现在的感受讲清楚，'
                    '并帮你整理就诊时要说明的情况。')
BOUNDARY_MEDICATION = '抗抑郁药、安眠药的种类和剂量需要精神科医生评估后开具，我不能给用药建议。是否需要调整，请带着近期的情绪和睡眠记录去复诊。'
TOXIC = re.compile(r'(?:想开点|别想太多|想那么多干什么|比你惨的人多了|矫情|多大点事|坚强点|忍一忍|'
                   r'都是为你好|开心一点就好了|振作起来|别太敏感)')
DIAGNOSIS = re.compile(r'(?:你就是抑郁症|确诊为|您患有|你已经得了|肯定是抑郁)')
MEDICATION = re.compile(r'(?:吃|服|用)(?:点|些)?[^。；\n]{0,8}(?:安眠药|抗抑郁药|药)|加量|减量|停药|(?:吃|服)(?:点|些)?[^。；\n]{0,6}(?:片|粒)')
MEDICATION_NEG = re.compile(r'(?:不要|不得|不可|请勿|不能|别)[^。；\n]{0,10}$')
METHOD = re.compile(r'(?:跳楼|上吊|烧炭|割腕|怎么死|吃多少片|致死量|剂量)')
ABSOLUTE = re.compile(r'(?:一定会好|保证会好|我保证|绝对保密|不会告诉任何人)')
CONFIDENTIALITY = re.compile(r'(?:绝对保密|不会告诉任何人|谁都不说)')


def normalize(text: str) -> str:
    return unicodedata.normalize('NFKC', text or '')


def _negated(text: str, start: int, pattern=MEDICATION_NEG) -> bool:
    return bool(pattern.search(text[max(0, start - 14):start]))


def toxic_issues(text: str) -> list[str]:
    return [match.group(0) for match in TOXIC.finditer(normalize(text))]


def diagnosis_issues(text: str) -> list[str]:
    return [match.group(0) for match in DIAGNOSIS.finditer(normalize(text))]


def medication_issues(text: str) -> list[str]:
    text = normalize(text)
    return [match.group(0) for match in MEDICATION.finditer(text) if not _negated(text, match.start())]


def method_issues(text: str) -> list[str]:
    return [match.group(0) for match in METHOD.finditer(normalize(text))]


def absolute_issues(text: str) -> list[str]:
    return [match.group(0) for match in ABSOLUTE.finditer(normalize(text))]


def confidentiality_issues(text: str) -> list[str]:
    return [match.group(0) for match in CONFIDENTIALITY.finditer(normalize(text))]


def paragraph_issues(paragraph: MindParagraph, level: str) -> list[str]:
    text = paragraph.text
    issues = []
    if toxic_issues(text): issues.append('toxic_positivity')
    if diagnosis_issues(text): issues.append('overreach_diagnosis')
    if medication_issues(text): issues.append('medication_advice')
    if method_issues(text): issues.append('harmful_advice')
    if absolute_issues(text): issues.append('confidentiality_overclaim')
    if level in {'L1', 'L2'} and re.search(r'(?:自己扛一扛|不用找人|不需要看医生|过段时间就好了)', text):
        issues.append('missing_referral')
    return list(dict.fromkeys(issues))


def crisis_block(triage: MindTriage) -> str:
    return risk.crisis_text(triage) + '\n' + risk.CRISIS_LINE_NOTE


def safety_plan_block() -> str:
    steps = risk.safety_plan_text()
    return '\n'.join([steps[0]] + [f'· {step}' for step in steps[1:]])


def tips_block(intent: str) -> str:
    tips = risk.tips_for(intent)
    return '一些现在就能做的小事（一般建议，不替代专业治疗）：\n' + '\n'.join(f'· {tip}' for tip in tips)


def screening_block(assessment: MindAssessment) -> str:
    if not assessment.screening.positive: return ''
    return ('你提到最近情绪低落、也提不起兴趣，这类情况在两周以上时，专业人员通常会用问卷进一步评估。'
            '这不是诊断，但值得尽快找人聊一次。')


def referral_text(triage: MindTriage) -> str:
    return risk.referral_text(triage)


def boundary_text(intent: str) -> str:
    if intent == 'medication_request': return BOUNDARY_MEDICATION
    return BOUNDARY_THERAPY


def insufficient_text(assessment: MindAssessment, triage: MindTriage, reason: str) -> str:
    head = {
        'no_vectors': '心理关怀知识库当前没有可用于该向量模型的片段，暂时不能给出有依据的说明。',
        'no_hits': '已执行检索，但没有召回与本次问题相关的资料，暂时不能给出有依据的说明。',
        'model_insufficient': '当前知识库资料不足以支持对该问题的可靠解释。',
        'invalid_output': '已检索到资料，但回答格式或安全校验未通过，本次不展示草稿。',
        'invalid_citations': '已检索到资料，但引用未通过校验，本次不展示草稿。',
        'unsupported_mind_claim': '草稿中的判断或建议未通过原文一致性检查，已拦截。',
        'grounding_review_failed': '已检索到资料，但本次答案与原文的一致性检查未能完成，暂不展示草稿。',
        'unsafe_paragraph': '草稿包含不当建议，已拦截，不展示。',
    }.get(reason, '本次未能形成有依据的回答。')
    parts = [part for part in (screening_block(assessment), head) if part]
    if triage.level in {'L1'}:
        parts.append(crisis_block(triage))
    elif triage.level == 'L2':
        parts.append(safety_plan_block())
        parts.append(referral_text(triage))
    else:
        parts.append(tips_block('emotional_support'))
    parts.append(EMERGENCY_CHECKLIST)
    parts.append(DISCLAIMER)
    return '\n\n'.join(parts)


def missing_labels(keys) -> list[str]:
    labels = {
        'mood_detail': '最近的睡眠、食欲和情绪变化',
        'duration': '这种状态持续了多久',
        'sleep_detail': '具体睡眠情况（入睡、早醒、白天精神）',
        'support_person': '身边可以联系的人',
        'safety_status': '现在是否安全、有没有具体的打算',
        'grief_context': '失去亲人或生活变化的情况',
        'social_situation': '目前的居住与社交情况',
        'evidence': '相关心理关怀资料',
    }
    return [labels.get(key, key) for key in keys]
