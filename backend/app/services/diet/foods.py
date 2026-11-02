"""Curated food dictionary, tags, portion reference and BMI.

The dictionary decides food flags; the portion table is what the answer displays.
Neither is a prescription: every item carries a "reference, not prescription" note.
"""
import re
import unicodedata
from dataclasses import dataclass

from app.schemas.diet import FoodInput, FoodMention, PortionItem, PortionReference

TABLE_VERSION = 'diet-ref-2022.1'
DISPLAY_VERSION = '份量表 ' + TABLE_VERSION

# category -> (label, default flags)
CATEGORY_INFO: dict[str, tuple[str, frozenset[str]]] = {
    'staple_refined': ('精制主食', frozenset({'staple'})),
    'staple_whole': ('全谷物/杂豆', frozenset({'staple', 'whole_grain'})),
    'potato': ('薯类', frozenset({'staple', 'high_potassium'})),
    'protein_animal': ('动物性蛋白', frozenset({'protein'})),
    'protein_plant': ('豆制品', frozenset({'protein', 'plant_protein'})),
    'egg': ('蛋类', frozenset({'protein'})),
    'dairy': ('奶及奶制品', frozenset({'protein', 'calcium'})),
    'vegetable_leafy': ('深色蔬菜', frozenset({'vegetable', 'vitamin_k', 'high_potassium'})),
    'vegetable_other': ('蔬菜', frozenset({'vegetable'})),
    'fruit': ('水果', frozenset({'fruit'})),
    'fruit_high_k': ('水果', frozenset({'fruit', 'high_potassium'})),
    'nut': ('坚果', frozenset({'protein', 'high_potassium', 'high_fat'})),
    'high_salt': ('腌制或高盐食品', frozenset({'high_salt'})),
    'high_fat': ('高油食品', frozenset({'high_fat'})),
    'high_sugar': ('高糖食品', frozenset({'high_sugar'})),
    'high_purine': ('高嘌呤食物', frozenset({'high_purine'})),
    'condiment': ('调味品', frozenset({'condiment'})),
    'beverage': ('饮品', frozenset()),
    'alcohol': ('含酒精饮品', frozenset({'alcohol'})),
    'processed_meat': ('加工肉制品', frozenset({'high_salt', 'processed'})),
    'soup': ('汤类', frozenset()),
    'texture_hard': ('质地偏硬', frozenset({'texture_hard'})),
    'raw_risk': ('生食或高风险食物', frozenset({'raw_risk'})),
    'dessert': ('甜点', frozenset({'high_sugar', 'high_fat'})),
    'supplement': ('营养补充剂', frozenset({'supplement'})),
    'other': ('其他', frozenset()),
}

FLAG_LABELS = {
    'high_salt': '高盐', 'high_fat': '高油', 'high_sugar': '高糖', 'high_purine': '高嘌呤',
    'high_potassium': '含钾较高', 'vitamin_k': '含维生素 K', 'calcium': '富含钙', 'protein': '蛋白质',
    'vegetable': '蔬菜', 'fruit': '水果', 'staple': '主食', 'whole_grain': '全谷物',
    'alcohol': '含酒精', 'caffeine': '含咖啡因', 'grapefruit': '西柚类', 'raw_risk': '生食风险',
    'texture_hard': '质地偏硬', 'processed': '加工食品', 'supplement': '补充剂', 'plant_protein': '植物蛋白',
}

