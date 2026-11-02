"""Deterministic red-flag triage over user text and parsed readings.

The model never sets the urgency level. Rules only read the user's own words and the
parser output, so a model timeout cannot suppress an emergency referral.
"""
import re

from app.schemas.health import HealthProfile, Triage, VitalsAssessment
from app.services.health.vitals import TABLE_VERSION

LEVELS = ['L1', 'L2', 'L3', 'L4']
ACTIONS = {'L1': 'call_120', 'L2': 'contact_doctor_24h', 'L3': 'clinic_visit', 'L4': 'self_care'}

LABELS = {
    'chest_pain_15min': '胸痛或胸闷持续不缓解',
    'stroke_fast': '疑似卒中表现（口角歪斜、言语不清、单侧无力等）',
    'dyspnea_rest': '静息状态呼吸困难',
    'altered_consciousness': '意识模糊、晕厥或抽搐',
    'bp_crisis_symptom': '血压达危象范围并伴症状',
    'bp_crisis_no_symptom': '血压达危象范围',
    'hypoglycemia_severe': '严重低血糖范围',
    'hypoglycemia': '低血糖范围',
    'spo2_critical': '血氧饱和度低于 90%',
    'temp_hyperpyrexia': '超高热（≥41℃）',
    'hr_extreme_symptom': '心率极端异常并伴症状',
    'gi_bleeding': '呕血、黑便或便血',
    'fall_head_injury': '跌倒后头部外伤或髋部不能站立',
    'self_harm': '自伤或自杀意念表述',
    'bp_stage3_persistent': '血压 ≥180/110 mmHg',
    'bp_stage2': '血压 ≥160/100 mmHg',
    'bp_stage1': '血压达 1 级范围',
    'bp_low': '血压偏低',
    'glucose_fasting_high': '空腹血糖 ≥11.1 mmol/L',
    'glucose_very_high': '血糖显著升高（≥16.7 mmol/L）',
    'glucose_above_cutoff': '血糖达到糖尿病诊断切点',
    'glucose_impaired': '空腹血糖受损或糖耐量减低',
    'spo2_low': '血氧饱和度 90–94%',
    'hr_abnormal_rest': '静息心率异常（<50 或 >110 次/分）',
    'fever_high': '高热（≥39℃）',
    'fever_moderate': '中度发热',
    'hypothermia': '体温过低（<35℃）',
    'symptom_alert': '用户描述了需要关注的症状',
}

L1_RULES = {'chest_pain_15min', 'stroke_fast', 'dyspnea_rest', 'altered_consciousness', 'bp_crisis_symptom',
            'hypoglycemia_severe', 'spo2_critical', 'temp_hyperpyrexia', 'hr_extreme_symptom', 'gi_bleeding',
            'fall_head_injury', 'self_harm'}
L2_RULES = {'bp_crisis_no_symptom', 'bp_stage3_persistent', 'hypoglycemia', 'spo2_low', 'hr_abnormal_rest',
            'fever_high', 'glucose_fasting_high', 'glucose_very_high', 'hypothermia'}
L3_RULES = {'bp_stage2', 'bp_stage1', 'bp_low', 'glucose_above_cutoff', 'glucose_impaired', 'fever_moderate'}

CHEST = ('胸痛', '胸口痛', '胸闷', '心口痛', '胸口发紧', '压得慌', '胸部压榨')
STROKE = ('口角歪斜', '嘴歪', '说话不清', '言语不清', '口齿不清', '一侧无力', '半边无力', '单侧无力',
          '一侧手脚', '半边身子', '视物模糊', '看不见', '眼前发黑')
DYSPNEA = ('呼吸困难', '喘不上气', '喘不过气', '憋气', '不能平卧', '躺不下', '呼吸费力')
CONSCIOUSNESS = ('意识模糊', '意识不清', '叫不醒', '晕倒', '晕厥', '抽搐', '昏迷', '说胡话')
FALL = ('摔倒', '跌倒', '摔了一跤', '摔伤')
GI_BLEEDING = ('呕血', '吐血', '黑便', '大便发黑', '便血', '血便')
SELF_HARM = ('自杀', '不想活', '活着没意思', '想死', '伤害自己', '结束生命', '轻生')
CRISIS_SYMPTOMS = ('头痛', '头晕', '胸痛', '胸闷', '呼吸困难', '视物模糊', '看不清', '恶心', '呕吐', '意识')
HYPO_SYMPTOMS = ('出汗', '心慌', '手抖', '发抖', '乏力', '意识', '头晕')
HR_SYMPTOMS = ('头晕', '黑矇', '眼前发黑', '胸痛', '胸闷', '晕')
RELIEVED = ('已缓解', '好多了', '不痛了', '已经好了', '缓解了', '没事了', '稳定了')
CONCEPTUAL = ('什么是', '是什么', '指的是', '定义', '有什么区别', '有什么区别', '有哪些', '如何预防', '怎么预防', '一般怎么')
PERSONAL = ('我', '俺', '我爸', '我妈', '父亲', '母亲', '爷爷', '奶奶', '外公', '外婆', '老人', '家里',
            '爱人', '丈夫', '妻子', '老伴', '刚才', '今天', '今早', '昨晚', '这几天')

