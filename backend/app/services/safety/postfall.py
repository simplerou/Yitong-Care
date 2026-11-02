"""Post-fall assessment rules and the fixed first-aid copy.

The single most important rule: do not rush to lift the person up. The model never
decides whether a fall is an emergency; these rules do.
"""
import re

from app.schemas.safety import PostFallFinding, SafetyProfile
from app.services.safety.hazards import TABLE_VERSION

FALL_WORDS = ('摔倒', '摔了', '摔一跤', '摔了一跤', '摔了一交', '滑倒', '滑了一下', '跌了', '跌倒后',
              '跌伤', '摔伤', '从床上掉', '从椅子', '晕倒', '躺在地上', '在地上躺')

POST_FALL_ADVICE = ('先不要急着把人扶起来。先看他是否清醒、能不能说话、哪里疼、有没有出血；'
                    '如果怀疑髋部、腰背或颈部受伤，或者他意识不清，不要搬动，立即拨打 120。'
                    '意识不清时不要喂水、喂药、喂饭；注意保暖，等他保持舒适体位，直到救护人员到达。'
                    '如果意识清醒、没有明显外伤，再按"先侧身、再跪起、扶稳慢起"的顺序协助起身，'
                    '起身后坐下休息并观察 30 分钟。')

NEGATION = re.compile(r'(?:没有|没|无|未|不|否认)[^。；\n]{0,4}$')


def _present(text: str, words) -> list[str]:
    found = []
    for word in words:
        for match in re.finditer(re.escape(word), text):
            if NEGATION.search(text[max(0, match.start() - 8):match.start()]): continue
            found.append(word); break
    return found


PREVENTION_CONTEXT = re.compile(r'(?:容易|会|怕|担心|防止|避免|预防|小心|防|易)[^。；\n]{0,4}$')
EVENT_PATTERN = re.compile(r'摔倒|摔了|摔过|摔一跤|摔了一跤|摔了一交|摔伤|滑倒|滑了一下|跌了|跌倒后|跌伤|'
                           r'从床上掉|从椅子|晕倒|躺在地上|在地上躺')


def is_fall_event(text: str) -> bool:
    # "怎么防跌倒""容易滑倒" are prevention/risk statements, not reports of a fall.
    for match in EVENT_PATTERN.finditer(text):
        prefix = text[max(0, match.start() - 6):match.start()]
        if PREVENTION_CONTEXT.search(prefix): continue
        return True
    return bool(re.search(r'跌倒(?:了)?(?:怎么办|怎么处理|如何办|咋办)', text))


