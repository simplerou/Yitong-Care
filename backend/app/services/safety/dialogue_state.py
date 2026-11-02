"""User-only safety dialogue state. Falls, living situation and drugs come from user words."""
import re

from app.schemas.safety import SafetyDialogueState, SafetyProfile

CONDITION_WORDS = {
    '骨质疏松': 'osteoporosis', '帕金森': 'parkinson', '中风': 'stroke_history', '脑梗': 'stroke_history',
    '偏瘫': 'stroke_history', '关节炎': 'arthritis', '糖尿病': 'diabetes', '高血压': 'hypertension',
    '心脏病': 'heart_disease', '房颤': 'heart_disease', '痴呆': 'cognitive_impairment',
    '认知障碍': 'cognitive_impairment', '眩晕': 'vertigo', '美尼尔': 'vertigo',
}
DRUG_WORDS = {
    '安眠药': '安眠药', '地西泮': '地西泮', '阿普唑仑': '阿普唑仑', '艾司唑仑': '艾司唑仑',
    '唑吡坦': '唑吡坦', '佐匹克隆': '佐匹克隆', '降压药': '降压药', '氨氯地平': '氨氯地平',
    '缬沙坦': '缬沙坦', '美托洛尔': '美托洛尔', '华法林': '华法林', '利伐沙班': '利伐沙班',
    '达比加群': '达比加群', '阿司匹林': '阿司匹林', '氯吡格雷': '氯吡格雷',
    '降糖药': '降糖药', '胰岛素': '胰岛素', '格列美脲': '格列美脲',
}
ROOM_WORDS = {'卫生间': '卫生间', '厕所': '卫生间', '浴室': '卫生间', '卧室': '卧室', '客厅': '客厅',
              '厨房': '厨房', '楼梯': '楼梯', '门口': '门口', '玄关': '门口'}
TOPICS = {
    '摔倒': 'fall_event', '跌倒': 'fall_event', '滑倒': 'fall_event',
    '预防': 'fall_prevention', '防跌倒': 'fall_prevention',
    '扶手': 'environment', '防滑': 'environment', '改造': 'environment', '夜灯': 'environment',
    '拐杖': 'gait_aid', '助行器': 'gait_aid', '手杖': 'gait_aid',
    '训练': 'exercise', '太极': 'exercise',
}
FALL_COUNT = {'一次': 1, '1次': 1, '两次': 2, '2次': 2, '三次': 3, '3次': 3, '好几次': 3, '多次': 3}


def infer_profile(profile: SafetyProfile, text: str) -> SafetyProfile:
    text = text or ''
    conditions = list(profile.conditions)
    for word, code in CONDITION_WORDS.items():
        if word in text and code not in conditions: conditions.append(code)
    medications = list(profile.medications)
    for word, canonical in DRUG_WORDS.items():
        if word in text and canonical not in medications: medications.append(canonical)
    previous = profile.previous_falls
    for word, count in FALL_COUNT.items():
        if re.search(r'(?:摔|跌|滑倒)[^。；\n]{0,6}' + re.escape(word), text):
            previous = max(previous or 0, count)
    if previous is None and re.search(r'摔过|跌倒过', text): previous = 1
    living_alone = profile.living_alone or bool(re.search(r'独居|一个人住|自己住|没人照顾', text))
    mobility = profile.mobility
    if re.search(r'坐轮椅', text): mobility = 'wheelchair'
    elif re.search(r'助行器|助行架', text): mobility = 'walker'
    elif re.search(r'拄拐|拐杖|手杖', text): mobility = 'cane'
    elif re.search(r'走不稳|腿没劲|需要扶|卧床', text) and mobility == 'independent': mobility = 'cane'
    vision = 'impaired' if re.search(r'看不清|视力下降|白内障', text) else profile.vision
    cognition = 'impaired' if re.search(r'记不住|糊涂|痴呆|认知', text) else profile.cognition
    return profile.model_copy(update={'conditions': conditions, 'medications': medications,
                                      'previous_falls': previous, 'living_alone': living_alone,
                                      'mobility': mobility, 'vision': vision, 'cognition': cognition})


def advance(state: SafetyDialogueState, text: str, profile: SafetyProfile | None = None) -> SafetyDialogueState:
    state = state.model_copy(deep=True)
    if re.search(r'换个人|重新开始|换个话题', text): state = SafetyDialogueState()
    for word, topic in TOPICS.items():
        if word in text: state.topic = topic
    effective = infer_profile(profile or SafetyProfile(), text)
    for condition in effective.conditions:
        if condition not in state.conditions: state.conditions.append(condition)
    for drug in effective.medications:
        if drug not in state.medications: state.medications.append(drug)
    if effective.previous_falls: state.previous_falls = effective.previous_falls
    if effective.living_alone: state.living_alone = True
    state.mobility = effective.mobility
    for word, room in ROOM_WORDS.items():
        if word in text and room not in state.rooms: state.rooms.append(room)
    return state


def build_dialogue(texts, base: SafetyDialogueState | None = None,
                   profile: SafetyProfile | None = None) -> SafetyDialogueState:
    state = base or SafetyDialogueState()
    for text in texts:
        state = advance(state, text, profile)
    return state
