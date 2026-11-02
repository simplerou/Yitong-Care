"""Emotion lexicon and a conservative PHQ-2 style screen.

The screen is a prompt to seek assessment, never a diagnosis.
"""
import re

from app.schemas.mind import MindAssessment, MindProfile, RiskSignal, ScreeningResult

TABLE_VERSION = 'mind-screen-2026.1'

MOOD_WORDS = ('难过', '伤心', '想哭', '低落', '没意思', '空虚', '烦躁', '焦虑', '害怕', '担心',
              '委屈', '生气', '内疚', '自责', '无望', '绝望', '累', '压抑', '孤独', '寂寞', '没劲')
TRIGGER_WORDS = {
    '丧偶或亲友离世': ('丧偶', '老伴走了', '老伴去世', '去世', '走了', '白发人送黑发人', '葬礼'),
    '退休或角色变化': ('退休', '不上班', '没工作', '闲下来'),
    '子女不在身边': ('子女不在', '孩子不在', '儿女不在', '见不到孩子', '没人来看'),
    '独居或社交减少': ('独居', '一个人住', '自己住', '没朋友', '没人说话', '不想出门', '不见人'),
    '疾病或失能': ('生病', '住院', '失能', '卧床', '慢性病', '疼'),
}
RISK_WORDS = {
    'suicidal_ideation': ('自杀', '不想活', '活着没意思', '想死', '死了算了', '结束生命', '了结', '轻生',
                          '不想拖累', '解脱'),
    'suicidal_plan': ('计划', '方法', '遗书', '告别', '攒药', '攒了药', '准备好了', '选好日子'),
    'self_harm': ('自残', '割腕', '伤害自己', '打自己', '撞墙'),
    'immediate_danger': ('已经吃了', '已经吃', '已经服药', '吃药了', '吃了一瓶', '已经割', '割了',
                         '在楼顶', '在天台', '手里有刀', '正在流血', '吃了一把'),
    'psychosis': ('有人要害我', '听到声音', '命令我', '被监视', '有人在说我'),
    'violence': ('被打', '家暴', '虐待', '锁起来', '不给吃饭', '打我'),
    'hopelessness': ('看不到希望', '撑不下去', '熬不下去', '没意义', '没有意义'),
}
PROTECTIVE_WORDS = {
    '有家人或朋友可依靠': ('家人', '老伴', '孩子', '女儿', '儿子', '朋友', '邻居', '志愿者'),
    '有宠物或爱好': ('猫', '狗', '宠物', '种花', '下棋', '跳舞', '唱戏', '书法', '太极'),
    '有求助意愿': ('想找人聊聊', '想咨询', '想看看医生', '想求助'),
}
SLEEP_WORDS = ('睡不着', '失眠', '早醒', '整夜', '睡不好', '入睡难', '睡眠差')
ANHEDONIA_WORDS = ('没兴趣', '不想做', '提不起劲', '什么都不想干', '没劲', '不想动')
FUNCTION_WORDS = ('上不了班', '做不了饭', '起不来床', '什么都不想做', '影响生活', '不想吃饭', '没法照顾自己')
TWO_WEEKS = re.compile(r'两(?:个)?星期|两(?:个)?周|半个?月|半个月|两周|一直|这段时间|最近.{0,4}(?:都|总)')


def _present(text: str, words) -> list[str]:
    found = []
    for word in words:
        if word in text: found.append(word)
    return found


def _negated(text: str, word: str) -> bool:
    for match in re.finditer(re.escape(word), text):
        prefix = text[max(0, match.start() - 6):match.start()]
        if re.search(r'(?:没有|没|不|无|未|并不)[^。；\n]{0,4}$', prefix): continue
        return False
    return True


def assessment(text: str, profile: MindProfile) -> MindAssessment:
    signals: list[RiskSignal] = []
    for word in MOOD_WORDS:
        if word in text and not _negated(text, word):
            signals.append(RiskSignal(id=f'mood_{word}', label=word, kind='risk', detail='情绪词'))
    for label, words in TRIGGER_WORDS.items():
        if any(word in text for word in words):
            signals.append(RiskSignal(id='trigger', label=label, kind='trigger'))
    for signal_id, words in RISK_WORDS.items():
        if any(word in text and not _negated(text, word) for word in words):
            signals.append(RiskSignal(id=signal_id, label=signal_id, kind='risk'))
    for label, words in PROTECTIVE_WORDS.items():
        if any(word in text for word in words):
            signals.append(RiskSignal(id='protective', label=label, kind='protective'))
    if profile.recent_loss:
        signals.append(RiskSignal(id='loss', label='近期失去亲人', kind='trigger'))

    low_mood = any(word in text for word in MOOD_WORDS) or bool(re.search(r'心情不好|情绪低落|高兴不起来|闷闷不乐', text))
    anhedonia = any(word in text for word in ANHEDONIA_WORDS)
    two_weeks = bool(TWO_WEEKS.search(text))
    impairment = any(word in text for word in FUNCTION_WORDS)
    screening = ScreeningResult(low_mood=low_mood, anhedonia=anhedonia, duration_two_weeks=two_weeks,
                                functional_impairment=impairment,
                                positive=bool(low_mood and anhedonia and (two_weeks or impairment)),
                                note='这不是诊断，只是提示可以与专业人员进一步评估。')

    critical = {'immediate_danger', 'suicidal_plan', 'self_harm'}
    high = {'suicidal_ideation', 'psychosis', 'violence'}
    ids = {signal.id for signal in signals}
    if ids & critical: level = 'critical'
    elif ids & high: level = 'high'
    elif screening.positive or 'hopelessness' in ids or impairment: level = 'medium'
    else: level = 'low'
    if profile.conditions and 'depression_history' in profile.conditions and level == 'low':
        signals.append(RiskSignal(id='history', label='既往抑郁史', kind='risk'))
    return MindAssessment(signals=signals, screening=screening, risk_level=level, table_version=TABLE_VERSION)


def risk_labels(assessment: MindAssessment) -> list[str]:
    labels = []
    ids = {signal.id for signal in assessment.signals}
    if 'immediate_danger' in ids: labels.append('已采取伤害行为或处于危险环境')
    if 'suicidal_plan' in ids: labels.append('有具体计划或准备')
    if 'suicidal_ideation' in ids: labels.append('表达自杀意念')
    if 'self_harm' in ids: labels.append('自我伤害行为')
    if 'psychosis' in ids: labels.append('疑似精神病性症状')
    if 'violence' in ids: labels.append('可能遭受暴力')
    if 'hopelessness' in ids: labels.append('持续无望感')
    if assessment.screening.positive: labels.append('近两周情绪低落伴兴趣减退')
    return labels
