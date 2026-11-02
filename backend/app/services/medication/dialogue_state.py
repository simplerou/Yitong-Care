"""User-only medication dialogue state. Never extracts facts from assistant answers."""
import re

from app.schemas.medication import MedicationDialogueState, MedicationProfile
from app.services.medication.drugs import parse_frequency, triage

TOPICS = {
    '漏服': 'missed_dose', '忘了吃': 'missed_dose', '忘记吃': 'missed_dose',
    '一起吃': 'interaction', '同服': 'interaction', '相互作用': 'interaction', '冲突': 'interaction',
    '怎么吃': 'timing', '什么时候吃': 'timing', '饭前': 'timing', '饭后': 'timing', '空腹': 'timing',
    '副作用': 'adverse_reaction', '不良反应': 'adverse_reaction', '不舒服': 'adverse_reaction',
    '重复': 'duplication', '成分': 'duplication',
    '加量': 'dose_change', '减量': 'dose_change', '停药': 'stop_or_switch', '换药': 'stop_or_switch',
}
RESET = re.compile(r'换个人|另一个人|帮朋友|重新开始|换个话题|说别的药')


def advance(state: MedicationDialogueState, text: str, profile: MedicationProfile | None = None,
            drugs: list[str] | None = None) -> MedicationDialogueState:
    state = state.model_copy(deep=True)
    if RESET.search(text): state = MedicationDialogueState()
    for word, topic in TOPICS.items():
        if word in text: state.topic = topic
    frequency = parse_frequency(text)
    if frequency != 'unknown': state.frequency = frequency
    ages = re.findall(r'(?<!\d)(\d{1,3})\s*(?:周岁|岁)', text)
    if ages and len(set(ages)) == 1 and 0 <= int(ages[0]) <= 130:
        state.age = int(ages[0])
    if profile:
        if profile.age is not None: state.age = profile.age
        for condition in profile.conditions:
            if condition not in state.conditions: state.conditions.append(condition)
    if drugs:
        for name in drugs:
            if name not in state.drugs: state.drugs.append(name)
        state.drugs = state.drugs[-12:]
    from app.services.medication import drugs as drug_rules
    assessment = drug_rules.assess(text, [])
    triage_result = triage(assessment, text, profile)
    for label in triage_result.red_flags:
        if label not in state.symptoms: state.symptoms.append(label)
    state.symptoms = state.symptoms[-10:]
    return state


def build_dialogue(texts, base: MedicationDialogueState | None = None,
                  profile: MedicationProfile | None = None) -> MedicationDialogueState:
    state = base or MedicationDialogueState()
    for text in texts:
        state = advance(state, text, profile)
    return state
