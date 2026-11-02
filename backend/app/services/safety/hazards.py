"""Home hazard table and fall-risk factor extraction.

Actions are general safety guidance; dimensions are marked as common recommendations and
defer to an occupational therapist or renovation professional for the actual fitting.
"""
import re
from dataclasses import dataclass

from app.schemas.safety import HazardFinding, RiskFactor, SafetyProfile

TABLE_VERSION = 'safety-home-2026.1'


@dataclass(frozen=True)
class Hazard:
    id: str
    room: str
    issue: str
    patterns: tuple[str, ...]
    severity: str
    action: str
    reference: str = ''


HAZARDS: tuple[Hazard, ...] = (
    Hazard('bath_grab_bar', '卫生间', '马桶旁或淋浴区没有扶手',
           ('没扶手', '没有扶手', '装扶手', '扶手高度', '扶手多高', '马桶旁扶手', '淋浴扶手'),
           'moderate',
           '马桶旁装水平扶手、淋浴区装竖向扶手；常见建议高度为马桶旁约 70–80 cm，'
           '具体位置和高度请让适老化改造人员或康复治疗师现场确定。'),
    Hazard('bath_slippery', '卫生间', '地面湿滑',
           ('地滑', '滑倒', '湿滑', '防滑垫', '瓷砖滑'),
           'moderate', '铺防滑垫或做防滑处理，洗澡时使用洗澡椅，地面湿了及时擦干，穿防滑拖鞋。'),
    Hazard('bath_threshold', '卫生间', '门口有门槛或高差',
           ('门槛', '高差', '台阶'),
           'moderate', '尽量消除门槛或加装缓坡；无法改造时在门槛处贴醒目标识并放慢脚步。'),
    Hazard('bath_toilet_height', '卫生间', '坐便器偏低或使用蹲便',
           ('马桶矮', '蹲便', '蹲坑', '起不来', '坐下起不来'),
           'note', '可加装马桶增高器或坐便椅，常见坐便高度约 40–45 cm，以双脚能踏实着地为宜。'),
    Hazard('bath_shower_chair', '卫生间', '站着洗澡',
           ('站着洗澡', '站着洗', '洗澡累', '洗澡头晕'),
           'note', '使用洗澡椅或浴凳，避免长时间站立；洗澡水温不宜过高，时间不宜过长。'),
    Hazard('bath_door', '卫生间', '门反锁或向内开，影响救援',
           ('反锁', '门开不开', '门向内'),
           'note', '卫生间门建议改成向外开或易开启，不要反锁；安装可从外面打开的锁。'),
    Hazard('bedroom_night_light', '卧室', '起夜时照明不足',
           ('起夜', '夜里', '晚上上厕所', '半夜', '夜灯', '摸黑'),
           'moderate', '床边和通往卫生间的路上装感应夜灯，开关放在床边容易够到的位置。'),
    Hazard('bedroom_bed_height', '卧室', '床过高或过低',
           ('床太高', '床太矮', '床高', '下床'),
           'note', '床高以坐在床边双脚能平放地面为宜，常见建议 45–50 cm，必要时加床边扶手。'),
    Hazard('bedroom_clutter', '卧室', '通道有杂物、电线或小地毯',
           ('电线', '杂物', '地毯', '绊倒'),
           'moderate', '清理床边和通道的杂物，电线沿墙固定，去除或固定小地毯边缘。'),
    Hazard('living_rug', '客厅', '小地毯或地垫边缘翘起',
           ('客厅地毯', '地垫', '脚垫'),
           'moderate', '去除小地毯，或在下面加防滑垫并用双面胶固定四边。'),
    Hazard('living_furniture', '客厅', '家具过低或尖角',
           ('茶几矮', '家具尖', '桌角', '沙发太软', '起不来'),
           'note', '选用高度合适、有扶手的椅子；尖角加防撞条；沙发不宜过软，起身时先扶稳。'),
    Hazard('home_light', '全屋', '照明不足或开关不便',
           ('光线暗', '灯太暗', '照明不足', '开关'),
           'note', '增加照明，采用双控或感应开关，夜间保持走廊有微光。'),
    Hazard('living_light', '客厅', '客厅灯光偏暗',
           ('客厅灯', '客厅光线', '看电视看不清'),
           'note', '客厅保持足够亮度，沙发旁加落地灯，开关放在伸手可及处。'),
    Hazard('kitchen_high_shelf', '厨房', '常用物品放在高处',
           ('高处取物', '柜子高', '够不着', '踩凳子'),
           'moderate', '常用物品放在腰部到肩部高度，不要踩凳子或椅子取物；必须登高时用有扶手的稳固踏凳并有人看护。'),
    Hazard('kitchen_floor', '厨房', '地面油污或积水',
           ('厨房滑', '油', '积水'),
           'note', '做饭时及时清理地面油水，铺防滑垫，穿防滑鞋。'),
    Hazard('stairs_rail', '楼梯', '楼梯没有扶手或台阶不清',
           ('楼梯', '楼梯扶手', '台阶'),
           'moderate', '楼梯两侧安装连续扶手，台阶边缘贴防滑条或亮色标识，上下楼一次一级、扶稳再走。'),
    Hazard('stairs_light', '楼梯', '楼梯照明不足',
           ('楼梯暗', '楼道'),
           'moderate', '楼梯上下端安装双控开关和照明，夜间保持常亮或感应灯。'),
    Hazard('entry_threshold', '门口', '入户门槛或高差',
           ('入户', '门口', '玄关'),
           'moderate', '消除入户高差或加装缓坡，门口放稳固换鞋凳，坐着换鞋。'),
    Hazard('outdoor_slippery', '户外', '雨雪天路滑或户外台阶',
           ('下雨', '下雪', '路滑', '户外', '外面滑', '公园'),
           'moderate', '雨雪天尽量减少外出；外出穿防滑鞋、使用手杖，避开湿滑地面和台阶。'),
    Hazard('emergency_call', '全屋', '独居或缺少紧急呼叫手段',
           ('独居', '一个人住', '自己住', '没人照顾', '呼叫器', '紧急呼叫'),
           'high', '把手机或紧急呼叫器随身携带（包括洗澡时用防水袋），与家人或社区约定每天定时联系。'),
    Hazard('footwear', '全屋', '穿拖鞋或不合脚的鞋',
           ('拖鞋', '赤脚', '鞋不合脚'),
           'note', '选合脚、包跟、防滑的鞋，避免穿拖鞋或只穿袜子在地砖上走动。'),
)

