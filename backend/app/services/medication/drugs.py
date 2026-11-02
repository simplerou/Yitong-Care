"""Curated medication dictionary, interaction rules, timing hints and missed-dose logic.

Everything here is conservative reference material for education: it never decides a
dose, and every finding defers the final decision to a doctor or pharmacist.
"""
import re
import unicodedata
from dataclasses import dataclass

from app.schemas.medication import (
    DrugMention, InteractionFinding, MedicationAssessment, MedicationItem, MedicationProfile,
    MedicationTriage,
)

TABLE_VERSION = 'medication-rules-2026.1'
DISPLAY_VERSION = '规则集 ' + TABLE_VERSION

# group -> (类别说明, 常见用途)
CLASS_INFO = {
    'ccb': ('钙通道阻滞剂（降压药）', '常用于高血压、心绞痛'),
    'acei': ('血管紧张素转换酶抑制剂（降压药）', '常用于高血压、心力衰竭'),
    'arb': ('血管紧张素受体阻滞剂（降压药）', '常用于高血压、心力衰竭'),
    'beta_blocker': ('β 受体阻滞剂', '常用于高血压、冠心病、心律失常'),
    'thiazide': ('噻嗪类利尿剂（降压药）', '常用于高血压'),
    'loop_diuretic': ('袢利尿剂', '常用于水肿、心力衰竭'),
    'potassium_sparing': ('保钾利尿剂', '常与排钾利尿剂合用'),
    'potassium': ('补钾制剂', '用于低钾血症'),
    'nitrate': ('硝酸酯类', '用于心绞痛'),
    'digoxin': ('强心苷', '用于心力衰竭、房颤心室率控制'),
    'amiodarone': ('抗心律失常药', '用于心律失常'),
    'statin': ('他汀类调脂药', '用于高脂血症、动脉粥样硬化防治'),
    'antiplatelet': ('抗血小板药', '用于血栓预防'),
    'anticoagulant': ('抗凝药', '用于血栓栓塞预防与治疗'),
    'biguanide': ('双胍类降糖药', '常用于 2 型糖尿病'),
    'sulfonylurea': ('磺脲类降糖药', '常用于 2 型糖尿病'),
    'insulin': ('胰岛素', '用于糖尿病降糖治疗'),
    'alpha_glucosidase': ('α-糖苷酶抑制剂', '用于降低餐后血糖'),
    'dpp4': ('DPP-4 抑制剂', '用于 2 型糖尿病'),
    'sglt2': ('SGLT-2 抑制剂', '用于 2 型糖尿病、心衰'),
    'ppi': ('质子泵抑制剂（抑酸药）', '用于胃食管反流、溃疡'),
    'benzodiazepine': ('苯二氮䓬类镇静催眠药', '用于焦虑、失眠'),
    'z_drug': ('非苯二氮䓬类助眠药', '用于失眠'),
    'anticholinergic': ('抗胆碱能药', '用于过敏、晕动、膀胱过度活动或帕金森症状'),
    'opioid': ('阿片类镇痛药', '用于中重度疼痛'),
    'ssri': ('SSRI 类抗抑郁药', '用于抑郁、焦虑'),
    'levothyroxine': ('甲状腺激素', '用于甲状腺功能减退'),
    'bisphosphonate': ('双膦酸盐', '用于骨质疏松'),
    'calcium': ('钙剂', '用于补钙、骨质疏松辅助'),
    'iron': ('铁剂', '用于缺铁性贫血'),
    'nsaid': ('非甾体抗炎药（解热镇痛）', '用于疼痛、发热、炎症'),
    'acetaminophen': ('解热镇痛药（对乙酰氨基酚）', '用于发热、轻中度疼痛'),
    'cold_medicine': ('复方感冒药', '用于感冒症状，常含对乙酰氨基酚'),
    'macrolide': ('大环内酯类抗生素', '用于呼吸道等感染'),
    'fluoroquinolone': ('氟喹诺酮类抗生素', '用于细菌感染'),
    'azole': ('唑类抗真菌药', '用于真菌感染'),
    'metronidazole': ('硝基咪唑类抗菌药', '用于厌氧菌、滴虫感染'),
    'penicillin': ('青霉素类抗生素', '用于细菌感染'),
    'cephalosporin': ('头孢菌素类抗生素', '用于细菌感染'),
    'allopurinol': ('黄嘌呤氧化酶抑制剂', '用于高尿酸、痛风'),
    'colchicine': ('秋水仙碱', '用于痛风急性发作'),
    'pde5': ('PDE5 抑制剂', '用于勃起功能障碍、肺动脉高压'),
    'herbal': ('中成药或植物提取物', '成分复杂，可能与处方药相互作用'),
    'vitamin': ('维生素类', '用于补充维生素'),
    'other': ('其他药物', ''),
}

