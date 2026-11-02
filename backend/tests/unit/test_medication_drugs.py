from app.schemas.medication import MedicationItem, MedicationProfile
from app.services.medication import drugs


def assess(question, provided=None, profile=None):
    return drugs.assess(question, provided or [], profile or MedicationProfile())


def ids(assessment):
    return [finding.id for finding in assessment.interactions]


def test_extraction_prefers_the_longer_alias():
    assessment = assess('泰诺林和感冒灵能一起吃吗')
    names = [drug.name for drug in assessment.drugs]
    assert '对乙酰氨基酚' in names and '复方感冒药' in names
    assert '复方感冒药' not in [drug.name for drug in assess('只吃了泰诺林').drugs]


def test_aliases_and_brand_names_map_to_generic_names():
    assert [drug.name for drug in assess('络活喜和代文一起吃').drugs] == ['氨氯地平', '缬沙坦']
    assert [drug.name for drug in assess('优甲乐什么时候吃').drugs] == ['左甲状腺素']


def test_unknown_drugs_are_reported_not_guessed():
    assessment = assess('这个新药能和华法林一起吃吗', [MedicationItem(name='某某新药')])
    assert assessment.unknown_names == ['某某新药']
    assert [drug.name for drug in assessment.drugs] == ['华法林']


def test_high_risk_interactions_are_detected():
    assert 'anticoagulant_antiplatelet' in ids(assess('华法林和阿司匹林'))
    assert 'anticoagulant_nsaid' in ids(assess('华法林加布洛芬'))
    assert 'antiplatelet_nsaid' in ids(assess('阿司匹林和布洛芬'))
    assert 'acei_arb_potassium_sparing' in ids(assess('缬沙坦和螺内酯'))
    assert 'nitrate_pde5' in ids(assess('硝酸甘油和西地那非'))
    assert 'statin_macrolide' in ids(assess('阿托伐他汀和克拉霉素'))
    assert 'duplicate_acetaminophen' in ids(assess('对乙酰氨基酚加复方感冒药'))


def test_triple_whammy_requires_a_diuretic():
    assert 'triple_whammy' not in ids(assess('缬沙坦和布洛芬'))
    assert 'triple_whammy' in ids(assess('缬沙坦、氢氯噻嗪和布洛芬'))


def test_warfarin_herbal_and_vitamin_k_findings():
    assert 'warfarin_herbal' in ids(assess('华法林和银杏叶'))
    assert 'warfarin_vitamin_k' in ids(assess('华法林和维生素K'))


def test_single_drug_never_triggers_a_pair_rule():
    assessment = assess('阿司匹林怎么吃')
    assert assessment.interactions == []


def test_multiple_antihypertensives_note_requires_three_drugs():
    two = assess('氨氯地平和缬沙坦')
    three = assess('氨氯地平、缬沙坦和美托洛尔')
    assert 'multiple_antihypertensives' not in ids(two)
    assert 'multiple_antihypertensives' in ids(three)


def test_older_adult_and_condition_cautions():
    older = assess('阿普唑仑', profile=MedicationProfile(age=80))
    assert any(finding.id.startswith('older_adult_') for finding in older.interactions)
    ulcer = assess('布洛芬', profile=MedicationProfile(conditions=['peptic_ulcer']))
    assert 'condition_peptic_ulcer' in ids(ulcer)
    asthma = assess('美托洛尔', profile=MedicationProfile(conditions=['asthma']))
    assert 'condition_asthma' in ids(asthma)


def test_frequency_parsing():
    assert drugs.parse_frequency('每天两次') == 'twice_daily'
    assert drugs.parse_frequency('一天三次，饭后吃') == 'three_daily'
    assert drugs.parse_frequency('每天早上一次') == 'once_daily'
    assert drugs.parse_frequency('每周一次') == 'weekly'
    assert drugs.parse_frequency('必要时服用') == 'as_needed'
    assert drugs.parse_frequency('怎么吃') == 'unknown'


def test_missed_dose_advice_distinguishes_special_drugs():
    generic = drugs.missed_dose_advice(assess('二甲双胍每天两次，忘了吃'))
    assert '不要一次吃双倍剂量' in generic
    special = drugs.missed_dose_advice(assess('华法林忘了吃'))
    assert '不要自行补服' in special and '医生或药师' in special


def test_triage_levels_for_allergic_and_bleeding_events():
    severe = assess('吃了阿莫西林后起疹子，喘不上气')
    assert drugs.triage(severe, '吃了阿莫西林后起疹子，喘不上气').level == 'L1'
    bleeding = assess('吃阿司匹林后黑便')
    result = drugs.triage(bleeding, '吃阿司匹林后黑便')
    assert result.level == 'L1' and 'gi_bleeding' in result.rule_ids
    minor = assess('吃阿司匹林后刷牙牙龈出血')
    assert drugs.triage(minor, '吃阿司匹林后刷牙牙龈出血').level == 'L3'


def test_triage_hypoglycemia_and_rhabdomyolysis():
    hypo = assess('打胰岛素后出冷汗心慌')
    assert drugs.triage(hypo, '打胰岛素后出冷汗心慌').level == 'L2'
    severe_hypo = assess('打胰岛素后出冷汗，人叫不醒')
    assert drugs.triage(severe_hypo, '打胰岛素后出冷汗，人叫不醒').level == 'L1'
    muscle = assess('吃阿托伐他汀后肌肉酸痛，尿色深')
    assert drugs.triage(muscle, '吃阿托伐他汀后肌肉酸痛，尿色深').level == 'L2'


def test_negated_symptoms_do_not_trigger():
    assessment = assess('吃阿司匹林，没有黑便，也没有皮疹')
    assert drugs.triage(assessment, '吃阿司匹林，没有黑便，也没有皮疹').level == 'L4'


def test_interaction_alone_prompts_pharmacist_review():
    assessment = assess('华法林和阿司匹林')
    result = drugs.triage(assessment, '华法林和阿司匹林')
    assert result.level == 'L3' and 'interaction_needs_review' in result.rule_ids