ALIAS_ORDER = sorted(HAZARDS, key=lambda item: max(len(pattern) for pattern in item.patterns), reverse=True)
ROOM_WORDS = {'卫生间': '卫生间', '厕所': '卫生间', '浴室': '卫生间', '卧室': '卧室', '床': '卧室',
              '客厅': '客厅', '沙发': '客厅', '厨房': '厨房', '楼梯': '楼梯', '楼道': '楼梯',
              '门口': '门口', '玄关': '门口', '户外': '户外', '外面': '户外'}

DRUG_PATTERNS = {
    'sedative': ('安眠药', '地西泮', '阿普唑仑', '艾司唑仑', '唑匹坦', '唑吡坦', '佐匹克隆', '助眠'),
    'antihypertensive': ('降压药', '氨氯地平', '缬沙坦', '美托洛尔', '利尿剂'),
    'anticoagulant': ('华法林', '利伐沙班', '达比加群', '阿司匹林', '氯吡格雷', '抗凝', '抗血小板'),
    'glucose_lowering': ('降糖药', '胰岛素', '格列美脲', '格列齐特', '二甲双胍'),
    'anticholinergic': ('苯海索', '阿托品', '托特罗定', '索利那新', '扑尔敏'),
}

RISK_RULES = {
    'previous_falls': ('既往跌倒史', 'history', '跌倒是可预防的，但既往跌倒史是最重要的危险因素；建议做一次步态与平衡评估。'),
    'living_alone': ('独居或无人照看', 'living', '随身携带呼叫器或手机，与家人、邻居约定每日联系；洗澡时尤其要注意。'),
    'night_toilet': ('夜间起夜', 'body', '床边放便器或夜壶、装感应夜灯，起夜先坐片刻再站起。'),
    'vision_impairment': ('视力下降', 'body', '定期查视力，配戴合适眼镜，家中增加照明与对比色标识。'),
    'dizziness': ('头晕或体位性低血压', 'body', '起身遵循"躺 30 秒、坐 30 秒、站 30 秒"；反复头晕黑矇请就医。'),
    'gait_balance': ('步态不稳或需借助器具', 'body', '使用合适高度的手杖或助行器，做平衡与肌力训练，必要时康复评估。'),
    'cognition': ('认知功能下降', 'body', '家中设置醒目标识，收好危险物品，避免独自使用热水和外出。'),
    'osteoporosis': ('骨质疏松', 'body', '跌倒后骨折风险更高；补充钙和维生素 D 需医生评估，同时做好防跌倒。'),
    'parkinson_stroke': ('帕金森或卒中后遗症', 'body', '步态与平衡问题建议由康复科评估，家中通道保持宽敞。'),
    'sedative': ('使用镇静催眠药', 'medication', '镇静药会增加跌倒风险，夜间起床尤其危险；是否调整用药请咨询医生。'),
    'antihypertensive': ('使用降压药', 'medication', '注意体位性低血压，起身放慢；血压波动请复诊，不要自行停药。'),
    'anticoagulant': ('使用抗凝或抗血小板药', 'medication', '跌倒后出血风险更高，头部撞击需尽快就医评估。'),
    'glucose_lowering': ('使用降糖药', 'medication', '低血糖会引起头晕乏力，规律进餐并随身带糖；反复低血糖请复诊。'),
    'environment': ('居家环境隐患', 'environment', '按上面的清单逐项改造，优先处理通道、卫生间和照明。'),
}