def assess_post_fall(text: str, profile: SafetyProfile) -> list[PostFallFinding]:
    if not is_fall_event(text):
        return []
    findings: list[PostFallFinding] = []
    unconscious = _present(text, ('叫不醒', '意识模糊', '意识不清', '昏迷', '说胡话', '抽搐'))
    if unconscious:
        findings.append(PostFallFinding(
            id='altered_consciousness', severity='high', title='跌倒后意识改变',
            detail='跌倒后意识不清、抽搐或难以唤醒，可能存在颅内损伤或其他急症。',
            action='立即拨打 120；不要搬动、不要喂水喂药，保持侧卧防止误吸。'))
    if _present(text, ('呼吸困难', '喘不上气', '脸色发紫', '憋气')):
        findings.append(PostFallFinding(
            id='breathing_difficulty', severity='high', title='跌倒后呼吸困难',
            detail='呼吸困难可能提示胸部损伤、气道问题或原有心肺疾病加重。',
            action='立即拨打 120；让患者保持半坐位，不要强行平躺。'))
    head = _present(text, ('头', '撞到头', '头部', '磕到头'))
    if head and _present(text, ('呕吐', '吐了', '嗜睡', '想睡', '头痛加重', '叫不醒')):
        findings.append(PostFallFinding(
            id='head_injury', severity='high', title='头部撞击后出现警示症状',
            detail='头部外伤后呕吐、嗜睡或头痛加重，需警惕颅内出血。',
            action='立即拨打 120，不要自行观察等待；不要服用止痛药掩盖症状。'))
    drug_text = ' '.join(profile.medications) + ' ' + text
    anticoagulant = any(word in drug_text for word in ('华法林', '利伐沙班', '达比加群', '阿司匹林', '氯吡格雷', '抗凝'))
    if head and anticoagulant:
        findings.append(PostFallFinding(
            id='anticoagulant_head_strike', severity='high', title='抗凝或抗血小板药使用者头部撞击',
            detail='正在使用抗凝或抗血小板药时，头部撞击后颅内出血风险明显升高。',
            action='尽快就医评估，即使当下没有明显症状；不要自行停药。'))
    if _present(text, ('髋', '胯', '大腿根')) and _present(text, ('站不起来', '不能站', '动不了', '疼得厉害')):
        findings.append(PostFallFinding(
            id='hip_fracture', severity='high', title='疑似髋部骨折',
            detail='跌倒后髋部疼痛、无法站立或负重，需要按髋部骨折处理。',
            action='不要扶起、不要试着走路，立即拨打 120；保持双腿自然位置，避免搬动。'))
    if _present(text, ('腰', '后背', '脊柱', '脖子', '颈')) and _present(text, ('麻', '不能动', '动不了', '疼得厉害')):
        findings.append(PostFallFinding(
            id='spine_injury', severity='high', title='腰背或颈部受伤可能',
            detail='腰背或颈部疼痛伴下肢麻木、活动受限，需警惕脊柱损伤。',
            action='不要搬动或扶起，保持原体位，立即拨打 120。'))
    if _present(text, ('大量出血', '流血不止', '出血很多')):
        findings.append(PostFallFinding(
            id='heavy_bleeding', severity='high', title='大量出血',
            detail='跌倒后大量出血可能导致休克。',
            action='立即拨打 120；用干净布料直接压迫伤口，不要反复揭开查看。'))
    if _present(text, ('肿', '畸形', '不能负重', '一踩就疼', '手腕', '胳膊')):
        findings.append(PostFallFinding(
            id='suspected_fracture', severity='moderate', title='疑似骨折',
            detail='局部肿胀、疼痛或形态异常，需要影像检查确认。',
            action='固定患肢、不要强行活动，尽快就医拍片；不要自行复位或揉搓。'))
    if _present(text, ('独居', '一个人住', '自己住', '没人')) and _present(text, ('起不来', '爬不起来', '站不起来')):
        findings.append(PostFallFinding(
            id='alone_cannot_rise', severity='moderate', title='独居且无法自行起身',
            detail='独居老人跌倒后长时间无法起身，可能出现脱水、低体温和肌肉损伤。',
            action='立即用手机或呼叫器联系家人、邻居或 120；不要勉强站立，先移到有遮挡处保暖。'))
    if _present(text, ('躺了', '在地上', '起不来')) and re.search(r'(?:半|一|两|几|3|四|五)\s*个?小时|半天', text):
        findings.append(PostFallFinding(
            id='long_lie', severity='moderate', title='倒地时间较长',
            detail='长时间倒地可能引起脱水、低体温和肌肉损伤。',
            action='尽快就医评估，即使感觉还能活动；不要一次大量进食饮水。'))
    if _present(text, ('头晕', '眼前黑', '晕倒', '眩晕')) and _present(text, FALL_WORDS):
        findings.append(PostFallFinding(
            id='syncope_fall', severity='moderate', title='头晕或晕厥导致的跌倒',
            detail='因头晕、眼前发黑或晕厥而跌倒，可能与心律、血压或血糖问题有关。',
            action='尽快就医查明原因，不要只当作"没站稳"；就医前避免独自洗澡和外出。'))
    if _present(text, ('又摔', '反复摔', '第二次摔', '经常摔', '好几次')):
        findings.append(PostFallFinding(
            id='recurrent_falls', severity='moderate', title='反复跌倒',
            detail='反复跌倒是需要系统评估的信号，涉及步态、用药、视力和居家环境。',
            action='建议到老年科或康复科做跌倒风险评估，并同步改造居家环境。'))
    if not findings:
        findings.append(PostFallFinding(
            id='minor_fall', severity='note', title='跌倒后暂无警示症状',
            detail='目前描述中没有意识改变、明显外伤或无法站立的迹象，但仍需观察。',
            action='坐下休息并观察 30 分钟；如出现头痛加重、嗜睡、呕吐、髋部疼痛或走路困难，及时就医。'))
    order = {'high': 0, 'moderate': 1, 'note': 2}
    findings.sort(key=lambda item: (order[item.severity], item.id))
    return findings


def level_of(findings: list[PostFallFinding]) -> str:
    if any(item.severity == 'high' for item in findings): return 'L1'
    if any(item.severity == 'moderate' for item in findings): return 'L2'
    if findings: return 'L3'
    return 'L4'


def table_version() -> str:
    return TABLE_VERSION