# (name, aliases, category, extra flags)
FOODS: tuple[tuple[str, tuple[str, ...], str, frozenset[str]], ...] = (
    ('白米饭', ('米饭', '大米饭', '蒸饭'), 'staple_refined', frozenset()),
    ('白粥', ('稀饭', '大米粥', '米粥', '粥'), 'staple_refined', frozenset()),
    ('馒头', ('花卷',), 'staple_refined', frozenset()),
    ('面条', ('挂面', '汤面', '拉面', '面'), 'staple_refined', frozenset()),
    ('米粉', ('米线', '河粉'), 'staple_refined', frozenset()),
    ('饺子', ('水饺',), 'staple_refined', frozenset()),
    ('包子', ('肉包', '菜包'), 'staple_refined', frozenset()),
    ('烙饼', ('饼', '葱油饼'), 'staple_refined', frozenset()),
    ('面包', (), 'staple_refined', frozenset()),
    ('全麦面包', ('全麦',), 'staple_whole', frozenset()),
    ('燕麦', ('燕麦片', '麦片'), 'staple_whole', frozenset()),
    ('糙米', ('糙米饭',), 'staple_whole', frozenset()),
    ('玉米', ('玉米棒', '老玉米'), 'staple_whole', frozenset()),
    ('小米粥', ('小米',), 'staple_whole', frozenset()),
    ('杂豆', ('红豆', '绿豆', '芸豆'), 'staple_whole', frozenset()),
    ('荞麦', ('荞麦面',), 'staple_whole', frozenset()),
    ('藜麦', (), 'staple_whole', frozenset()),
    ('红薯', ('地瓜', '番薯'), 'potato', frozenset()),
    ('土豆', ('马铃薯', '洋芋'), 'potato', frozenset()),
    ('山药', (), 'potato', frozenset()),
    ('鸡蛋', ('蛋', '水煮蛋', '蒸蛋', '鸡蛋羹'), 'egg', frozenset()),
    ('鸭蛋', (), 'egg', frozenset()),
    ('咸鸭蛋', ('咸蛋',), 'high_salt', frozenset()),
    ('牛奶', ('纯牛奶', '鲜奶'), 'dairy', frozenset()),
    ('酸奶', ('酸牛奶',), 'dairy', frozenset()),
    ('奶粉', (), 'dairy', frozenset()),
    ('奶酪', ('芝士',), 'dairy', frozenset()),
    ('豆浆', (), 'protein_plant', frozenset()),
    ('豆腐', ('北豆腐', '南豆腐', '嫩豆腐'), 'protein_plant', frozenset()),
    ('豆干', ('豆腐干', '香干'), 'protein_plant', frozenset()),
    ('腐竹', (), 'protein_plant', frozenset()),
    ('黄豆', ('大豆',), 'protein_plant', frozenset()),
    ('纳豆', (), 'protein_plant', frozenset({'vitamin_k'})),
    ('瘦肉', ('猪瘦肉', '里脊'), 'protein_animal', frozenset()),
    ('猪肉', ('五花肉',), 'protein_animal', frozenset()),
    ('牛肉', (), 'protein_animal', frozenset()),
    ('羊肉', (), 'protein_animal', frozenset()),
    ('鸡肉', ('鸡胸肉', '鸡腿'), 'protein_animal', frozenset()),
    ('鸭肉', (), 'protein_animal', frozenset()),
    ('鱼', ('鱼肉', '清蒸鱼', '鲫鱼', '鲈鱼'), 'protein_animal', frozenset()),
    ('三文鱼', ('深海鱼',), 'protein_animal', frozenset()),
    ('带鱼', (), 'protein_animal', frozenset()),
    ('虾', ('虾仁', '基围虾'), 'protein_animal', frozenset()),
    ('螃蟹', ('蟹', '大闸蟹'), 'protein_animal', frozenset({'high_purine'})),
    ('动物肝脏', ('猪肝', '肝', '鸡肝'), 'protein_animal', frozenset({'high_purine', 'vitamin_k', 'iron'})),
    ('鸭血', ('猪血', '动物血', '血豆腐'), 'protein_animal', frozenset({'iron'})),
    ('蛋白粉', ('乳清蛋白', '蛋白质粉'), 'supplement', frozenset()),
    ('鱼油', ('深海鱼油',), 'supplement', frozenset()),
    ('红烧肉', ('东坡肉',), 'protein_animal', frozenset({'high_fat'})),
    ('菠菜', (), 'vegetable_leafy', frozenset()),
    ('油菜', ('小白菜', '青菜'), 'vegetable_leafy', frozenset()),
    ('生菜', (), 'vegetable_leafy', frozenset()),
    ('芹菜', (), 'vegetable_leafy', frozenset()),
    ('西兰花', ('绿花菜',), 'vegetable_leafy', frozenset()),
    ('卷心菜', ('圆白菜', '包菜'), 'vegetable_leafy', frozenset()),
    ('白菜', ('大白菜',), 'vegetable_other', frozenset()),
    ('胡萝卜', (), 'vegetable_other', frozenset()),
    ('番茄', ('西红柿',), 'vegetable_other', frozenset()),
    ('黄瓜', (), 'vegetable_other', frozenset()),
    ('茄子', (), 'vegetable_other', frozenset()),
    ('青椒', ('辣椒',), 'vegetable_other', frozenset()),
    ('冬瓜', (), 'vegetable_other', frozenset()),
    ('南瓜', (), 'vegetable_other', frozenset()),
    ('苦瓜', (), 'vegetable_other', frozenset()),
    ('白萝卜', ('萝卜',), 'vegetable_other', frozenset()),
    ('莲藕', ('藕',), 'vegetable_other', frozenset()),
    ('豆角', ('四季豆', '扁豆'), 'vegetable_other', frozenset({'raw_risk'})),
    ('菌菇', ('香菇', '蘑菇', '金针菇'), 'vegetable_other', frozenset({'high_potassium'})),
    ('木耳', ('黑木耳',), 'vegetable_other', frozenset()),
    ('海带', (), 'vegetable_other', frozenset()),
    ('紫菜', (), 'vegetable_other', frozenset()),
    ('苹果', (), 'fruit', frozenset()),
    ('香蕉', (), 'fruit_high_k', frozenset()),
    ('橙子', ('橙',), 'fruit_high_k', frozenset()),
    ('橘子', ('桔子', '柑橘'), 'fruit_high_k', frozenset()),
    ('柚子', ('蜜柚',), 'fruit_high_k', frozenset({'grapefruit'})),
    ('西柚', ('葡萄柚',), 'fruit_high_k', frozenset({'grapefruit'})),
    ('葡萄', (), 'fruit', frozenset()),
    ('西瓜', (), 'fruit', frozenset()),
    ('梨', ('雪梨',), 'fruit', frozenset()),
    ('桃', ('桃子',), 'fruit', frozenset()),
    ('草莓', (), 'fruit', frozenset()),
    ('猕猴桃', ('奇异果',), 'fruit_high_k', frozenset()),
    ('火龙果', (), 'fruit', frozenset()),
    ('芒果', (), 'fruit', frozenset()),
    ('荔枝', (), 'fruit', frozenset()),
    ('龙眼', ('桂圆',), 'fruit', frozenset()),
    ('红枣', ('枣',), 'fruit', frozenset()),
    ('柿子', (), 'fruit', frozenset()),
    ('核桃', (), 'nut', frozenset()),
    ('花生', ('花生米',), 'nut', frozenset()),
    ('瓜子', (), 'nut', frozenset()),
    ('杏仁', (), 'nut', frozenset()),
    ('腰果', (), 'nut', frozenset()),
    ('芝麻', ('芝麻酱',), 'nut', frozenset({'calcium'})),
    ('咸菜', ('腌菜', '酸菜', '酱菜'), 'high_salt', frozenset()),
    ('榨菜', (), 'high_salt', frozenset()),
    ('腌肉', ('腊肉', '咸肉'), 'high_salt', frozenset({'processed'})),
    ('腊肠', ('香肠',), 'processed_meat', frozenset()),
    ('火腿肠', ('火腿',), 'processed_meat', frozenset()),
    ('咸鱼', (), 'high_salt', frozenset()),
    ('腐乳', ('豆腐乳',), 'high_salt', frozenset()),
    ('豆瓣酱', ('黄酱',), 'high_salt', frozenset()),
    ('酱油', ('生抽', '老抽'), 'high_salt', frozenset({'condiment'})),
    ('蚝油', (), 'high_salt', frozenset({'condiment'})),
    ('味精', (), 'condiment', frozenset()),
    ('鸡精', (), 'condiment', frozenset()),
    ('方便面', ('泡面',), 'high_salt', frozenset({'processed', 'high_fat'})),
    ('油条', (), 'high_fat', frozenset()),
    ('炸鸡', ('油炸食品',), 'high_fat', frozenset()),
    ('薯条', (), 'high_fat', frozenset()),
    ('肥肉', (), 'high_fat', frozenset()),
    ('猪油', ('动物油',), 'high_fat', frozenset()),
    ('奶油', (), 'high_fat', frozenset()),
    ('黄油', (), 'high_fat', frozenset()),
    ('蛋糕', (), 'dessert', frozenset()),
    ('饼干', (), 'dessert', frozenset()),
    ('桃酥', (), 'dessert', frozenset()),
    ('油饼', (), 'high_fat', frozenset()),
    ('麻花', (), 'high_fat', frozenset()),
    ('含糖饮料', ('可乐', '汽水', '甜饮料'), 'high_sugar', frozenset()),
    ('果汁', ('果汁饮料',), 'high_sugar', frozenset()),
    ('蜂蜜', (), 'high_sugar', frozenset()),
    ('糖果', ('糖', '白糖'), 'high_sugar', frozenset({'condiment'})),
    ('冰淇淋', ('雪糕',), 'dessert', frozenset()),
    ('奶茶', (), 'high_sugar', frozenset()),
    ('动物内脏', ('猪腰', '猪心'), 'high_purine', frozenset()),
    ('沙丁鱼', ('小鱼干',), 'high_purine', frozenset({'calcium'})),
    ('浓肉汤', ('肉汤', '老火汤', '骨头汤'), 'high_purine', frozenset()),
    ('火锅汤', ('火锅',), 'high_purine', frozenset()),
    ('啤酒', (), 'alcohol', frozenset({'high_purine'})),
    ('白酒', ('酒', '烧酒'), 'alcohol', frozenset()),
    ('红酒', ('葡萄酒',), 'alcohol', frozenset()),
    ('黄酒', ('料酒',), 'alcohol', frozenset()),
    ('盐', ('食盐', '咸'), 'condiment', frozenset()),
    ('低钠盐', ('低钠',), 'condiment', frozenset({'high_potassium'})),
    ('食用油', ('植物油', '花生油', '菜籽油', '大豆油'), 'condiment', frozenset({'high_fat'})),
    ('橄榄油', (), 'condiment', frozenset()),
    ('醋', (), 'condiment', frozenset()),
    ('浓茶', ('茶', '茶水'), 'beverage', frozenset({'caffeine'})),
    ('咖啡', (), 'beverage', frozenset({'caffeine'})),
    ('剩菜', ('隔夜菜', '剩饭'), 'raw_risk', frozenset()),
    ('生鱼片', ('刺身', '生食'), 'raw_risk', frozenset()),
    ('溏心蛋', ('半熟蛋',), 'raw_risk', frozenset()),
    ('坚果', (), 'nut', frozenset({'texture_hard'})),
    ('糯米', ('糯米制品', '汤圆', '年糕'), 'texture_hard', frozenset({'staple'})),
    ('大块肉', ('大块',), 'texture_hard', frozenset({'protein'})),
)

