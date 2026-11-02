"""Deterministic medication safety checks and fixed copy.

Doses, substitutions, interactions and emergency wording are owned by code or by
explicit rules, so a model failure can never produce a dosing instruction.
"""
import re
import unicodedata

from app.schemas.medication import (
    InteractionFinding, MedicationAssessment, MedicationParagraph, MedicationTriage,
)
from app.services.medication.drugs import INTERACTION_LABELS

DISCLAIMER = ('以上为用药科普信息，不构成处方或用药调整建议，不能替代医生或药师面诊；'
              '请勿自行加量、减量或停药。')
BOUNDARY = ('我不能提供加量、减量、停药或换药的具体建议。降压药、降糖药、抗凝药、镇静催眠药等自行调整，'
            '可能带来低血压、低血糖、出血或跌倒风险。')
BOUNDARY_ACTION = ('正确做法是：把最近的血压、血糖或症状记录，连同所有正在服用的药盒（包括保健品）带给开药医生或药师核对。')
EMERGENCY_CHECKLIST = ('用药后如出现口唇或喉头肿胀、呼吸困难、皮疹迅速加重、呕血黑便、突发剧烈头痛、'
                       '意识模糊或叫不醒，请立即拨打 120。')
MISSED_DOSE_NOTE = '以上补服原则是通用提示，具体药物请以说明书或医嘱为准。'

DOSAGE_NUMBER = re.compile(r'\d+(?:\.\d+)?\s*(?:mg|毫克|μg|微克|ug|片|粒|单位|IU|万单位)')
DOSE_CHANGE = re.compile(r'(?:加量|减量|停药|停掉|停用|停服|换药|改用|加倍|减半|自行服药|自己加药|'
                         r'(?:加|减|吃|改|换)(?:到|至|成)?\s*[0-9一二三四五六七八九十两半]+\s*(?:片|粒|mg|毫克))')
DOSE_CHANGE_NEG = re.compile(r'(?:不要|不得|不可|请勿|切勿|禁止|避免|不应|不能|勿|别)[^。；\n]{0,10}$')
INTERACTION_ASSERTION = re.compile(
    r'(?:可以|能|放心)[^。；\n]{0,12}(?:一起|同时)(?:服用|吃|用)|'
    r'(?:一起|同时)(?:服用|吃|用)?(?:没问题|没事|安全)|'
    r'没有(?:任何)?(?:相互作用|冲突)|不会(?:有)?相互作用|绝对安全|肯定安全')
SUBSTITUTION = re.compile(r'(?:可以|建议|不妨|不如)(?:用|把)[^。；\n]{0,20}(?:代替|替代|换成)|(?:替代|代替)[^。；\n]{0,10}(?:原药|原来的药)')
DIAGNOSIS = re.compile(r'(?:诊断|确诊)(?:为|是)|可以确诊|您患有(?:高血压|糖尿病|冠心病|肾病)')
ABSOLUTE = re.compile(r'(?:肯定没事|完全没问题|绝对安全|没有任何副作用|放心吃|可以替代(?:就诊|医生|药师))')


def normalize(text: str) -> str:
    return unicodedata.normalize('NFKC', text or '')


def _negated(text: str, start: int) -> bool:
    return bool(DOSE_CHANGE_NEG.search(text[max(0, start - 14):start]))


def dosage_issues(text: str) -> list[str]:
    """Any numeric dose in model prose is blocked: dose numbers must not be volunteered."""
    return [match.group(0) for match in DOSAGE_NUMBER.finditer(normalize(text))]


def dose_change_issues(text: str) -> list[str]:
    text = normalize(text)
    return [match.group(0) for match in DOSE_CHANGE.finditer(text) if not _negated(text, match.start())]


def interaction_assertions(text: str) -> list[str]:
    return [match.group(0) for match in INTERACTION_ASSERTION.finditer(normalize(text))]


def substitution_issues(text: str) -> list[str]:
    return [match.group(0) for match in SUBSTITUTION.finditer(normalize(text))]


def diagnosis_issues(text: str) -> list[str]:
    return [match.group(0) for match in DIAGNOSIS.finditer(normalize(text)) if not _negated(normalize(text), match.start())]


def absolute_issues(text: str) -> list[str]:
    return [match.group(0) for match in ABSOLUTE.finditer(normalize(text))]


def paragraph_issues(paragraph: MedicationParagraph, level: str) -> list[str]:
    issues = []
    if dose_change_issues(paragraph.text): issues.append('dose_advice')
    if dosage_issues(paragraph.text): issues.append('dose_number')
    if interaction_assertions(paragraph.text): issues.append('interaction_claim')
    if substitution_issues(paragraph.text): issues.append('substitution')
    if diagnosis_issues(paragraph.text): issues.append('overreach_diagnosis')
    if absolute_issues(paragraph.text): issues.append('unsafe_advice')
    if level in {'L1', 'L2'} and re.search(r'(?:在家观察|先观察观察|明天再看|问题不大)', paragraph.text):
        issues.append('missing_referral')
    return issues


