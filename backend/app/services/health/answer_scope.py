"""Editorial concept help and finite gap labels, separate from cited local facts."""
import re

GAPS = {
    'measurement_method': '规范的测量方法',
    'target_values': '个体化控制目标',
    'symptom_triage_criteria': '症状加重的判断标准',
    'lifestyle_evidence': '生活方式干预的具体依据',
    'medication_boundary': '用药调整的边界',
    'emergency_signs': '需要立即就医的征象',
    'lab_reference_range': '检验项目的参考范围',
    'full_health_scope': '问题涉及的完整健康范围',
}

TOPIC_QUERY = {
    'blood_pressure': '家庭血压测量 判读标准 老年人 高血压 指南',
    'glucose': '老年人 空腹血糖 餐后血糖 判读标准 指南',
    'fasting_glucose': '老年人 空腹血糖 判读标准 指南',
    'postprandial_glucose': '老年人 餐后血糖 判读标准 指南',
    'spo2': '血氧饱和度 低氧血症 判读 指南',
    'heart_rate': '静息心率 异常 判读 指南',
    'temperature': '老年人 发热 体温 处理 指南',
    'weight': '老年人 体重 管理 指南',
}


def gap_message(gaps, partial: bool = False) -> str:
    labels = '、'.join(GAPS[key] for key in dict.fromkeys(gaps) if key in GAPS)
    return ('本次仅回答已有原文支持的部分；' if partial else '') + \
        '当前资料尚不足以核实' + (labels or '所问结论') + '。这不代表相关问题不存在，建议就诊时向医生确认。'


def concept_help(text: str) -> list[str]:
    help_text = []
    if re.search(r'空腹血糖|餐后血糖|血糖', text):
        help_text.append('空腹血糖指至少 8 小时未进食后测得的血糖；餐后 2 小时血糖从第一口饭开始计时。')
    if re.search(r'家庭血压|在家量|自测血压', text):
        help_text.append('家庭自测血压的判读标准低于诊室测量，因此需要用同一台设备、安静休息后测量，并记录时间。')
    if re.search(r'血氧|氧饱和', text):
        help_text.append('指脉氧仪显示的是血氧饱和度估计值，末梢循环差、指甲油、手冷都可能影响读数，必要时复测。')
    return help_text


def web_query(metric: str | None, question: str) -> str:
    """Coarsened query: personal values are never sent to the search service."""
    if metric and metric in TOPIC_QUERY: return TOPIC_QUERY[metric]
    category = 'blood_pressure' if re.search(r'血压', question) else \
        'glucose' if re.search(r'血糖', question) else \
        'spo2' if re.search(r'血氧', question) else \
        'temperature' if re.search(r'体温|发烧|发热', question) else \
        'heart_rate' if re.search(r'心率|脉搏', question) else 'blood_pressure'
    return TOPIC_QUERY[category]


def strip_personal_values(text: str) -> str:
    return re.sub(r'\d{1,3}\s*/\s*\d{1,3}|\d+(?:\.\d+)?\s*(?:mmol/L|mg/dL|mmHg|%|℃|次/分|kg)', ' ', text)
