"""Editorial concept help and finite gap labels for the safety agent."""
import re

GAPS = {
    'fall_history': '过去一年的跌倒情况',
    'living_situation': '居住与照看情况',
    'mobility': '行走与平衡情况',
    'medication_list': '正在服用的药物',
    'home_layout': '居家房间与地面情况',
    'injury_detail': '跌倒后的受伤部位与活动能力',
    'environment_evidence': '尺寸与环境要求的资料依据',
    'full_safety_scope': '问题涉及的完整安全范围',
}

TOPIC_QUERY = {
    'fall_event': '老年人 跌倒后 应急处置 不要搬动 指南',
    'fall_prevention': '老年人 跌倒预防 居家 指南',
    'environment': '居家适老化改造 卫生间 扶手 防滑 照明 指南',
    'gait_aid': '老年人 手杖 助行器 选择 高度 指南',
    'exercise': '老年人 平衡训练 肌力训练 防跌倒 指南',
    'risk_assessment': '老年人 跌倒风险评估 危险因素 指南',
    'education': '老年人 跌倒 危险因素 健康教育',
}


def gap_message(gaps, partial: bool = False) -> str:
    labels = '、'.join(GAPS[key] for key in dict.fromkeys(gaps) if key in GAPS)
    return ('本次仅回答已有原文支持的部分；' if partial else '') + \
        '当前资料尚不足以核实' + (labels or '所问结论') + '。这不代表没有风险，建议请康复治疗师或社区医生上门评估。'


def concept_help(text: str) -> list[str]:
    tips = []
    if re.search(r'体位性低血压|站起来头晕', text):
        tips.append('体位性低血压指从躺到坐、从坐到站时血压明显下降，表现为头晕、眼前发黑；'
                    '起身时按"躺 30 秒、坐 30 秒、站 30 秒"缓慢改变体位。')
    if re.search(r'适老化改造|改造', text):
        tips.append('适老化改造的优先顺序通常是：先处理绊倒和滑倒风险（通道、地面、门槛），再装扶手与夜灯，最后考虑家具与卫浴设备。')
    if re.search(r'手杖|拐杖|助行器', text):
        tips.append('手杖高度一般以站立时手腕横纹附近为宜，握把与股骨大转子同高；具体需康复治疗师按身高和步态调整。')
    if re.search(r'跌倒风险|评估', text):
        tips.append('跌倒风险评估通常包括既往跌倒史、步态与平衡、视力、认知、用药和居家环境五部分，单项异常不等于高风险。')
    return tips


def web_query(intent: str, question: str) -> str:
    """Only topic words; no age, address, injury detail or identity."""
    if intent in TOPIC_QUERY: return TOPIC_QUERY[intent]
    if re.search(r'摔|跌倒|滑倒', question): return TOPIC_QUERY['fall_event']
    if re.search(r'扶手|防滑|改造|门槛|夜灯', question): return TOPIC_QUERY['environment']
    return TOPIC_QUERY['fall_prevention']
