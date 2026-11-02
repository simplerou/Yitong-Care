"""Editorial concept help and finite gap labels, separate from cited drug facts."""
import re

GAPS = {
    'drug_list': '完整的在服药物清单',
    'dose_frequency': '每种药每天服用几次',
    'last_dose_time': '上次服药的时间',
    'symptom_detail': '症状出现的时间与具体表现',
    'interaction_evidence': '相互作用的说明书或资料依据',
    'timing_evidence': '服用时间与进食关系的资料依据',
    'adverse_evidence': '不良反应的判断依据',
    'full_medication_scope': '问题涉及的完整用药范围',
}


def gap_message(gaps, partial: bool = False) -> str:
    labels = '、'.join(GAPS[key] for key in dict.fromkeys(gaps) if key in GAPS)
    return ('本次仅回答已有原文支持的部分；' if partial else '') + \
        '当前资料尚不足以核实' + (labels or '所问结论') + '。这不代表不存在相关风险，建议让医生或药师核对。'


def concept_help(text: str) -> list[str]:
    tips = []
    if re.search(r'缓释|控释', text):
        tips.append('缓释片、控释片通过特殊工艺让药物缓慢释放，通常需要整片吞服，不能掰开或嚼碎；'
                    '掰开可能让药物一次性释放，增加不良反应风险。')
    if re.search(r'饭前|饭后|空腹|随餐', text):
        tips.append('饭前一般指餐前 30 分钟到 1 小时，饭后一般指餐后 15–30 分钟，随餐指与食物同服；'
                    '具体时间以说明书写明的为准。')
    if re.search(r'半衰期', text):
        tips.append('半衰期指体内药物浓度下降一半所需时间，它影响服药间隔和漏服后的处理，具体数值以说明书为准。')
    if re.search(r'相互作用', text):
        tips.append('药物相互作用分两类：一类影响药物在体内的吸收、代谢和排出，另一类影响药效或毒性叠加；'
                    '是否需要调整由医生或药师结合具体情况判断。')
    if re.search(r'保健品', text):
        tips.append('保健品不是药品，不能替代治疗，但部分成分（如银杏、鱼油、大蒜提取物、维生素 K）会影响抗凝药等处方药。')
    return tips


def web_query(drugs: list[str], topic: str) -> str:
    """Only generic names and a topic word: no personal data is sent to search."""
    names = ' '.join(drugs[:3]) if drugs else '老年 常用药'
    topic_word = {
        'timing': '说明书 服用时间 饭前 饭后',
        'missed_dose': '漏服 补服 说明书',
        'interaction': '相互作用 说明书',
        'adverse_reaction': '不良反应 说明书',
        'duplication': '重复成分 说明书',
        'education': '说明书 用法 注意事项',
    }.get(topic, '说明书 注意事项')
    return f'{names} {topic_word}'
