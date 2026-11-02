"""Deterministic vitals parsing, unit normalisation and classification.

The parser is the only source of numeric facts. Model-extracted numbers are never
classified: a wrong category is a safety failure, so a table plus tests own it.
"""
import re
import unicodedata
from dataclasses import dataclass

from app.schemas.health import (
    CategoryCode, Condition, HealthProfile, MeasurementState, Metric, MissingField,
    VitalsAssessment, VitalsInput, VitalsReading,
)

TABLE_VERSION = 'cn-bp-2024/cds-2024/hs-2023'
DISPLAY_VERSION = '表 ' + TABLE_VERSION

CONTEXT_LABEL = {'home': '家庭自测', 'clinic': '诊室测量', 'unknown': '测量情境未说明'}
CONDITION_LABEL = {'fasting': '空腹', 'postprandial_2h': '餐后2小时', 'random': '随机',
                   'resting': '静息', 'after_exercise': '运动后', 'unknown': '状态未说明'}

# Measurable ranges. Values outside are treated as recording errors, never classified.
LIMITS = {
    'blood_pressure': (60, 260, 30, 160),
    'glucose': (2.0, 35.0),
    'heart_rate': (30, 220),
    'spo2': (60, 100),
    'temperature': (33.0, 42.5),
    'weight': (25.0, 200.0),
}

GLUCOSE_METRIC = {'fasting': 'fasting_glucose', 'postprandial_2h': 'postprandial_glucose',
                  'random': 'random_glucose', 'unknown': 'random_glucose',
                  'resting': 'random_glucose', 'after_exercise': 'random_glucose'}


@dataclass
class RawReading:
    metric: Metric
    unit: str
    raw: str
    systolic: int | None = None
    diastolic: int | None = None
    value: float | None = None
    context: Condition = 'unknown'
    condition: MeasurementState = 'unknown'
    converted: bool = False
    source: str = 'parsed'


def clean(text: str) -> str:
    return unicodedata.normalize('NFKC', text or '')


def _window(text: str, start: int, end: int, size: int = 46) -> str:
    return text[max(0, start - size):min(len(text), end + size)]


def _context(window: str, current: Condition = 'unknown') -> Condition:
    if re.search(r'家里|在家|自测|家庭|自己量|家用', window): return 'home'
    if re.search(r'医院|诊室|门诊|体检|社区测', window): return 'clinic'
    return current


def _condition(window: str) -> MeasurementState:
    if re.search(r'空腹|晨起|没吃东西|未进食', window): return 'fasting'
    if re.search(r'餐后|饭后|早餐后|午餐后|晚餐后', window): return 'postprandial_2h'
    if re.search(r'随机|任意时间', window): return 'random'
    if re.search(r'静息|安静|休息时', window): return 'resting'
    if re.search(r'运动后|爬楼后|刚运动|锻炼后', window): return 'after_exercise'
    return 'unknown'


def _number(text: str) -> float:
    return float(text)


def parse_blood_pressure(text: str) -> list[RawReading]:
    readings: list[RawReading] = []
    consumed: list[tuple[int, int]] = []
    for match in re.finditer(r'(\d{2,3})\s*(?:/|／)\s*(\d{2,3})', text):
        systolic, diastolic = int(match[1]), int(match[2])
        window = _window(text, match.start(), match.end())
        readings.append(RawReading(metric='blood_pressure', unit='mmHg', raw=match.group(0),
                                   systolic=systolic, diastolic=diastolic,
                                   context=_context(window), condition=_condition(window)))
        consumed.append((match.start(), match.end()))
    for systolic, diastolic in re.findall(r'(?:高压|收缩压)[^\d]{0,6}(\d{2,3})[^\d]{0,10}(?:低压|舒张压)[^\d]{0,6}(\d{2,3})', text):
        window = _window(text, 0, len(text))
        readings.append(RawReading(metric='blood_pressure', unit='mmHg', raw=f'{systolic}/{diastolic}',
                                   systolic=int(systolic), diastolic=int(diastolic), context=_context(window)))
    single = re.search(r'(?:血压|高压)[^\d，。；\n]{0,10}(\d{2,3})(?!\s*(?:/|／)\s*\d)', text)
    if single and not any(start <= single.start(1) <= end for start, end in consumed):
        window = _window(text, single.start(), single.end())
        readings.append(RawReading(metric='blood_pressure', unit='mmHg', raw=single.group(0),
                                   systolic=int(single[1]), context=_context(window), condition=_condition(window)))
    return readings