def drug_block(assessment: MedicationAssessment) -> str:
    if not assessment.drugs: return ''
    lines = []
    for drug in assessment.drugs:
        line = f'· {drug.name}：{drug.class_label}，{drug.indication}' if drug.indication else f'· {drug.name}：{drug.class_label}'
        if drug.timing_hint: line += f'；常见服用时间：{drug.timing_hint}'
        line += '（常见信息，以说明书和医嘱为准）'
        lines.append(line)
    if assessment.unknown_names:
        lines.append('· 未收录：' + '、'.join(assessment.unknown_names) + '（暂无法核对相互作用，请让药师确认）')
    return '本次识别到的药物：\n' + '\n'.join(lines)


def interaction_block(assessment: MedicationAssessment) -> str:
    if not assessment.interactions: return ''
    lines = []
    for finding in assessment.interactions:
        label = INTERACTION_LABELS[finding.severity]
        lines.append(f'· 【{label}】{finding.title}（{"、".join(finding.drugs)}）\n  {finding.detail}\n  {finding.action}')
    return '相互作用与用药风险：\n' + '\n'.join(lines)


def high_severity_note(assessment: MedicationAssessment) -> str:
    if not assessment.high_count(): return ''
    return ('以上相互作用中，标记为“需尽快核对”的项建议在下一次服药前联系开药医生或药师确认，'
            '不要自行停药或调整剂量。')


def referral_text(triage: MedicationTriage) -> str:
    if triage.level == 'L1': return '请立即拨打 120 或前往急诊。'
    if triage.level == 'L2': return '请尽快（24 小时内）联系医生或药师，携带药盒和近期检查结果。'
    if triage.level == 'L3': return '建议咨询药师或门诊医生，说明用药与症状。'
    return ''


def emergency_text(triage: MedicationTriage, assessment: MedicationAssessment) -> str:
    parts = ['这可能属于需要紧急处理的情况。请立即拨打 120，或让家人陪同前往最近医院急诊。']
    block = drug_block(assessment)
    if block: parts.append(block)
    parts.append('等待救护时：带上所有正在服用的药物和保健品（或药盒、药单）交给医生；'
                 '不要自行停药、加量或再服其他药；如怀疑低血糖且意识清醒，可含少量糖。')
    parts.append(DISCLAIMER)
    return '\n\n'.join(parts)


def boundary_text(reason: str) -> str:
    if reason == 'stop_or_switch':
        return (BOUNDARY + '是否停药或换药需要医生根据病情、检查结果和合并用药判断。' + BOUNDARY_ACTION +
                '如果是因为出现不适想停药，请先联系医生，不要突然停用降压药、抗凝药或激素类药物。')
    return (BOUNDARY + '剂量需要医生结合血压、血糖、肝肾功能和合并用药来确定。' + BOUNDARY_ACTION)


def insufficient_text(assessment: MedicationAssessment, triage: MedicationTriage, reason: str) -> str:
    head = {
        'no_vectors': '用药知识库当前没有可用于该向量模型的片段，暂不能给出有依据的解释。',
        'no_hits': '已执行检索，但没有召回与本次问题相关的资料，暂不能给出有依据的解释。',
        'model_insufficient': '当前知识库资料不足以支持对该问题的可靠解释。',
        'invalid_output': '已检索到资料，但回答格式或用药安全校验未通过，本次不展示草稿。',
        'invalid_citations': '已检索到资料，但引用或数值未通过校验，本次不展示草稿。',
        'unsupported_medication_claim': '草稿中的相互作用或用药结论未通过原文一致性检查，已拦截。',
        'grounding_review_failed': '已检索到资料，但本次答案与原文的一致性检查未能完成，暂不展示草稿。',
        'unsafe_paragraph': '草稿包含剂量、停药或相互作用断言，已拦截，不展示。',
    }.get(reason, '本次未能形成有依据的回答。')
    parts = [part for part in (drug_block(assessment), head) if part]
    if assessment.interactions:
        parts.append(interaction_block(assessment))
        parts.append(high_severity_note(assessment))
    if triage.level in {'L2', 'L3'}:
        parts.append(referral_text(triage))
    parts.append(EMERGENCY_CHECKLIST)
    parts.append(DISCLAIMER)
    return '\n\n'.join(parts)


def missing_labels(keys) -> list[str]:
    labels = {
        'drug_list': '正在服用的药物清单（药名）',
        'dose_frequency': '每种药每天服用几次',
        'last_dose_time': '上次服药的时间',
        'symptom_detail': '症状出现的时间和具体表现',
        'interaction_evidence': '相互作用的说明书或资料依据',
        'timing_evidence': '服用时间与进食关系的资料依据',
        'adverse_evidence': '不良反应的判断依据',
        'full_medication_scope': '问题涉及的完整用药范围',
    }
    return [labels.get(key, key) for key in keys]