ALIAS_INDEX: dict[str, str] = {}
for _name, _aliases, _category, _flags in FOODS:
    ALIAS_INDEX[_name] = _name
    for _alias in _aliases:
        ALIAS_INDEX.setdefault(_alias, _name)
ALIAS_ORDER = sorted(ALIAS_INDEX, key=len, reverse=True)

# Words that contain a food alias but are not the food itself (糖尿病 contains 糖, 肝功能 contains 肝).
MASK_WORDS = sorted(('糖尿病', '血糖', '低血糖', '高血糖', '糖耐量', '控糖', '无糖', '低糖',
                     '蛋白质', '肝功能', '脂肪肝', '肝硬化', '肝病', '酒精', '面粉'), key=len, reverse=True)


def _mask(text: str) -> str:
    for word in MASK_WORDS:
        text = text.replace(word, '□' * len(word))
    return text
FOOD_BY_NAME = {name: (aliases, category, flags) for name, aliases, category, flags in FOODS}

PORTION_ITEMS = (
    PortionItem(name='谷类', range_text='200–300 g/日（全谷物和杂豆 50–150 g）', note='粗细搭配，可替换部分白米白面'),
    PortionItem(name='薯类', range_text='50–100 g/日', note='可替代部分主食'),
    PortionItem(name='蔬菜', range_text='300–500 g/日，深色蔬菜占一半', note='牙口差可切碎煮软'),
    PortionItem(name='水果', range_text='200–350 g/日', note='糖尿病分次、随餐或两餐之间'),
    PortionItem(name='畜禽肉', range_text='40–75 g/日', note='优先瘦肉、禽肉'),
    PortionItem(name='鱼虾', range_text='40–75 g/日', note='优先清蒸、炖煮'),
    PortionItem(name='蛋类', range_text='40–50 g/日（约 1 个）', note='高血脂者按医嘱'),
    PortionItem(name='奶及奶制品', range_text='300–500 g/日', note='乳糖不耐受选酸奶或低乳糖奶'),
    PortionItem(name='大豆与坚果', range_text='大豆 15 g、坚果 10 g/日', note='肾病者需医生评估'),
    PortionItem(name='烹调油与盐', range_text='油 25–30 g、盐 <5 g/日', note='高血压重点，少用腌制品与酱油'),
    PortionItem(name='饮水', range_text='1500–1700 ml/日', note='心衰、肾病限水者按医嘱'),
)
PORTION_DISCLAIMER = ('以上份量为一般参考区间，来自膳食指南的公开推荐；需要按体重、病情、咀嚼与吞咽能力调整，'
                      '不是疾病治疗饮食处方。')