def _glucose_value(number: str, unit: str | None) -> tuple[float, str, bool]:
    value = _number(number)
    normalized = (unit or '').replace(' ', '').lower()
    if normalized in {'mg/dl', 'mgdl'}:
        return round(value / 18, 2), 'mmol/L', True
    return value, 'mmol/L', False


def parse_glucose(text: str) -> list[RawReading]:
    readings: list[RawReading] = []
    pattern = (r'(?:空腹|餐后|饭后|随机)?[^，。；\n]{0,8}?(?:血糖|葡萄糖)'
               r'[^0-9，。；\n]{0,10}(\d{1,3}(?:\.\d)?)\s*(mmol/L|mmol|毫摩尔/升|mg/dL|mg/dl)?')
    for match in re.finditer(pattern, text, re.I):
        window = _window(text, match.start(), match.end(), 30)
        value, unit, converted = _glucose_value(match[1], match[2])
        condition = _condition(window)
        readings.append(RawReading(metric=GLUCOSE_METRIC[condition], unit=unit, raw=match.group(0),
                                   value=value, context=_context(window), condition=condition,
                                   converted=converted))
    if not readings:
        for match in re.finditer(r'(\d{1,3}(?:\.\d)?)\s*(mmol/L|mg/dL)', text, re.I):
            window = _window(text, match.start(), match.end(), 30)
            if not re.search(r'血糖|葡萄糖', window): continue
            value, unit, converted = _glucose_value(match[1], match[2])
            condition = _condition(window)
            readings.append(RawReading(metric=GLUCOSE_METRIC[condition], unit=unit, raw=match.group(0),
                                       value=value, context=_context(window), condition=condition,
                                       converted=converted))
    return readings


def parse_heart_rate(text: str) -> list[RawReading]:
    readings = []
    for match in re.finditer(r'(?:心率|脉搏|心跳)[^0-9，。；\n]{0,8}(\d{2,3})', text):
        window = _window(text, match.start(), match.end())
        readings.append(RawReading(metric='heart_rate', unit='次/分', raw=match.group(0),
                                   value=float(match[1]), condition=_condition(window)))
    for match in re.finditer(r'(\d{2,3})\s*(?:次/分|次／分|bpm)', text):
        if any(item.raw == match.group(0) for item in readings): continue
        window = _window(text, match.start(), match.end())
        readings.append(RawReading(metric='heart_rate', unit='次/分', raw=match.group(0),
                                   value=float(match[1]), condition=_condition(window)))
    return readings


def parse_spo2(text: str) -> list[RawReading]:
    readings = []
    for match in re.finditer(r'(?:血氧|血氧饱和度|氧饱和度|指脉氧)[^0-9，。；\n]{0,8}(\d{2,3})', text):
        readings.append(RawReading(metric='spo2', unit='%', raw=match.group(0), value=float(match[1])))
    for match in re.finditer(r'(\d{2,3})\s*%', text):
        window = _window(text, match.start(), match.end())
        if not re.search(r'血氧|氧饱和', window): continue
        if any(item.raw == match.group(0) for item in readings): continue
        readings.append(RawReading(metric='spo2', unit='%', raw=match.group(0), value=float(match[1])))
    return readings


def parse_temperature(text: str) -> list[RawReading]:
    readings = []
    for match in re.finditer(r'(?:体温)[^0-9，。；\n]{0,8}(\d{2}(?:\.\d)?)\s*(℃|度|摄氏度)?', text):
        readings.append(RawReading(metric='temperature', unit='℃', raw=match.group(0), value=float(match[1])))
    for match in re.finditer(r'(\d{2}(?:\.\d)?)\s*(℃|摄氏度)', text):
        if any(item.raw == match.group(0) for item in readings): continue
        window = _window(text, match.start(), match.end())
        if not re.search(r'体温|发烧|发热|烧到', window): continue
        readings.append(RawReading(metric='temperature', unit='℃', raw=match.group(0), value=float(match[1])))
    return readings


def parse_weight(text: str) -> list[RawReading]:
    readings = []
    for match in re.finditer(r'(?:体重)[^0-9，。；\n]{0,8}(\d{2,3}(?:\.\d)?)\s*(kg|公斤|千克|斤)?', text):
        value = float(match[1])
        unit = 'kg'
        converted = False
        if match[2] == '斤':
            value, converted = round(value / 2, 1), True
        readings.append(RawReading(metric='weight', unit=unit, raw=match.group(0), value=value, converted=converted))
    return readings


def parse_text(text: str) -> list[RawReading]:
    text = clean(text)
    readings = [*parse_blood_pressure(text), *parse_glucose(text), *parse_heart_rate(text),
                *parse_spo2(text), *parse_temperature(text), *parse_weight(text)]
    return readings