# (canonical, aliases, group, extra_tags)
DRUGS: tuple[tuple[str, tuple[str, ...], str, frozenset[str]], ...] = (
    ('华法林', ('华法令',), 'anticoagulant', frozenset({'warfarin'})),
    ('利伐沙班', ('拜瑞妥', '拜瑞妥片'), 'anticoagulant', frozenset({'doac'})),
    ('达比加群', ('达比加群酯', '泰毕全'), 'anticoagulant', frozenset({'doac'})),
    ('阿哌沙班', ('艾乐妥',), 'anticoagulant', frozenset({'doac'})),
    ('阿司匹林', ('拜阿司匹林', '拜阿司匹灵', '乙酰水杨酸'), 'antiplatelet', frozenset()),
    ('氯吡格雷', ('波立维', '泰嘉'), 'antiplatelet', frozenset({'clopidogrel'})),
    ('替格瑞洛', ('倍林达',), 'antiplatelet', frozenset()),
    ('布洛芬', ('芬必得', '美林'), 'nsaid', frozenset()),
    ('双氯芬酸', ('扶他林', '双氯芬酸钠'), 'nsaid', frozenset()),
    ('塞来昔布', ('西乐葆',), 'nsaid', frozenset()),
    ('美洛昔康', (), 'nsaid', frozenset()),
    ('洛索洛芬', ('洛索洛芬钠',), 'nsaid', frozenset()),
    ('对乙酰氨基酚', ('扑热息痛', '泰诺林', '必理通', '醋氨酚'), 'acetaminophen', frozenset({'contains_acetaminophen'})),
    ('复方感冒药', ('感冒灵', '感康', '快克', '白加黑', '泰诺', '新康泰克', '复方氨酚烷胺'), 'cold_medicine', frozenset({'contains_acetaminophen'})),
    ('氨氯地平', ('络活喜', '苯磺酸氨氯地平'), 'ccb', frozenset()),
    ('左旋氨氯地平', ('施慧达',), 'ccb', frozenset()),
    ('硝苯地平', ('拜新同', '心痛定'), 'ccb', frozenset()),
    ('非洛地平', ('波依定',), 'ccb', frozenset()),
    ('缬沙坦', ('代文',), 'arb', frozenset()),
    ('厄贝沙坦', ('安博维',), 'arb', frozenset()),
    ('氯沙坦', ('科素亚',), 'arb', frozenset()),
    ('替米沙坦', ('美卡素',), 'arb', frozenset()),
    ('奥美沙坦', (), 'arb', frozenset()),
    ('坎地沙坦', (), 'arb', frozenset()),
    ('卡托普利', ('开博通',), 'acei', frozenset()),
    ('依那普利', ('依苏',), 'acei', frozenset()),
    ('培哚普利', ('雅施达',), 'acei', frozenset()),
    ('贝那普利', ('洛汀新',), 'acei', frozenset()),
    ('福辛普利', ('蒙诺',), 'acei', frozenset()),
    ('美托洛尔', ('倍他乐克', '酒石酸美托洛尔', '琥珀酸美托洛尔'), 'beta_blocker', frozenset()),
    ('比索洛尔', ('康忻', '博苏'), 'beta_blocker', frozenset()),
    ('阿替洛尔', (), 'beta_blocker', frozenset()),
    ('普萘洛尔', ('心得安',), 'beta_blocker', frozenset()),
    ('氢氯噻嗪', ('双氢克尿噻',), 'thiazide', frozenset()),
    ('吲达帕胺', ('寿比山',), 'thiazide', frozenset()),
    ('呋塞米', ('速尿',), 'loop_diuretic', frozenset()),
    ('托拉塞米', (), 'loop_diuretic', frozenset()),
    ('螺内酯', ('安体舒通',), 'potassium_sparing', frozenset()),
    ('氨苯蝶啶', (), 'potassium_sparing', frozenset()),
    ('氯化钾', ('补钾片', '枸橼酸钾'), 'potassium', frozenset()),
    ('硝酸甘油', ('硝酸甘油片',), 'nitrate', frozenset()),
    ('硝酸异山梨酯', ('消心痛',), 'nitrate', frozenset()),
    ('单硝酸异山梨酯', ('欣康', '依姆多', '鲁南欣康'), 'nitrate', frozenset()),
    ('地高辛', (), 'digoxin', frozenset()),
    ('胺碘酮', ('可达龙',), 'amiodarone', frozenset()),
    ('阿托伐他汀', ('立普妥',), 'statin', frozenset()),
    ('瑞舒伐他汀', ('可定',), 'statin', frozenset()),
    ('辛伐他汀', ('舒降之',), 'statin', frozenset()),
    ('普伐他汀', (), 'statin', frozenset()),
    ('匹伐他汀', (), 'statin', frozenset()),
    ('二甲双胍', ('格华止', '盐酸二甲双胍'), 'biguanide', frozenset()),
    ('格列美脲', ('亚莫利',), 'sulfonylurea', frozenset()),
    ('格列齐特', ('达美康',), 'sulfonylurea', frozenset()),
    ('格列吡嗪', ('瑞易宁',), 'sulfonylurea', frozenset()),
    ('格列本脲', ('优降糖',), 'sulfonylurea', frozenset()),
    ('阿卡波糖', ('拜唐苹', '卡博平'), 'alpha_glucosidase', frozenset()),
    ('伏格列波糖', ('倍欣',), 'alpha_glucosidase', frozenset()),
    ('西格列汀', ('捷诺维',), 'dpp4', frozenset()),
    ('沙格列汀', (), 'dpp4', frozenset()),
    ('利格列汀', ('欧唐宁',), 'dpp4', frozenset()),
    ('达格列净', ('安达唐',), 'sglt2', frozenset()),
    ('恩格列净', ('欧唐静',), 'sglt2', frozenset()),
    ('卡格列净', ('怡可安',), 'sglt2', frozenset()),
    ('胰岛素', ('甘精胰岛素', '门冬胰岛素', '赖脯胰岛素', '精蛋白人胰岛素', '诺和灵', '优泌林', '来得时'), 'insulin', frozenset()),
    ('奥美拉唑', ('洛赛克',), 'ppi', frozenset({'omeprazole_esomeprazole'})),
    ('埃索美拉唑', ('耐信',), 'ppi', frozenset({'omeprazole_esomeprazole'})),
    ('泮托拉唑', ('潘妥洛克',), 'ppi', frozenset()),
    ('兰索拉唑', ('达克普隆',), 'ppi', frozenset()),
    ('雷贝拉唑', ('波利特',), 'ppi', frozenset()),
    ('地西泮', ('安定',), 'benzodiazepine', frozenset({'sedative'})),
    ('阿普唑仑', ('佳静安定',), 'benzodiazepine', frozenset({'sedative'})),
    ('艾司唑仑', ('舒乐安定',), 'benzodiazepine', frozenset({'sedative'})),
    ('劳拉西泮', ('罗拉',), 'benzodiazepine', frozenset({'sedative'})),
    ('氯硝西泮', (), 'benzodiazepine', frozenset({'sedative'})),
    ('唑吡坦', ('思诺思',), 'z_drug', frozenset({'sedative'})),
    ('佐匹克隆', ('三辰',), 'z_drug', frozenset({'sedative'})),
    ('右佐匹克隆', ('文飞',), 'z_drug', frozenset({'sedative'})),
    ('曲马多', ('奇曼丁',), 'opioid', frozenset({'tramadol'})),
    ('羟考酮', ('奥施康定',), 'opioid', frozenset()),
    ('可待因', (), 'opioid', frozenset()),
    ('吗啡', ('美施康定',), 'opioid', frozenset()),
    ('舍曲林', ('左洛复',), 'ssri', frozenset()),
    ('帕罗西汀', ('赛乐特',), 'ssri', frozenset()),
    ('氟西汀', ('百忧解',), 'ssri', frozenset()),
    ('艾司西酞普兰', ('来士普',), 'ssri', frozenset()),
    ('阿米替林', (), 'anticholinergic', frozenset({'anticholinergic'})),
    ('苯海索', ('安坦',), 'anticholinergic', frozenset({'anticholinergic'})),
    ('托特罗定', ('舍尼亭',), 'anticholinergic', frozenset({'anticholinergic'})),
    ('索利那新', ('卫喜康',), 'anticholinergic', frozenset({'anticholinergic'})),
    ('氯苯那敏', ('扑尔敏',), 'anticholinergic', frozenset({'anticholinergic'})),
    ('异丙嗪', ('非那根',), 'anticholinergic', frozenset({'anticholinergic'})),
    ('左甲状腺素', ('优甲乐', '雷替斯'), 'levothyroxine', frozenset()),
    ('阿仑膦酸钠', ('福善美', '固邦'), 'bisphosphonate', frozenset()),
    ('利塞膦酸钠', (), 'bisphosphonate', frozenset()),
    ('碳酸钙', ('钙尔奇', '钙片'), 'calcium', frozenset()),
    ('枸橼酸钙', (), 'calcium', frozenset()),
    ('葡萄糖酸钙', (), 'calcium', frozenset()),
    ('硫酸亚铁', ('铁片',), 'iron', frozenset()),
    ('琥珀酸亚铁', ('速力菲',), 'iron', frozenset()),
    ('多糖铁复合物', ('力蜚能',), 'iron', frozenset()),
    ('阿奇霉素', ('希舒美',), 'macrolide', frozenset()),
    ('克拉霉素', ('克拉仙',), 'macrolide', frozenset()),
    ('红霉素', (), 'macrolide', frozenset()),
    ('左氧氟沙星', ('可乐必妥', '利复星'), 'fluoroquinolone', frozenset()),
    ('莫西沙星', ('拜复乐',), 'fluoroquinolone', frozenset()),
    ('环丙沙星', ('悉复欢',), 'fluoroquinolone', frozenset()),
    ('氟康唑', ('大扶康',), 'azole', frozenset()),
    ('伊曲康唑', ('斯皮仁诺',), 'azole', frozenset()),
    ('甲硝唑', ('灭滴灵',), 'metronidazole', frozenset()),
    ('阿莫西林', ('阿莫仙',), 'penicillin', frozenset()),
    ('头孢呋辛', ('西力欣',), 'cephalosporin', frozenset()),
    ('头孢克肟', ('世福素',), 'cephalosporin', frozenset()),
    ('别嘌醇', (), 'allopurinol', frozenset()),
    ('秋水仙碱', (), 'colchicine', frozenset()),
    ('西地那非', ('万艾可',), 'pde5', frozenset()),
    ('他达拉非', ('希爱力',), 'pde5', frozenset()),
    ('银杏叶提取物', ('银杏叶', '银杏叶片'), 'herbal', frozenset({'ginkgo'})),
    ('鱼油', ('深海鱼油', 'omega-3'), 'herbal', frozenset({'fish_oil'})),
    ('大蒜素', ('大蒜提取物',), 'herbal', frozenset({'garlic'})),
    ('圣约翰草', ('贯叶连翘',), 'herbal', frozenset({'st_johns_wort'})),
    ('人参', ('西洋参', '人参提取物'), 'herbal', frozenset()),
    ('维生素E', ('维E', '维生素e'), 'vitamin', frozenset({'vitamin_e'})),
    ('维生素K', ('维生素k',), 'vitamin', frozenset({'vitamin_k'})),
    ('纳豆', ('纳豆激酶',), 'herbal', frozenset({'vitamin_k'})),
    ('辅酶Q10', ('辅酶q10',), 'herbal', frozenset()),
    ('坦索罗辛', ('哈乐', '坦洛新'), 'other', frozenset()),
    ('非那雄胺', ('保列治',), 'other', frozenset()),
    ('多奈哌齐', ('安理申',), 'other', frozenset()),
    ('美金刚', (), 'other', frozenset()),
)

