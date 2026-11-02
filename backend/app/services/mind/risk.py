"""Crisis protocol, safety plan and supportive copy.

These blocks are fixed text: the model may talk with the person, but it never decides
whether a disclosure is a crisis, and it never writes the hotline number itself.
"""
import re

from app.schemas.mind import MindAssessment, MindProfile, MindTriage
from app.services.mind import emotions

CRISIS_NOTICE = ('我很在意你刚才说的话，谢谢你愿意告诉我。你现在承受的痛苦是真实的，不需要一个人扛。\n'
                 '请先做下面几件事，任何一件都可以马上做：\n'
                 '1. 如果已经有具体的打算，或已经做了伤害自己的事，请立刻拨打 120，或让身边的人陪你去最近的医院急诊。\n'
                 '2. 拨打全国心理援助热线 12356（24 小时），或当地精神卫生中心的心理援助电话，和专业的人说说话。\n'
                 '3. 联系一个你信任的人——家人、朋友、邻居或社区工作人员，请他现在过来陪你，尽量不要独处。\n'
                 '4. 把可能伤害自己的东西先交给家人收起来，或离开让你觉得危险的地方。\n'
                 '我想确认一下：你现在安全吗？有没有具体的计划？身边有没有人可以马上过来？')

CRISIS_LINE_NOTE = '如果此刻不方便说话，也可以先发消息给家人或社区工作人员，让他们知道你现在需要陪伴。'

SAFETY_PLAN = (
    '接下来几天可以做一个简单的安全计划：',
    '记下让自己情绪明显变差的信号，比如整夜睡不着、不想吃饭、反复想同一件事；',
    '写下两件难受时可以做的事，比如给某个人打电话、出门走十分钟；',
    '写下两个可以马上联系的人，再存好心理援助热线 12356；',
    '把药物和尖锐物品交给家人管理，难受时不要一个人待在房间里；',
    '如果出现伤害自己的念头，按这个计划马上求助，不要等到"撑不住"才说。',
)

GENERAL_TIPS = (
    '这几天先把生活节奏稳住：固定起床时间，白天出门晒一会儿太阳。',
    '难受时试试缓慢呼吸：吸气 4 秒、呼气 6 秒，重复两三分钟。',
    '每天至少和一个真人说几句话——家人、邻居、社区活动都算。',
    '睡前 1 小时不看手机、不喝浓茶咖啡；躺 20 分钟睡不着就起来坐一会儿再回床。',
    '把担心的事写下来，分成"现在能做的"和"现在做不了的"，先做前者。',
)

SLEEP_TIPS = (
    '固定起床时间比固定入睡时间更重要，周末也尽量保持一致。',
    '白天午睡不超过 30 分钟，下午三点后不喝浓茶和咖啡。',
    '睡前 1 小时把灯光调暗，不看让人激动的节目或手机。',
    '躺 20 分钟睡不着就起来坐一会儿，困了再回床，不要在床上反复看时间。',
)
GRIEF_TIPS = (
    '哀伤没有固定时间表，想哭、想说话、反复回忆都是正常的。',
    '可以留一个固定时段想他/她，其他时间把注意力放回当下的事情上。',
    '把想说的话写下来，或和同样认识他/她的人聊聊。',
    '如果一年后仍然无法正常生活，建议到精神科或心理科评估。',
)
SOCIAL_TIPS = (
    '先从低门槛的接触开始：和邻居打招呼、去社区活动室坐一会儿。',
    '参加有固定时间的活动更容易坚持，比如合唱、书法、太极、老年大学。',
    '和子女约定固定的通话时间，比"等他们想起来"更可靠。',
    '如果出门困难，可以先用电话或视频保持联系，再慢慢增加见面。',
)

RULES = {
    'suicidal_ideation': ('表达自杀或结束生命的念头', 'L1'),
    'suicidal_plan': ('有具体计划或准备', 'L1'),
    'self_harm': ('自我伤害行为', 'L1'),
    'immediate_danger': ('已采取伤害行为或处于危险环境', 'L1'),
    'psychosis': ('疑似精神病性症状', 'L1'),
    'violence': ('可能正在遭受暴力', 'L1'),
    'hopelessness': ('持续无望感', 'L2'),
    'screening_positive': ('近两周情绪低落伴兴趣减退', 'L2'),
    'grief_support': ('丧亲后的哀伤反应', 'L3'),
    'grief_prolonged': ('哀伤持续影响生活', 'L2'),
    'severe_insomnia': ('严重失眠影响白天功能', 'L2'),
    'sleep_difficulty': ('睡眠困难', 'L3'),
    'social_withdrawal': ('长期不出门、不见人', 'L3'),
    'loneliness': ('孤独感', 'L3'),
}


