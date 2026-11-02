"""Editorial concept help and finite gap labels for the mind companion."""
import re

GAPS = {
    'mood_detail': '最近的睡眠、食欲和情绪变化',
    'duration': '这种状态持续了多久',
    'sleep_detail': '具体睡眠情况',
    'support_person': '身边可以联系的人',
    'safety_status': '现在是否安全',
    'grief_context': '失去亲人或生活变化的情况',
    'social_situation': '目前的居住与社交情况',
    'evidence': '相关心理关怀资料',
}

TOPIC_QUERY = {
    'emotional_support': '老年人 情绪支持 倾听 陪伴 心理关怀 指南',
    'loneliness': '老年人 孤独感 社交连接 社区活动 心理关怀',
    'grief': '老年人 丧亲 哀伤反应 陪伴 心理关怀',
    'sleep': '老年人 失眠 睡眠卫生 心理关怀 指南',
    'family_conflict': '老年人 家庭矛盾 沟通 心理关怀',
    'retirement': '退休适应 角色转变 老年人 心理调适',
    'social_connection': '老年人 社交活动 社区参与 心理关怀',
    'education': '老年心理 情绪 常见问题 科普',
}


def gap_message(gaps, partial: bool = False) -> str:
    labels = '、'.join(GAPS[key] for key in dict.fromkeys(gaps) if key in GAPS)
    return ('本次仅回答已有资料支持的部分；' if partial else '') + \
        '当前资料还不足以说清楚' + (labels or '所问的情况') + '。如果方便，可以再多说一点，我陪你一起理一理。'


def concept_help(text: str) -> list[str]:
    tips = []
    if re.search(r'哀伤|丧偶|走了', text):
        tips.append('哀伤是失去重要的人之后的正常反应，可能反复出现想念、愧疚、愤怒和麻木，通常随时间起伏而不是直线变好。')
    if re.search(r'失眠|睡不着', text):
        tips.append('睡眠卫生包括固定起床时间、白天见光、睡前减少刺激；躺床上超过二十分钟睡不着可以先起来坐一会儿。')
    if re.search(r'抑郁|情绪低落', text):
        tips.append('情绪低落和兴趣减退持续两周以上、影响生活时，专业人员通常会用问卷进一步评估；这不是给人贴标签。')
    if re.search(r'孤独|没人说话', text):
        tips.append('社交连接的关键是"固定"和"低门槛"：固定时间的活动比偶尔的聚会更容易坚持。')
    return tips


def web_query(intent: str, question: str) -> str:
    if intent in TOPIC_QUERY: return TOPIC_QUERY[intent]
    if re.search(r'睡|失眠', question): return TOPIC_QUERY['sleep']
    if re.search(r'老伴|去世|走了', question): return TOPIC_QUERY['grief']
    if re.search(r'孤独|没人|朋友', question): return TOPIC_QUERY['loneliness']
    return TOPIC_QUERY['emotional_support']
