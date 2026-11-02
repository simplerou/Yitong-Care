"""User-only mind dialogue state: mood words, duration, sleep and support."""
import re

from app.schemas.mind import MindDialogueState, MindProfile

TOPICS = {
    '睡不着': 'sleep', '失眠': 'sleep', '睡不好': 'sleep',
    '老伴': 'grief', '去世': 'grief', '走了': 'grief',
    '孤独': 'loneliness', '没人说话': 'loneliness', '不想出门': 'loneliness',
    '吵架': 'family_conflict', '矛盾': 'family_conflict',
    '退休': 'retirement',
    '朋友': 'social_connection', '活动': 'social_connection',
}
MOODS = ('难过', '伤心', '低落', '焦虑', '害怕', '孤独', '寂寞', '烦躁', '内疚', '没意思', '无望', '绝望')


def infer_profile(profile: MindProfile, text: str) -> MindProfile:
    text = text or ''
    living_alone = profile.living_alone or bool(re.search(r'独居|一个人住|自己住|没人照顾', text))
    recent_loss = profile.recent_loss or bool(re.search(r'老伴走了|去世|走了|丧偶|白发人送黑发人', text))
    confidant = profile.has_confidant
    if re.search(r'没人说话|没有朋友|没人管|一个人', text): confidant = False
    elif re.search(r'子女|女儿|儿子|朋友|邻居|社区', text): confidant = True
    conditions = list(profile.conditions)
    if re.search(r'抑郁(?:症)?史|以前抑郁', text) and 'depression_history' not in conditions:
        conditions.append('depression_history')
    medications = list(profile.medications)
    for word, canonical in (('安眠药', '安眠药'), ('抗抑郁药', '抗抑郁药'), ('舍曲林', '舍曲林'), ('艾司西酞普兰', '艾司西酞普兰')):
        if word in text and canonical not in medications: medications.append(canonical)
    return profile.model_copy(update={'living_alone': living_alone, 'recent_loss': recent_loss,
                                      'has_confidant': confidant, 'conditions': conditions,
                                      'medications': medications})


def advance(state: MindDialogueState, text: str) -> MindDialogueState:
    state = state.model_copy(deep=True)
    if re.search(r'换个话题|说点别的', text): state = MindDialogueState()
    for word, topic in TOPICS.items():
        if word in text: state.topic = topic
    for word in MOODS:
        if word in text and word not in state.mood_words: state.mood_words.append(word)
    state.mood_words = state.mood_words[-10:]
    duration = re.search(r'(?:两|2|半|一|几)\s*(?:个)?(?:星期|周|月)|半个月|很久|好几年', text)
    if duration: state.duration = duration.group(0)
    sleep = re.search(r'整夜睡不着|入睡难|早醒|睡不好|睡不着|失眠', text)
    if sleep: state.sleep = sleep.group(0)
    support = re.search(r'(?:女儿|儿子|老伴|朋友|邻居|社区|志愿者)', text)
    if support: state.support_person = support.group(0)
    loss = re.search(r'老伴走了|老伴去世|丧偶|白发人送黑发人', text)
    if loss and loss.group(0) not in state.losses: state.losses.append(loss.group(0))
    return state


def build_dialogue(texts, base: MindDialogueState | None = None,
                   profile: MindProfile | None = None) -> MindDialogueState:
    # profile is re-applied by the orchestrator; the dialogue state only keeps user words.
    state = base or MindDialogueState()
    for text in texts:
        state = advance(state, text)
    return state
