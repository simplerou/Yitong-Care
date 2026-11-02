"""Editorial concept help and finite gap labels, separate from cited diet facts."""
import re

GAPS = {
    'condition_list': '老人的慢病情况',
    'chewing_swallowing': '咀嚼和吞咽情况',
    'weight_trend': '近三个月的体重变化',
    'allergy_list': '食物过敏史',
    'medication_list': '正在服用的药物',
    'portion_evidence': '份量的资料依据',
    'menu_evidence': '食谱搭配的资料依据',
    'full_diet_scope': '问题涉及的完整膳食范围',
}

TOPIC_QUERY = {
    'meal_plan': '老年人 一日三餐 膳食搭配 指南',
    'protein': '老年人 蛋白质 补充 优质蛋白 指南',
    'salt_control': '老年人 控盐 控油 高血压 膳食 指南',
    'fruit_staple': '糖尿病 老年人 水果 主食 粗粮 膳食 指南',
    'texture': '老年人 吞咽困难 软食 质地 膳食 指南',
    'food_safety': '老年人 食品安全 剩菜 储存 指南',
    'condition_diet': '慢性肾脏病 心力衰竭 痛风 膳食 原则 指南',
    'food_drug': '食物 药物 相互作用 膳食 指南',
}


def gap_message(gaps, partial: bool = False) -> str:
    labels = '、'.join(GAPS[key] for key in dict.fromkeys(gaps) if key in GAPS)
    return ('本次仅回答已有原文支持的部分；' if partial else '') + \
        '当前资料尚不足以核实' + (labels or '所问结论') + '。这不代表不存在相关建议，具体请咨询营养师。'


def concept_help(text: str) -> list[str]:
    tips = []
    if re.search(r'优质蛋白', text):
        tips.append('优质蛋白指氨基酸组成接近人体需要、吸收利用率高的蛋白质，常见于鸡蛋、奶、鱼、瘦肉和大豆制品。')
    if re.search(r'升糖指数|GI', text, re.I):
        tips.append('升糖指数反映食物升高血糖的速度；同一种食物加工越细、煮得越烂，通常升糖越快。')
    if re.search(r'膳食纤维', text):
        tips.append('膳食纤维来自全谷物、杂豆、蔬菜和水果，有助于改善便秘；增加时要同时增加饮水，循序渐进。')
    if re.search(r'低钠盐', text):
        tips.append('低钠盐用部分钾替代钠，并非人人适合：肾功能不全或正在使用保钾药物的人需要先咨询医生。')
    if re.search(r'少食多餐', text):
        tips.append('少食多餐指把一天食物分成 4–5 次，适合食欲差或消化能力弱的老年人，具体安排以营养师建议为准。')
    return tips


def web_query(intent: str, question: str) -> str:
    """Only topic words; no age, weight, symptoms or identity."""
    if intent in TOPIC_QUERY: return TOPIC_QUERY[intent]
    if re.search(r'肾|透析', question): return TOPIC_QUERY['condition_diet']
    if re.search(r'糖尿病|血糖', question): return TOPIC_QUERY['fruit_staple']
    if re.search(r'盐|咸|血压', question): return TOPIC_QUERY['salt_control']
    return TOPIC_QUERY['meal_plan']