TIMING = {
    '二甲双胍': '随餐或餐后服用，可减少胃肠不适',
    '阿卡波糖': '随第一口主食嚼服',
    '伏格列波糖': '随第一口主食服用',
    '格列美脲': '通常早餐前服用，具体按医嘱',
    '格列齐特': '通常早餐前服用，具体按医嘱',
    '格列吡嗪': '通常餐前服用，具体按医嘱',
    '格列本脲': '通常早餐前服用，具体按医嘱',
    '胰岛素': '按医嘱在餐前或固定时间注射',
    '左甲状腺素': '晨起空腹，服后至少 30 分钟再进食',
    '阿仑膦酸钠': '晨起空腹，足量白水送服，服后 30 分钟内保持直立',
    '利塞膦酸钠': '晨起空腹，足量白水送服，服后保持直立',
    '奥美拉唑': '餐前 30–60 分钟服用',
    '埃索美拉唑': '餐前 30–60 分钟服用',
    '泮托拉唑': '餐前服用',
    '兰索拉唑': '餐前服用',
    '雷贝拉唑': '餐前服用',
    '阿司匹林': '肠溶片通常餐前空腹服用，具体以说明书和医嘱为准',
    '布洛芬': '餐后服用，减少胃部刺激',
    '双氯芬酸': '餐后服用，减少胃部刺激',
    '塞来昔布': '餐后服用，减少胃部刺激',
    '对乙酰氨基酚': '餐后服用，避免长期超量',
    '呋塞米': '晨起服用，避免夜间频繁排尿',
    '氢氯噻嗪': '晨起服用，避免夜间频繁排尿',
    '吲达帕胺': '晨起服用',
    '华法林': '每天固定时间服用，便于按凝血指标调整',
    '利伐沙班': '固定时间随餐服用（按说明书）',
    '达比加群': '固定时间整粒吞服，不要掰开',
    '硝酸甘油': '心绞痛发作时舌下含服，不作日常预防用药',
    '单硝酸异山梨酯': '晨起服用，具体按医嘱',
    '阿托伐他汀': '每天固定时间服用，短效他汀多建议睡前',
    '瑞舒伐他汀': '每天固定时间服用',
    '辛伐他汀': '睡前服用',
    '美托洛尔': '晨起服用，注意监测心率',
    '比索洛尔': '晨起服用，注意监测心率',
    '地高辛': '每天固定时间服用',
    '坦索罗辛': '睡前服用，可减少体位性低血压',
    '唑吡坦': '睡前即刻服用',
    '佐匹克隆': '睡前服用',
    '右佐匹克隆': '睡前服用',
    '多奈哌齐': '睡前服用',
    '别嘌醇': '餐后服用，注意皮疹等过敏表现',
    '左氧氟沙星': '与含铝镁抗酸药、钙剂、铁剂间隔约 2 小时',
    '莫西沙星': '与含铝镁抗酸药、钙剂、铁剂间隔约 2 小时',
    '硫酸亚铁': '餐前或两餐间服用，避免与钙剂、浓茶同服',
    '琥珀酸亚铁': '餐前或两餐间服用，避免与钙剂、浓茶同服',
    '碳酸钙': '随餐服用',
}