def triage(text: str, assessment: MindAssessment, profile: MindProfile) -> MindTriage:
    # A general "why do older people get insomnia" question is education, not a personal disclosure.
    educational = bool(re.search(r'为什么|什么是|怎么回事|如何改善|有哪些|怎么办才|是什么原因', text)) and \
        not re.search(r'我|最近|总是|这段时间|这几天|一直', text)
    ids = {signal.id for signal in assessment.signals}
    rules: list[str] = []
    if 'immediate_danger' in ids: rules.append('immediate_danger')
    if 'suicidal_plan' in ids: rules.append('suicidal_plan')
    if 'self_harm' in ids: rules.append('self_harm')
    if 'suicidal_ideation' in ids: rules.append('suicidal_ideation')
    if 'psychosis' in ids: rules.append('psychosis')
    if 'violence' in ids: rules.append('violence')
    if 'hopelessness' in ids: rules.append('hopelessness')
    if assessment.screening.positive: rules.append('screening_positive')
    loss = profile.recent_loss or any(signal.label == '丧偶或亲友离世' for signal in assessment.signals)
    if loss:
        if re.search(r'一年|两年|半年多|还是无法|不能正常生活', text):
            rules.append('grief_prolonged')
        else:
            rules.append('grief_support')
    sleep = any(word in text for word in ('睡不着', '失眠', '早醒', '整夜', '睡不好', '入睡难'))
    if sleep and any(word in text for word in ('白天没精神', '白天困', '影响白天', '整夜', '半个月', '一个月')):
        rules.append('severe_insomnia')
    elif sleep:
        rules.append('sleep_difficulty')
    if any(word in text for word in ('不想出门', '不见人', '半年没出门', '没朋友')):
        rules.append('social_withdrawal')
    if any(word in text for word in ('孤独', '寂寞', '没人说话')):
        rules.append('loneliness')

    if educational and assessment.risk_level == 'low':
        return MindTriage(level='L4', rule_ids=[], required_action='self_care',
                          red_flags=[], table_version=emotions.TABLE_VERSION)
    if assessment.risk_level in {'critical', 'high'} or ids & {'suicidal_ideation', 'suicidal_plan', 'self_harm',
                                                                'immediate_danger', 'psychosis', 'violence'}:
        level = 'L1'
    elif assessment.risk_level == 'medium' or any(rule in {'hopelessness', 'screening_positive', 'grief_prolonged',
                                                           'severe_insomnia'} for rule in rules):
        level = 'L2'
    elif rules:
        level = 'L3'
    else:
        level = 'L4'
    if level == 'L1':
        action = 'emergency_120' if ids & {'immediate_danger', 'self_harm'} else 'crisis_line'
    elif level == 'L2':
        action = 'mental_health_referral'
    else:
        action = 'self_care'
    red_flags = [emotions.risk_labels(assessment)[0]] if emotions.risk_labels(assessment) else []
    red_flags = emotions.risk_labels(assessment) or [RULES[rule][0] for rule in rules if rule in RULES]
    return MindTriage(level=level, rule_ids=list(dict.fromkeys(rules)), required_action=action,
                      red_flags=red_flags, table_version=emotions.TABLE_VERSION)


def crisis_text(triage: MindTriage) -> str:
    return CRISIS_NOTICE


def safety_plan_text() -> list[str]:
    return list(SAFETY_PLAN)


def tips_for(intent: str) -> list[str]:
    if intent == 'sleep': return list(SLEEP_TIPS)
    if intent == 'grief': return list(GRIEF_TIPS)
    if intent in {'loneliness', 'social_connection'}: return list(SOCIAL_TIPS)
    return list(GENERAL_TIPS)


def referral_text(triage: MindTriage) -> str:
    if triage.level == 'L1': return '请现在就把上面这几件事做起来，尤其是拨打 12356 或 120，并让身边的人过来陪你。'
    if triage.level == 'L2': return '建议在 1–2 周内到精神科或心理科门诊评估，去的时候可以带上这几周的睡眠、情绪和用药记录。'
    if triage.level == 'L3': return '如果这种状态持续两周以上，或者开始影响吃饭睡觉，建议找家庭医生或心理咨询师聊一次。'
    return ''
