from app.schemas.diet import DietProfile, FoodInput
from app.services.diet import foods


def test_longest_alias_wins_and_nested_names_do_not_leak():
    assert [item.name for item in foods.extract('咸鸭蛋配粥', [])[0]] == ['咸鸭蛋', '白粥']
    assert [item.name for item in foods.extract('低钠盐少放点', [])[0]] == ['低钠盐']
    assert [item.name for item in foods.extract('白米饭', [])[0]] == ['白米饭']


def test_context_words_are_not_mistaken_for_food():
    assert [item.name for item in foods.extract('糖尿病能吃香蕉吗', [])[0]] == ['香蕉']
    assert [item.name for item in foods.extract('血糖高能吃西瓜吗', [])[0]] == ['西瓜']
    assert [item.name for item in foods.extract('肝功能不好能吃鸡蛋吗', [])[0]] == ['鸡蛋']
    assert foods.extract('蛋白质怎么补', [])[0] == []


def test_tags_and_labels():
    foods_map = {item.name: item for item in foods.extract('咸菜、菠菜、香蕉、牛奶、豆腐', [])[0]}
    assert 'high_salt' in foods_map['咸菜'].flags
    assert 'vitamin_k' in foods_map['菠菜'].flags and 'high_potassium' in foods_map['菠菜'].flags
    assert 'calcium' in foods_map['牛奶'].flags
    assert 'protein' in foods_map['豆腐'].flags
    assert '高盐' in foods_map['咸菜'].label
    assert '含钾较高' not in foods_map['香蕉'].label


def test_unknown_foods_are_reported_without_guessing():
    mentions, unknown = foods.extract('这个菜能吃吗', [FoodInput(name='外婆菜')])
    assert mentions == [] and unknown == ['外婆菜']


def test_portion_reference_has_ranges_and_disclaimer():
    reference = foods.portion_reference()
    assert reference.table_version == foods.TABLE_VERSION
    names = [item.name for item in reference.items]
    assert '谷类' in names and '烹调油与盐' in names and '饮水' in names
    assert '不是疾病治疗饮食处方' in reference.disclaimer


def test_bmi_and_label():
    value = foods.bmi(52, 160)
    assert value == 20.3 and foods.bmi_label(value) == '正常范围'
    assert foods.bmi_label(foods.bmi(40, 165)) == '低体重'
    assert foods.bmi_label(foods.bmi(90, 165)) == '肥胖'
    assert foods.bmi(None, 165) is None


def test_provided_foods_are_merged_without_duplicates():
    mentions, unknown = foods.extract('早餐喝了豆浆', [FoodInput(name='豆浆'), FoodInput(name='燕麦')])
    assert [item.name for item in mentions] == ['豆浆', '燕麦']
    assert unknown == []