SPECIAL_MISSED_DOSE = {'华法林', '利伐沙班', '达比加群', '阿哌沙班', '胰岛素', '格列美脲', '格列齐特', '格列吡嗪', '格列本脲'}

HYPOTENSIVE = {'ccb', 'acei', 'arb', 'beta_blocker', 'thiazide', 'loop_diuretic', 'potassium_sparing', 'nitrate'}
GLUCOSE_LOWERING = {'biguanide', 'sulfonylurea', 'insulin', 'alpha_glucosidase', 'dpp4', 'sglt2'}


@dataclass(frozen=True)
class InteractionRule:
    id: str
    left: frozenset[str]
    right: frozenset[str]
    severity: str
    title: str
    detail: str
    action: str
    requires: frozenset[str] = frozenset()
    min_drugs: int = 2


DEFER = '请让开药的医生或药师核对，不要自行停药、加量或减量。'
URGENT = '建议尽快联系开药医生或药师核对方案；如出现不适加重，及时就医。'

RULES: tuple[InteractionRule, ...] = (
    InteractionRule('anticoagulant_antiplatelet', frozenset({'anticoagulant'}), frozenset({'antiplatelet'}), 'high',
                    '抗凝药与抗血小板药同用', '同时使用抗凝药和抗血小板药会明显增加出血风险，包括消化道出血和颅内出血。',
                    URGENT + '如出现黑便、呕血、持续头痛或皮下大片瘀斑，请立即就医。'),
    InteractionRule('anticoagulant_nsaid', frozenset({'anticoagulant'}), frozenset({'nsaid'}), 'high',
                    '抗凝药与解热镇痛药同用', '非甾体抗炎药会损伤胃黏膜并抑制血小板，与抗凝药合用显著增加消化道出血风险。',
                    URGENT + '如出现黑便、呕血或腹痛加重，请立即就医。'),
    InteractionRule('warfarin_macrolide', frozenset({'warfarin'}), frozenset({'macrolide', 'azole', 'metronidazole', 'fluoroquinolone'}), 'high',
                    '华法林与部分抗菌药同用', '部分抗菌药会影响华法林代谢或肠道菌群，使凝血指标升高、出血风险增加。',
                    '请让医生或药师核对并考虑监测凝血功能（如 INR）；不要自行调整华法林剂量。'),
    InteractionRule('antiplatelet_nsaid', frozenset({'antiplatelet'}), frozenset({'nsaid'}), 'high',
                    '抗血小板药与解热镇痛药同用', '两者都会影响血小板和胃黏膜，合用增加消化道出血风险；布洛芬还可能削弱小剂量阿司匹林的抗血小板作用。',
                    URGENT + '如需止痛，请先让医生或药师选择合适方案。'),
    InteractionRule('acei_arb_potassium_sparing', frozenset({'acei', 'arb'}), frozenset({'potassium_sparing', 'potassium'}), 'high',
                    '降压药与保钾药同用', '普利类/沙坦类降压药与保钾利尿剂或补钾制剂合用可能引起血钾升高，严重时影响心律。',
                    '请让医生核对并按需复查血钾和肾功能；不要自行加用补钾药。'),
    InteractionRule('triple_whammy', frozenset({'acei', 'arb'}), frozenset({'nsaid'}), 'high',
                    '降压药、利尿剂与解热镇痛药三联', '普利类/沙坦类 + 利尿剂 + 非甾体抗炎药合用被称为“三重打击”，可能引起急性肾功能损害。',
                    '请尽快让医生或药师核对，避免自行长期合用止痛药。', requires=frozenset({'thiazide', 'loop_diuretic'})),
    InteractionRule('sulfonylurea_insulin', frozenset({'sulfonylurea'}), frozenset({'insulin'}), 'high',
                    '磺脲类与胰岛素同用', '两类降糖药作用叠加，低血糖风险明显增加。',
                    '请让医生核对降糖方案，并按医嘱监测血糖；出现出汗、心慌、手抖或意识改变时及时处理。'),
    InteractionRule('sulfonylurea_azole', frozenset({'sulfonylurea'}), frozenset({'azole', 'fluoroquinolone', 'macrolide'}), 'moderate',
                    '磺脲类与部分抗菌药同用', '部分抗菌药可能增强磺脲类降糖作用，增加低血糖风险。',
                    '请让医生或药师在用药期间加强血糖监测，不要自行调整降糖药。'),
    InteractionRule('statin_macrolide', frozenset({'statin'}), frozenset({'macrolide', 'azole'}), 'high',
                    '他汀与部分抗菌药同用', '部分抗菌药会抑制他汀代谢，使肌肉损伤风险增加。',
                    '请让医生或药师核对是否需要换药或暂停他汀；出现肌肉酸痛无力或尿色变深请及时就医。'),
    InteractionRule('digoxin_amiodarone', frozenset({'digoxin'}), frozenset({'amiodarone'}), 'high',
                    '地高辛与胺碘酮同用', '胺碘酮可使地高辛血药浓度升高，增加中毒风险。',
                    DEFER + '出现恶心、看东西发黄或心律不齐时请及时就医。'),
    InteractionRule('digoxin_diuretic', frozenset({'digoxin'}), frozenset({'loop_diuretic', 'thiazide'}), 'moderate',
                    '地高辛与利尿剂同用', '利尿剂可能引起低钾，低钾会增加地高辛中毒风险。',
                    '请让医生按需复查血钾和地高辛相关指标。'),
    InteractionRule('nitrate_pde5', frozenset({'nitrate'}), frozenset({'pde5'}), 'high',
                    '硝酸酯与 PDE5 抑制剂同用', '两者合用可引起严重低血压，甚至晕厥、心肌缺血。',
                    '请立即告知医生这两类药的使用情况；未经医生评估不要同时使用。'),
    InteractionRule('sedative_opioid', frozenset({'sedative'}), frozenset({'opioid'}), 'high',
                    '镇静催眠药与阿片类镇痛药同用', '两者都抑制中枢，合用可能引起过度镇静、呼吸抑制和跌倒。',
                    URGENT + '如出现嗜睡难唤醒、呼吸变慢，请立即就医。'),
    InteractionRule('sedative_sedative', frozenset({'sedative'}), frozenset({'sedative'}), 'moderate',
                    '两种以上镇静催眠药同用', '同时使用多种镇静催眠药会增加跌倒、认知下降和夜间意识模糊的风险。',
                    '请让医生或药师核对是否可以精简，不要自行叠加助眠药。'),
    InteractionRule('ppi_clopidogrel', frozenset({'omeprazole_esomeprazole'}), frozenset({'clopidogrel'}), 'moderate',
                    '奥美拉唑类与氯吡格雷同用', '奥美拉唑、埃索美拉唑可能削弱氯吡格雷的抗血小板作用。',
                    '请让医生或药师评估是否需要换用其他抑酸药，不要自行停药。'),
    InteractionRule('levothyroxine_calcium_iron', frozenset({'levothyroxine'}), frozenset({'calcium', 'iron'}), 'moderate',
                    '左甲状腺素与钙剂/铁剂同用', '钙剂、铁剂会影响左甲状腺素吸收，降低药效。',
                    '请把两类药间隔至少 4 小时服用，并告知医生正在补充钙或铁。'),
    InteractionRule('bisphosphonate_calcium_iron', frozenset({'bisphosphonate'}), frozenset({'calcium', 'iron'}), 'moderate',
                    '双膦酸盐与钙剂/铁剂同用', '同服会影响双膦酸盐吸收。',
                    '请按说明书把服药时间错开，具体间隔让药师确认。'),
    InteractionRule('iron_calcium', frozenset({'iron'}), frozenset({'calcium'}), 'note',
                    '铁剂与钙剂同用', '钙会降低铁的吸收。',
                    '建议间隔服用，具体时间让药师确认。'),
    InteractionRule('duplicate_acetaminophen', frozenset({'contains_acetaminophen'}), frozenset({'contains_acetaminophen'}), 'high',
                    '重复使用含对乙酰氨基酚的药物', '多种感冒药、退烧药和止痛药常含同一成分，叠加使用容易超过每日安全总量，造成肝损伤。',
                    '请把正在吃的所有感冒药、退烧药拿给药师核对成分，不要同时服用多种含对乙酰氨基酚的药。'),
    InteractionRule('anticholinergic_burden', frozenset({'anticholinergic'}), frozenset({'anticholinergic'}), 'moderate',
                    '多种抗胆碱能药同用', '老年人同时使用多种抗胆碱能药，容易出现口干、便秘、排尿困难、视物模糊和意识模糊，并增加跌倒风险。',
                    '请让医生或药师核对能否精简，不要自行加药。'),
    InteractionRule('sglt2_diuretic', frozenset({'sglt2'}), frozenset({'loop_diuretic', 'thiazide'}), 'moderate',
                    'SGLT-2 抑制剂与利尿剂同用', '两者都可能引起脱水、低血压和肾功能波动。',
                    '请让医生关注饮水量、血压和肾功能，出现明显乏力头晕及时就诊。'),
    InteractionRule('ssri_nsaid', frozenset({'ssri'}), frozenset({'nsaid'}), 'moderate',
                    'SSRI 类抗抑郁药与解热镇痛药同用', '合用会增加消化道出血风险。',
                    '请让医生或药师评估是否需要胃黏膜保护，不要自行长期合用止痛药。'),
    InteractionRule('ssri_tramadol', frozenset({'ssri'}), frozenset({'tramadol'}), 'moderate',
                    'SSRI 与曲马多同用', '两者都可能影响 5-羟色胺，合用有 5-羟色胺综合征风险。',
                    '请让医生或药师核对；出现发热、震颤、大汗或意识改变及时就医。'),
    InteractionRule('warfarin_herbal', frozenset({'warfarin'}), frozenset({'ginkgo', 'fish_oil', 'garlic', 'vitamin_e'}), 'moderate',
                    '华法林与部分保健品同用', '银杏、鱼油、大蒜提取物和大剂量维生素 E 可能增加出血倾向。',
                    '请把保健品清单交给医生或药师核对，不要自行停用华法林。'),
    InteractionRule('warfarin_vitamin_k', frozenset({'warfarin'}), frozenset({'vitamin_k'}), 'moderate',
                    '华法林与维生素 K 同用', '维生素 K（含纳豆）会减弱华法林的抗凝作用。',
                    '请保持饮食和补充剂相对稳定，并告知医生；不要自行改变摄入量。'),
    InteractionRule('multiple_antihypertensives', frozenset({'antihypertensive'}), frozenset({'antihypertensive'}), 'note',
                    '多种降压药同用', '同时使用三种及以上降压药时，体位性低血压和跌倒风险增加。',
                    '起身动作放慢，按医嘱监测血压；如反复头晕眼前发黑请就诊。', min_drugs=3),
)