def _has(text: str, words) -> bool:
    return any(word in text for word in words)


def profile_factors(profile: SafetyProfile) -> set[str]:
    factors: set[str] = set()
    if profile.previous_falls: factors.add('previous_falls')
    if profile.living_alone: factors.add('living_alone')
    if profile.vision == 'impaired': factors.add('vision_impairment')
    if profile.cognition == 'impaired': factors.add('cognition')
    if profile.mobility != 'independent': factors.add('gait_balance')
    if 'osteoporosis' in profile.conditions: factors.add('osteoporosis')
    if 'parkinson' in profile.conditions or 'stroke_history' in profile.conditions: factors.add('parkinson_stroke')
    if 'vertigo' in profile.conditions: factors.add('dizziness')
    drugs = ' '.join(profile.medications)
    if drugs:
        for key, words in DRUG_PATTERNS.items():
            if _has(drugs, words): factors.add(key)
    return factors


FALL_COUNT_WORDS = {'一次': 1, '1次': 1, '一次了': 1, '两次': 2, '2次': 2, '三次': 3, '3次': 3,
                    '好几次': 3, '多次': 3, '几次': 2}


def fall_count(text: str) -> int:
    for match in re.finditer(r'摔过|跌倒过|摔过跤', text):
        prefix = text[max(0, match.start() - 2):match.start()]
        if re.search(r'(?:没|未|无)$', prefix): return 0
    for word, count in FALL_COUNT_WORDS.items():
        if re.search(r'(?:摔|跌|滑倒)[^。；\n]{0,6}' + re.escape(word), text):
            return count
    if re.search(r'摔过|跌倒过|摔了几次', text): return 1
    return 0


def text_factors(text: str) -> set[str]:
    factors: set[str] = set()
    if re.search(r'摔过|跌倒过|摔了几次|去年摔|上次摔|以前摔', text): factors.add('previous_falls')
    if re.search(r'独居|一个人住|自己住|没人照顾|老伴不在', text): factors.add('living_alone')
    if re.search(r'起夜|夜里上厕所|半夜起来|晚上起来', text): factors.add('night_toilet')
    if re.search(r'看不清|视力下降|白内障|老花|眼睛不好', text): factors.add('vision_impairment')
    if re.search(r'头晕|眩晕|眼前发黑|站起来眼前黑|体位性', text): factors.add('dizziness')
    if re.search(r'走不稳|腿没劲|腿无力|平衡差|需要扶|拄拐|助行器|走不动', text): factors.add('gait_balance')
    if re.search(r'记不住|糊涂|痴呆|认知', text): factors.add('cognition')
    if '骨质疏松' in text: factors.add('osteoporosis')
    if re.search(r'帕金森|中风后|脑梗后|偏瘫', text): factors.add('parkinson_stroke')
    for key, words in DRUG_PATTERNS.items():
        if _has(text, words): factors.add(key)
    return factors


def detect_hazards(text: str) -> list[HazardFinding]:
    found: list[HazardFinding] = []
    for hazard in HAZARDS:
        if any(pattern in text for pattern in hazard.patterns):
            found.append(HazardFinding(id=hazard.id, room=hazard.room, issue=hazard.issue,
                                       severity=hazard.severity, action=hazard.action,
                                       reference=hazard.reference))
    return found


def assess(text: str, profile: SafetyProfile) -> tuple[list[HazardFinding], list[RiskFactor], str]:
    hazards = detect_hazards(text)
    factors = profile_factors(profile) | text_factors(text)
    if len(hazards) >= 2: factors.add('environment')
    if hazards and 'environment' not in factors and len(hazards) == 1: factors.add('environment')
    falls = max(profile.previous_falls or 0, fall_count(text))
    if falls: factors.add('previous_falls')
    previous = 'previous_falls' in factors
    alone = 'living_alone' in factors
    anticoagulant = 'anticoagulant' in factors
    limited = 'gait_balance' in factors
    strong_single = {'gait_balance', 'dizziness', 'cognition', 'anticoagulant', 'sedative'}
    if falls >= 2 or (previous and (alone or anticoagulant or limited)):
        level = 'high'
    elif previous or len(factors) >= 2 or (factors & strong_single) or len(hazards) >= 2:
        level = 'medium'
    else:
        level = 'low'
    order = ['previous_falls', 'living_alone', 'sedative', 'anticoagulant', 'dizziness', 'gait_balance',
             'night_toilet', 'vision_impairment', 'cognition', 'osteoporosis', 'parkinson_stroke',
             'antihypertensive', 'glucose_lowering', 'environment']
    risk_factors = [RiskFactor(id=key, label=RISK_RULES[key][0], kind=RISK_RULES[key][1], action=RISK_RULES[key][2])
                    for key in order if key in factors]
    return hazards, risk_factors, level