def normalize(text: str) -> str:
    return unicodedata.normalize('NFKC', text or '')


def _flags(category: str, extra: frozenset[str]) -> frozenset[str]:
    return CATEGORY_INFO[category][1] | extra


def label_for(category: str, flags: frozenset[str]) -> str:
    base, implied = CATEGORY_INFO[category]
    hints = [FLAG_LABELS[flag] for flag in ('high_salt', 'high_purine', 'high_sugar', 'high_fat', 'processed')
             if flag in flags and flag not in implied]
    return base + ('（' + '、'.join(hints) + '）' if hints else '')


def mention(canonical: str, *, source: str = 'parsed') -> FoodMention:
    _, category, extra = FOOD_BY_NAME[canonical]
    flags = _flags(category, extra)
    return FoodMention(name=canonical, canonical=canonical, categories=[category],
                       flags=sorted(flags), label=label_for(category, flags), source=source)


def extract(text: str, provided: list[FoodInput]) -> tuple[list[FoodMention], list[str]]:
    text = _mask(normalize(text))
    found: dict[str, int] = {}
    consumed: list[tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(start < other_end and other_start < end for other_start, other_end in consumed)

    # Longest alias first, never counting an alias nested inside a longer one
    # (咸鸭蛋 is not plain duck egg; 低钠盐 is not plain salt).
    for alias in ALIAS_ORDER:
        position = text.find(alias)
        while position >= 0 and overlaps(position, position + len(alias)):
            position = text.find(alias, position + 1)
        if position < 0: continue
        consumed.append((position, position + len(alias)))
        canonical = ALIAS_INDEX[alias]
        if canonical not in found or position < found[canonical]:
            found[canonical] = position
    mentions = [mention(name) for name in sorted(found, key=found.get)]
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
        if any(existing.canonical == canonical for existing in mentions): continue
        mentions.append(mention(canonical, source='provided'))
    return mentions, unknown


def flags_of(foods: list[FoodMention]) -> set[str]:
    tags: set[str] = set()
    for food in foods: tags.update(food.flags)
    return tags


def portion_reference() -> PortionReference:
    return PortionReference(table_version=TABLE_VERSION, items=list(PORTION_ITEMS), disclaimer=PORTION_DISCLAIMER)


def bmi(weight_kg: float | None, height_cm: float | None) -> float | None:
    if not weight_kg or not height_cm: return None
    meters = height_cm / 100
    return round(weight_kg / (meters * meters), 1)


def bmi_label(value: float | None) -> str:
    if value is None: return ''
    if value < 18.5: return '低体重'
    if value < 24: return '正常范围'
    if value < 28: return '超重'
    return '肥胖'


def find_in_text(text: str, name: str) -> bool:
    return normalize(name) in normalize(text)