INTERACTION_LABELS = {'high': '需尽快核对', 'moderate': '需要关注', 'note': '用药提示'}


def normalize(text: str) -> str:
    return unicodedata.normalize('NFKC', text or '')


def _tags(group: str, extra: frozenset[str]) -> frozenset[str]:
    tags = {group, *extra}
    if group in HYPOTENSIVE: tags.add('antihypertensive')
    if group in GLUCOSE_LOWERING: tags.add('glucose_lowering')
    return frozenset(tags)


ALIAS_INDEX: dict[str, str] = {}
for _name, _aliases, _group, _extra in DRUGS:
    ALIAS_INDEX[_name] = _name
    for _alias in _aliases:
        ALIAS_INDEX.setdefault(_alias, _name)
ALIAS_ORDER = sorted(ALIAS_INDEX, key=len, reverse=True)
DRUG_BY_NAME = {name: (aliases, group, extra) for name, aliases, group, extra in DRUGS}


def mention(canonical: str, *, frequency: str = 'unknown', source: str = 'parsed') -> DrugMention:
    aliases, group, extra = DRUG_BY_NAME[canonical]
    label, indication = CLASS_INFO[group]
    return DrugMention(name=canonical, canonical=canonical, classes=[group], class_label=label,
                       tags=sorted(_tags(group, extra)), indication=indication,
                       timing_hint=TIMING.get(canonical), user_frequency=frequency, source=source)