def from_input(item: VitalsInput) -> RawReading:
    if item.metric == 'blood_pressure':
        return RawReading(metric='blood_pressure', unit='mmHg', raw=f'{item.systolic}/{item.diastolic}',
                          systolic=item.systolic, diastolic=item.diastolic,
                          context=item.context, condition=item.condition, source='provided')
    value = float(item.value or 0)
    converted = False
    unit = item.unit
    if item.metric in {'fasting_glucose', 'postprandial_glucose', 'random_glucose'} and unit == 'mg/dL':
        value, unit, converted = round(value / 18, 2), 'mmol/L', True
    return RawReading(metric=item.metric, unit=unit, raw=str(item.value), value=value,
                      context=item.context, condition=item.condition,
                      converted=converted, source='provided')


def _plausible(raw: RawReading) -> bool:
    if raw.metric == 'blood_pressure':
        if raw.systolic is None: return True
        low_sys, high_sys, low_dia, high_dia = LIMITS['blood_pressure']
        systolic, diastolic = raw.systolic, raw.diastolic
        if not low_sys <= systolic <= high_sys: return False
        if diastolic is not None and not low_dia <= diastolic <= high_dia: return False
        if diastolic is not None and diastolic >= systolic: return False
        return True
    if raw.value is None: return True
    limits = LIMITS['glucose'] if raw.metric.endswith('glucose') else LIMITS[raw.metric]
    return limits[0] <= raw.value <= limits[1]


def classify_bp(systolic: int, diastolic: int | None, context: Condition) -> tuple[str, CategoryCode, str]:
    if diastolic is None:
        if systolic >= 180: return '收缩压重度升高', 'stage3', '收缩压 ≥180 mmHg 属重度升高，需尽快就医评估'
        if systolic >= 160: return '收缩压升高', 'stage2', '收缩压 ≥160 mmHg 属明显升高，需就医评估'
        if systolic >= 140: return '收缩压升高', 'stage1', '收缩压 ≥140 mmHg 属升高，需复测并就医评估'
        if systolic >= 120: return '收缩压偏高', 'elevated', '收缩压 120–139 mmHg 为正常高值'
        return '收缩压偏低或正常', 'normal' if systolic >= 90 else 'low', '收缩压 <90 mmHg 偏低'
    if context == 'home':
        if systolic >= 180 and diastolic >= 120: return '血压危象范围', 'crisis', '家庭自测血压 ≥180/120 mmHg 属危象范围，需立即就医'
        if systolic >= 180 or diastolic >= 110: return '3级高血压范围', 'stage3', '家庭自测血压 ≥180/110 mmHg 相当于诊室 3 级'
        if systolic >= 160 or diastolic >= 100: return '2级高血压范围', 'stage2', '家庭自测血压 160–179/100–109 mmHg 相当于诊室 2 级'
        if systolic >= 135 or diastolic >= 85: return '血压偏高', 'stage1', '家庭自测血压 ≥135/85 mmHg 视为偏高（家庭标准低于诊室）'
        if systolic < 90 or diastolic < 60: return '血压偏低', 'low', '家庭自测收缩压 <90 或舒张压 <60 mmHg 属偏低'
        return '家庭自测血压正常', 'normal', '家庭自测血压 <135/85 mmHg 为正常'
    if systolic >= 180 and diastolic >= 120: return '血压危象范围', 'crisis', '血压 ≥180/120 mmHg 属危象范围，需立即就医'
    if systolic >= 180 or diastolic >= 110: return '3级高血压', 'stage3', '诊室血压 ≥180/110 mmHg 为 3 级（重度）'
    if systolic >= 160 or diastolic >= 100: return '2级高血压', 'stage2', '诊室血压 160–179/100–109 mmHg 为 2 级（中度）'
    if systolic >= 140 or diastolic >= 90: return '1级高血压', 'stage1', '诊室血压 140–159/90–99 mmHg 为 1 级（轻度）'
    if systolic < 90 or diastolic < 60: return '血压偏低', 'low', '收缩压 <90 或舒张压 <60 mmHg 属偏低'
    if systolic >= 120 or diastolic >= 80: return '正常高值', 'elevated', '诊室血压 120–139/80–89 mmHg 为正常高值'
    return '血压正常', 'normal', '诊室血压 <120/80 mmHg 为正常'


