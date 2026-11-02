"""User-only health dialogue state. Never extracts facts from assistant answers."""
import re

from app.schemas.health import HealthDialogueState, HealthProfile
from app.services.health.triage import observations
from app.services.health.vitals import parse_text

METRICS = {
    '血压': 'blood_pressure', '高压': 'blood_pressure', '低压': 'blood_pressure',
    '血糖': 'glucose', '空腹血糖': 'fasting_glucose', '餐后血糖': 'postprandial_glucose',
    '血氧': 'spo2', '氧饱和': 'spo2', '心率': 'heart_rate', '脉搏': 'heart_rate',
    '体温': 'temperature', '发烧': 'temperature', '发热': 'temperature', '体重': 'weight',
}
TOPICS = {
    '就医': '就医时机', '去医院': '就医时机', '急诊': '就医时机', '什么时候看': '就医时机',
    '饮食': '生活方式', '吃什么': '生活方式', '运动': '生活方式', '锻炼': '生活方式', '盐': '生活方式',
    '检验单': '检验单', '化验': '检验单', '报告单': '检验单', '指标': '指标解读',
    '急救': '急救', '120': '急救',
}
CONDITIONS = {'高血压': 'hypertension', '糖尿病': 'diabetes', '肾病': 'ckd', '肾衰': 'ckd',
              '心衰': 'heart_failure', '心功能': 'heart_failure', '慢阻肺': 'copd', '中风': 'stroke_history', '脑梗': 'stroke_history'}
RESET = re.compile(r'换个人|另一个人|帮朋友|我父亲|我母亲|我爸爸|我妈妈|重新开始|换个话题')


def advance(state: HealthDialogueState, text: str, profile: HealthProfile | None = None) -> HealthDialogueState:
    state = state.model_copy(deep=True)
    if RESET.search(text): state = HealthDialogueState()
    for alias, metric in METRICS.items():
        if alias in text: state.metric = metric
    for alias, topic in TOPICS.items():
        if alias in text: state.topic = topic
    ages = re.findall(r'(?<!\d)(\d{1,3})\s*(?:周岁|岁)', text)
    if ages and len(set(ages)) == 1 and 0 <= int(ages[0]) <= 130:
        state.age = int(ages[0])
    for alias, code in CONDITIONS.items():
        if alias in text and code not in state.conditions: state.conditions.append(code)
    if profile and profile.age is not None: state.age = profile.age
    if profile:
        for code in profile.conditions:
            if code not in state.conditions: state.conditions.append(code)
    symptoms = observations(text)
    for symptom in symptoms:
        if symptom not in state.symptoms: state.symptoms.append(symptom)
    readings = parse_text(text)
    if readings:
        state.last_reading_keys = [f'{item.metric}:{item.systolic or item.value}' for item in readings][-6:]
        state.value_text = readings[0].raw[:80]
    return state


def build_dialogue(texts, base: HealthDialogueState | None = None, profile: HealthProfile | None = None) -> HealthDialogueState:
    state = base or HealthDialogueState()
    for text in texts:
        state = advance(state, text, profile)
    return state