def parse_frequency(text: str) -> str:
    text = normalize(text)
    if re.search(r'每周(?:一|1)次|一周一次', text): return 'weekly'
    if re.search(r'每天|每日|一天|一日', text):
        if re.search(r'(?:每天|每日|一天|一日)\s*(?:四|4)\s*次|早中晚夜|早中晚睡前', text): return 'four_daily'
        if re.search(r'(?:每天|每日|一天|一日)\s*(?:三|3)\s*次|早中晚各', text): return 'three_daily'
        if re.search(r'(?:每天|每日|一天|一日)\s*(?:两|二|2)\s*次|早晚各', text): return 'twice_daily'
        return 'once_daily'
    if re.search(r'必要时|需要时|按需', text): return 'as_needed'
    return 'unknown'


def extract(text: str, provided: list[MedicationItem]) -> tuple[list[DrugMention], list[str]]:
    text = normalize(text)
    found: dict[str, int] = {}
    consumed: list[tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(start < other_end and other_start < end for other_start, other_end in consumed)

    # Longest alias first, and never count an alias nested inside a longer match
    # (泰诺林 is acetaminophen, not the cold medicine 泰诺).
    for alias in ALIAS_ORDER:
        position = text.find(alias)
        while position >= 0 and overlaps(position, position + len(alias)):
            position = text.find(alias, position + 1)
        if position < 0: continue
        consumed.append((position, position + len(alias)))
        canonical = ALIAS_INDEX[alias]
        if canonical not in found or position < found[canonical]:
            found[canonical] = position
    mentions = [mention(name, frequency='unknown') for name in sorted(found, key=found.get)]
    unknown: list[str] = []
    for item in provided:
        name = normalize(item.name).strip()
        if not name: continue
        canonical = ALIAS_INDEX.get(name)
        if canonical is None:
            for alias in ALIAS_ORDER:
                if alias in name:
                    canonical = ALIAS_INDEX[alias]
                    break
        if canonical is None:
            if name not in unknown: unknown.append(name)
            continue
        if any(existing.canonical == canonical for existing in mentions):
            existing = next(existing for existing in mentions if existing.canonical == canonical)
            if item.frequency != 'unknown':
                index = mentions.index(existing)
                mentions[index] = existing.model_copy(update={'user_frequency': item.frequency, 'source': 'provided'})
            continue
        mentions.append(mention(canonical, frequency=item.frequency, source='provided'))
    return mentions, unknown


def _all_tags(drugs: list[DrugMention]) -> set[str]:
    tags: set[str] = set()
    for drug in drugs: tags.update(drug.tags)
    return tags


def interactions(drugs: list[DrugMention]) -> list[InteractionFinding]:
    findings: list[InteractionFinding] = []
    for rule in RULES:
        left = [drug for drug in drugs if rule.left & set(drug.tags)]
        right = [drug for drug in drugs if rule.right & set(drug.tags)]
        if not left or not right: continue
        if rule.requires and not (rule.requires & _all_tags(drugs)): continue
        involved = []
        for drug in (left + right):
            if drug.name not in involved: involved.append(drug.name)
        if len(involved) < rule.min_drugs: continue
        findings.append(InteractionFinding(id=rule.id, severity=rule.severity, title=rule.title,
                                           drugs=involved, detail=rule.detail, action=rule.action))
    order = {'high': 0, 'moderate': 1, 'note': 2}
    findings.sort(key=lambda item: (order[item.severity], item.id))
    return findings


def assess(text: str, provided: list[MedicationItem], profile: MedicationProfile | None = None) -> MedicationAssessment:
    drugs, unknown = extract(text, provided)
    frequency = parse_frequency(text)
    if frequency == 'unknown' and provided:
        known = [item.frequency for item in provided if item.frequency != 'unknown']
        if known: frequency = max(set(known), key=known.count)
    findings = interactions(drugs)
    # Age-related cautions: sedatives and anticholinergics in older adults.
    if profile and profile.age and profile.age >= 65:
        sedatives = [drug for drug in drugs if 'sedative' in drug.tags]
        if sedatives:
            findings.append(InteractionFinding(
                id='older_adult_sedative', severity='moderate', title='老年人使用镇静催眠药',
                drugs=[drug.name for drug in sedatives],
                detail='老年人使用镇静催眠药后，夜间跌倒、次日嗜睡和认知模糊的风险更高。',
                action='请让医生评估是否仍需使用，夜间起身放慢动作；不要自行加量。'))
        anticholinergic = [drug for drug in drugs if 'anticholinergic' in drug.tags]
        if anticholinergic:
            findings.append(InteractionFinding(
                id='older_adult_anticholinergic', severity='moderate', title='老年人使用抗胆碱能药',
                drugs=[drug.name for drug in anticholinergic],
                detail='抗胆碱能药在老年人中容易引起口干、便秘、排尿困难和意识模糊。',
                action='请让医生或药师核对能否换用风险更低的方案。'))
        order = {'high': 0, 'moderate': 1, 'note': 2}
        findings.sort(key=lambda item: (order[item.severity], item.id))
    if profile:
        for condition, label, tags in (('peptic_ulcer', '消化性溃疡史', {'nsaid', 'antiplatelet', 'anticoagulant'}),
                                       ('asthma', '哮喘', {'beta_blocker'}),
                                       ('ckd', '慢性肾脏病', {'nsaid'})):
            if condition in profile.conditions:
                risky = [drug for drug in drugs if tags & set(drug.tags)]
                if risky:
                    findings.append(InteractionFinding(
                        id=f'condition_{condition}', severity='moderate', title=f'基础疾病（{label}）与当前用药',
                        drugs=[drug.name for drug in risky],
                        detail=f'有{label}时，这类药物的风险可能更高，需要医生结合病史评估。',
                        action='请在就诊时主动说明基础疾病，让医生核对用药。'))
        order = {'high': 0, 'moderate': 1, 'note': 2}
        findings.sort(key=lambda item: (order[item.severity], item.id))
    return MedicationAssessment(drugs=drugs, interactions=findings, unknown_names=unknown,
                                frequency=frequency, table_version=TABLE_VERSION)


# ---------------------------------------------------------------- missed dose

MISSED_TEMPLATE = ('想起漏服时：如果距离下一次服药时间还比较久，可以按原剂量补服一次；'
                   '如果已经接近下一次服药时间，就跳过这次，按原计划服用下一次。'
                   '任何时候都不要一次服用双倍剂量。')
MISSED_SPECIAL = ('这类药（抗凝药或降糖药）漏服后不要自行补服或加倍，请直接联系开药医生或药师，'
                  '说明漏服时间、当时是否进食以及最近的测量结果。')


def missed_dose_advice(assessment: MedicationAssessment) -> str:
    if not assessment.drugs:
        return MISSED_TEMPLATE + ' 如果不确定，请把药盒和服用时间给药师核对。'
    special = [drug.name for drug in assessment.drugs if drug.canonical in SPECIAL_MISSED_DOSE]
    if special:
        return '、'.join(special) + '：' + MISSED_SPECIAL
    frequency = assessment.frequency
    if frequency == 'once_daily':
        return ('每天一次的药：想起时若距下一次服药还有较长时间，可以尽快补服；'
                '若已接近下一次服药时间，跳过本次，下一次按原剂量服用。不要一次吃双倍剂量。')
    if frequency in {'twice_daily', 'three_daily', 'four_daily'}:
        return ('每天多次的药：以给药间隔的一半为界，距下一次服药超过半个间隔可以补服，'
                '否则跳过本次，下一次按原剂量服用。不要一次吃双倍剂量。')
    if frequency == 'weekly':
        return '每周一次的药：想起时尽快补服，若已接近下一次服药时间则跳过；具体补服方式请与医生确认。'
    if frequency == 'as_needed':
        return '按需服用的药不需要补服，需要时按说明书或医嘱使用。'
    return MISSED_TEMPLATE + ' 不同药物规则不同，请把药名和服用时间交给医生或药师核对。'


# ---------------------------------------------------------------- triage

ALLERGY_WORDS = ('皮疹', '风团', '瘙痒', '起疹子', '过敏')
AIRWAY_WORDS = ('呼吸困难', '喘不上气', '喉咙紧', '嗓子紧', '嘴唇肿', '脸肿', '舌头肿', '声音嘶哑')
BLEED_WORDS = ('呕血', '吐血', '黑便', '大便发黑', '便血', '血便')
HEAD_WORDS = ('剧烈头痛', '头痛欲裂', '意识模糊', '叫不醒', '昏迷')
HYPO_WORDS = ('出汗', '心慌', '手抖', '发抖', '冷汗', '饥饿感')
CONSCIOUS_WORDS = ('意识模糊', '意识不清', '晕倒', '晕厥', '叫不醒', '嗜睡')
RESP_WORDS = ('呼吸变慢', '呼吸很浅', '叫不醒')
MUSCLE_WORDS = ('肌肉酸痛', '肌肉无力', '肌肉疼', '腿没劲', '全身酸痛')
DARK_URINE_WORDS = ('尿色深', '酱油色尿', '尿像浓茶', '尿液发黑')
JAUNDICE_WORDS = ('黄疸', '皮肤发黄', '眼白发黄', '尿色加深')
PALPITATION_WORDS = ('心跳慢', '心率慢', '脉搏慢')
SEROTONIN_WORDS = ('震颤', '大汗', '发热', '抽搐')
DIGOXIN_WORDS = ('看东西发黄', '视物发黄', '恶心', '心律不齐')
MINOR_BLEED_WORDS = ('牙龈出血', '皮下瘀斑', '瘀青', '刷牙出血')
GI_WORDS = ('胃疼', '胃痛', '胃不舒服', '恶心', '反酸', '腹泻')

NEGATION = re.compile(r'(?:没有|没|无|未|不|否认|并非)[^。；\n]{0,4}$')


def _present(text: str, words) -> list[str]:
    found = []
    for word in words:
        for match in re.finditer(re.escape(word), text):
            if NEGATION.search(text[max(0, match.start() - 8):match.start()]): continue
            found.append(word); break
    return found


def triage(assessment: MedicationAssessment, text: str, profile: MedicationProfile | None = None) -> MedicationTriage:
    text = normalize(text)
    tags = _all_tags(assessment.drugs)
    rules: list[str] = []
    allergy = _present(text, ALLERGY_WORDS)
    airway = _present(text, AIRWAY_WORDS)
    if allergy and airway: rules.append('airway_swelling')
    elif allergy: rules.append('allergic_reaction_minor')
    if '过敏性休克' in text or '休克' in text: rules.append('anaphylaxis')
    if _present(text, BLEED_WORDS): rules.append('gi_bleeding')
    if _present(text, HEAD_WORDS) and tags & {'anticoagulant', 'antiplatelet'}: rules.append('intracranial_bleeding')
    if _present(text, CONSCIOUS_WORDS): rules.append('altered_consciousness')
    if _present(text, RESP_WORDS) and tags & {'sedative', 'opioid'}: rules.append('respiratory_depression')
    hypo = _present(text, HYPO_WORDS)
    if hypo and tags & {'glucose_lowering'}:
        rules.append('hypoglycemia_severe' if _present(text, CONSCIOUS_WORDS) else 'hypoglycemia')
    if _present(text, MUSCLE_WORDS) and _present(text, DARK_URINE_WORDS) and 'statin' in tags: rules.append('rhabdomyolysis')
    if _present(text, JAUNDICE_WORDS) and tags & {'contains_acetaminophen', 'statin'}: rules.append('liver_injury')
    if _present(text, PALPITATION_WORDS) and tags & {'beta_blocker', 'digoxin', 'amiodarone'}: rules.append('bradycardia')
    if _present(text, SEROTONIN_WORDS) and 'ssri' in tags and tags & {'tramadol', 'st_johns_wort'}: rules.append('serotonin')
    if _present(text, DIGOXIN_WORDS) and 'digoxin' in tags: rules.append('digoxin_toxicity')
    if _present(text, MINOR_BLEED_WORDS) and tags & {'anticoagulant', 'antiplatelet'}: rules.append('bleeding_minor')
    if _present(text, GI_WORDS) and tags & {'nsaid', 'biguanide', 'antiplatelet'}: rules.append('gi_intolerance')
    if assessment.high_count() and not rules and text: rules.append('interaction_needs_review')
    order = ['anaphylaxis', 'airway_swelling', 'gi_bleeding', 'intracranial_bleeding', 'hypoglycemia_severe',
             'altered_consciousness', 'respiratory_depression', 'rhabdomyolysis', 'liver_injury', 'bradycardia',
             'hypoglycemia', 'serotonin', 'digoxin_toxicity', 'allergic_reaction_minor', 'bleeding_minor',
             'gi_intolerance', 'interaction_needs_review']
    labels = {
        'anaphylaxis': '过敏性休克表现', 'airway_swelling': '过敏伴口唇或喉头肿胀、呼吸困难',
        'gi_bleeding': '呕血、黑便或便血', 'intracranial_bleeding': '抗凝/抗血小板药使用中出现剧烈头痛伴意识改变',
        'hypoglycemia_severe': '低血糖伴意识改变', 'altered_consciousness': '意识模糊或晕倒',
        'respiratory_depression': '镇静或阿片类药物相关的呼吸抑制', 'rhabdomyolysis': '他汀相关肌肉损伤表现',
        'liver_injury': '药物相关肝损伤表现', 'bradycardia': '心率明显偏慢伴头晕',
        'hypoglycemia': '低血糖表现', 'serotonin': '5-羟色胺综合征表现', 'digoxin_toxicity': '地高辛中毒表现',
        'allergic_reaction_minor': '药物过敏表现', 'bleeding_minor': '轻度出血表现',
        'gi_intolerance': '胃肠道不适', 'interaction_needs_review': '存在需核对的药物相互作用',
    }
    positive = [rule for rule in order if rule in rules]
    level = 'L4'
    if any(rule in {'anaphylaxis', 'airway_swelling', 'gi_bleeding', 'intracranial_bleeding', 'hypoglycemia_severe',
                    'altered_consciousness', 'respiratory_depression'} for rule in positive): level = 'L1'
    elif any(rule in {'rhabdomyolysis', 'liver_injury', 'bradycardia', 'hypoglycemia', 'serotonin', 'digoxin_toxicity'} for rule in positive): level = 'L2'
    elif any(rule in {'bleeding_minor', 'gi_intolerance', 'allergic_reaction_minor'} for rule in positive): level = 'L3'
    elif positive: level = 'L3'
    actions = {'L1': 'call_120', 'L2': 'contact_doctor_24h', 'L3': 'pharmacist_advice', 'L4': 'self_care'}
    return MedicationTriage(level=level, rule_ids=positive, required_action=actions[level],
                            red_flags=[labels[rule] for rule in positive], table_version=TABLE_VERSION)