def classify_glucose(value: float, condition: MeasurementState) -> tuple[str, CategoryCode, str]:
    if value < 3.0: return '严重低血糖范围', 'severe_low', '血糖 <3.0 mmol/L 属严重低血糖范围，需立即处理'
    if value < 3.9: return '低血糖范围', 'low', '血糖 <3.9 mmol/L 属低血糖范围'
    if condition == 'fasting':
        if value <= 6.0: return '空腹血糖正常', 'normal', '空腹血糖 3.9–6.0 mmol/L 为正常'
        if value <= 6.9: return '空腹血糖受损', 'impaired', '空腹血糖 6.1–6.9 mmol/L 为空腹血糖受损'
        return '达到糖尿病诊断切点', 'diabetes_range', '空腹血糖 ≥7.0 mmol/L 达到糖尿病诊断切点，需医院复核'
    if condition == 'postprandial_2h':
        if value < 7.8: return '餐后血糖正常', 'normal', '餐后 2 小时血糖 <7.8 mmol/L 为正常'
        if value <= 11.0: return '糖耐量减低', 'igt', '餐后 2 小时血糖 7.8–11.0 mmol/L 为糖耐量减低'
        return '达到糖尿病诊断切点', 'diabetes_range', '餐后 2 小时血糖 ≥11.1 mmol/L 达到糖尿病诊断切点，需医院复核'
    if value < 11.1: return '随机血糖未达切点', 'normal', '随机血糖 <11.1 mmol/L 未达糖尿病诊断切点（需结合空腹及餐后）'
    if value <= 13.8: return '随机血糖明显升高', 'diabetes_range', '随机血糖 ≥11.1 mmol/L 达到糖尿病诊断切点，需医院复核'
    return '随机血糖显著升高', 'diabetes_range', '随机血糖 ≥13.9 mmol/L 显著升高，需尽快就医评估'


def classify_heart_rate(value: float) -> tuple[str, CategoryCode, str]:
    if value < 40: return '心率明显偏慢', 'severe_low', '静息心率 <40 次/分属明显偏慢'
    if value < 50: return '心率偏慢', 'low', '静息心率 <50 次/分属偏慢'
    if value <= 100: return '心率正常范围', 'normal', '静息心率 60–100 次/分为正常范围（50–59 次/分偏慢但可属正常变异）'
    if value <= 150: return '心率偏快', 'high', '静息心率 >100 次/分属偏快'
    return '心率显著偏快', 'severe_high', '静息心率 >150 次/分属显著偏快'


def classify_spo2(value: float) -> tuple[str, CategoryCode, str]:
    if value < 90: return '血氧明显偏低', 'low', '血氧饱和度 <90% 属明显偏低，需立即就医'
    if value < 95: return '血氧偏低', 'low', '血氧饱和度 90–94% 属偏低'
    return '血氧正常', 'normal', '血氧饱和度 ≥95% 为正常范围'


def classify_temperature(value: float) -> tuple[str, CategoryCode, str]:
    if value < 35: return '体温偏低', 'hypothermia', '体温 <35℃ 属体温过低'
    if value < 37.3: return '体温正常', 'normal', '体温 <37.3℃ 为正常'
    if value <= 38.0: return '低热', 'low_fever', '体温 37.3–38.0℃ 为低热'
    if value <= 39.0: return '中度发热', 'moderate_fever', '体温 38.1–39.0℃ 为中度发热'
    if value <= 40.9: return '高热', 'high_fever', '体温 39.1–40.9℃ 为高热'
    return '超高热', 'hyperpyrexia', '体温 ≥41℃ 属超高热，需立即就医'


def classify_weight(value: float) -> tuple[str, CategoryCode, str]:
    return '体重记录', 'recorded', '单次体重不构成分级，需结合身高与短期变化趋势判断'


def display(raw: RawReading) -> str:
    if raw.metric == 'blood_pressure':
        text = f'{raw.systolic}/' + (f'{raw.diastolic}' if raw.diastolic is not None else '—') + ' mmHg'
        return text + f'（{CONTEXT_LABEL[raw.context]}）'
    if raw.metric in {'fasting_glucose', 'postprandial_glucose', 'random_glucose'}:
        suffix = f'（{CONDITION_LABEL[raw.condition]}' + ('，已换算' if raw.converted else '') + '）'
        return f'{raw.value:g} mmol/L{suffix}'
    if raw.metric == 'heart_rate': return f'{raw.value:g} 次/分'
    if raw.metric == 'spo2': return f'{raw.value:g}%'
    if raw.metric == 'temperature': return f'{raw.value:g} ℃'
    if raw.metric == 'weight': return f'{raw.value:g} kg' + ('（已换算）' if raw.converted else '')
    return str(raw.value)