NEGATION = re.compile(r'(?:没有|没|无|未|不|否认|并非|从不|排除)[^。；\n]{0,4}$')


def matched(text: str, words) -> list[str]:
    """Return symptom words that appear without a local negation ('没有胸痛' does not match)."""
    found = []
    for word in words:
        for match in re.finditer(re.escape(word), text):
            prefix = text[max(0, match.start() - 8):match.start()]
            if NEGATION.search(prefix): continue
            found.append(word)
            break
    return found


def relieved(text: str) -> bool:
    return any(word in text for word in RELIEVED)


def conceptual(text: str) -> bool:
    return any(word in text for word in CONCEPTUAL)


def personal(text: str) -> bool:
    return any(word in text for word in PERSONAL)


def _add(state: dict, rule_id: str) -> None:
    if rule_id not in state['rules']: state['rules'].append(rule_id)


def triage_of(assessment: VitalsAssessment, text: str, profile: HealthProfile | None = None) -> Triage:
    text = text or ''
    state = {'rules': []}
    readings = [item for item in assessment.readings if item.category_code != 'unverified']
    has_reading = bool(readings)
    is_concept = conceptual(text) and not has_reading
    symptoms = matched(text, CRISIS_SYMPTOMS)

    for reading in readings:
        code = reading.category_code
        value = reading.value or 0
        if reading.metric == 'blood_pressure':
            if code == 'crisis':
                _add(state, 'bp_crisis_symptom' if symptoms else 'bp_crisis_no_symptom')
            elif code == 'stage3': _add(state, 'bp_stage3_persistent')
            elif code == 'stage2': _add(state, 'bp_stage2')
            elif code == 'stage1': _add(state, 'bp_stage1')
            elif code == 'low': _add(state, 'bp_low')
        elif reading.metric.endswith('glucose'):
            if code == 'severe_low': _add(state, 'hypoglycemia_severe')
            elif code == 'low': _add(state, 'hypoglycemia')
            elif code in {'impaired', 'igt'}: _add(state, 'glucose_impaired')
            elif code == 'diabetes_range':
                if value >= 16.7: _add(state, 'glucose_very_high')
                elif reading.metric == 'fasting_glucose' and value >= 11.1: _add(state, 'glucose_fasting_high')
                elif reading.metric != 'fasting_glucose' and value >= 13.9: _add(state, 'glucose_very_high')
                else: _add(state, 'glucose_above_cutoff')
        elif reading.metric == 'heart_rate':
            if value < 40 or value > 150:
                if matched(text, HR_SYMPTOMS): _add(state, 'hr_extreme_symptom')
                else: _add(state, 'hr_abnormal_rest')
            elif value < 50 or value > 110: _add(state, 'hr_abnormal_rest')
        elif reading.metric == 'spo2':
            if value < 90: _add(state, 'spo2_critical')
            elif value < 95: _add(state, 'spo2_low')
        elif reading.metric == 'temperature':
            if value >= 41: _add(state, 'temp_hyperpyrexia')
            elif value >= 39: _add(state, 'fever_high')
            elif value >= 38.1: _add(state, 'fever_moderate')
            elif value < 35: _add(state, 'hypothermia')

    if not is_concept:
        chest = matched(text, CHEST)
        if chest and not relieved(text):
            _add(state, 'chest_pain_15min')
        if matched(text, STROKE): _add(state, 'stroke_fast')
        if matched(text, DYSPNEA): _add(state, 'dyspnea_rest')
        if matched(text, CONSCIOUSNESS): _add(state, 'altered_consciousness')
        if matched(text, GI_BLEEDING): _add(state, 'gi_bleeding')
        if matched(text, SELF_HARM): _add(state, 'self_harm')
        if matched(text, FALL) and any(word in text for word in ('头', '意识', '叫不醒', '髋', '站不起来', '不能动')):
            _add(state, 'fall_head_injury')
    rules = [rule for rule in LABELS if rule in state['rules']]
    level = 'L1' if any(rule in L1_RULES for rule in rules) else \
        'L2' if any(rule in L2_RULES for rule in rules) else \
        'L3' if any(rule in L3_RULES for rule in rules) else 'L4'
    return Triage(level=level, rule_ids=rules, required_action=ACTIONS[level],
                  red_flags=[LABELS[rule] for rule in rules], table_version=TABLE_VERSION)


def observations(text: str) -> list[str]:
    """Non-authoritative symptom words, used only to phrase missing information."""
    found = []
    for words in (CHEST, STROKE, DYSPNEA, CONSCIOUSNESS, CRISIS_SYMPTOMS, HYPO_SYMPTOMS):
        for word in matched(text, words):
            if word not in found: found.append(word)
    return found