def assess_reading(raw: RawReading, *, implausible: bool = False) -> VitalsReading:
    if raw.metric == 'blood_pressure':
        category, code, basis = classify_bp(raw.systolic or 0, raw.diastolic, raw.context)
    elif raw.metric in {'fasting_glucose', 'postprandial_glucose', 'random_glucose'}:
        category, code, basis = classify_glucose(float(raw.value or 0), raw.condition)
    elif raw.metric == 'heart_rate':
        category, code, basis = classify_heart_rate(float(raw.value or 0))
    elif raw.metric == 'spo2':
        category, code, basis = classify_spo2(float(raw.value or 0))
    elif raw.metric == 'temperature':
        category, code, basis = classify_temperature(float(raw.value or 0))
    else:
        category, code, basis = classify_weight(float(raw.value or 0))
    flags: list[str] = []
    if not implausible and not _plausible(raw):
        implausible = True
    if implausible:
        category, code, basis = '数值待核实', 'unverified', '数值超出可测量范围，可能记录有误，未参与判读'
        flags.append('implausible')
    if raw.converted: flags.append('unit_converted')
    return VitalsReading(metric=raw.metric, systolic=raw.systolic, diastolic=raw.diastolic, value=raw.value,
                         unit=raw.unit, display=display(raw), context=raw.context, condition=raw.condition,
                         category=category, category_code=code, reference_basis=basis,
                         table_version=TABLE_VERSION, flags=flags, source='provided' if raw.source == 'provided' else 'parsed')


def context_matters(systolic: int | None, diastolic: int | None) -> bool:
    """Ask for home/clinic only where the two standards actually change the reading."""
    if systolic is None or diastolic is None: return False
    if systolic >= 140 or diastolic >= 90: return False
    return systolic >= 130 or diastolic >= 85


def _dedupe(readings: list[RawReading]) -> list[RawReading]:
    seen: set[tuple] = set()
    result = []
    for reading in readings:
        key = (reading.metric, reading.systolic, reading.diastolic, reading.value)
        if key in seen: continue
        seen.add(key)
        result.append(reading)
    return result


def assess(question: str, history_texts: list[str], provided: list[VitalsInput],
           profile: HealthProfile, reported_value: str | None = None) -> VitalsAssessment:
    raw: list[RawReading] = []
    if provided:
        raw = [from_input(item) for item in provided]
    else:
        raw = parse_text(question)
        if not raw:
            for text in reversed(history_texts[-3:]):
                raw = parse_text(text)
                if raw: break
    raw = _dedupe(raw)
    readings = [assess_reading(item) for item in raw]
    missing: list[str] = []
    implausible = any('implausible' in reading.flags for reading in readings)
    if implausible: missing.append('explicit_value')
    for reading in readings:
        if reading.metric == 'blood_pressure':
            if reading.diastolic is None and 'diastolic_value' not in missing: missing.append('diastolic_value')
            if reading.context == 'unknown' and context_matters(reading.systolic, reading.diastolic):
                if 'measurement_context' not in missing: missing.append('measurement_context')
        if reading.metric in {'fasting_glucose', 'postprandial_glucose', 'random_glucose'} and reading.condition == 'unknown':
            if 'fasting_status' not in missing: missing.append('fasting_status')
    unverified = False
    if not readings and reported_value:
        unverified = True
        missing.append('explicit_value')
    primary = next((item for item in readings if item.metric == 'blood_pressure'), readings[0] if readings else None)
    return VitalsAssessment(readings=readings, primary=primary, missing=missing, implausible=implausible,
                            unverified_from_model=unverified, table_version=TABLE_VERSION)


def clarification(assessment: VitalsAssessment) -> str | None:
    """Ask only for the decisive gap, at most two items."""
    if 'explicit_value' in assessment.missing and not assessment.readings:
        return '请补充具体测量数值和单位，例如“血压 150/95 mmHg”或“空腹血糖 7.2 mmol/L”，并说明是在家测还是在医院测的。'
    questions: list[str] = []
    if 'explicit_value' in assessment.missing:
        questions.append('这个数值明显超出常见测量范围，可能记录有误，请再确认一次测量值和单位')
    if 'diastolic_value' in assessment.missing:
        questions.append('低压（舒张压）是多少')
    if 'measurement_context' in assessment.missing and 'blood_pressure' in {item.metric for item in assessment.readings}:
        questions.append('这是在家里量的还是医院量的')
    if 'fasting_status' in assessment.missing:
        questions.append('这次血糖是空腹还是餐后测的')
    if not questions: return None
    return '请补充：' + '；'.join(questions[:2]) + '。'
