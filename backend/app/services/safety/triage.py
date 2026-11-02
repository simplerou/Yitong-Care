"""Deterministic safety triage: post-fall rules first, then home risk level."""
from app.schemas.safety import SafetyAssessment, SafetyProfile, SafetyTriage
from app.services.safety import hazards, postfall

LABELS = {
    'altered_consciousness': '跌倒后意识改变', 'breathing_difficulty': '跌倒后呼吸困难',
    'head_injury': '头部撞击后呕吐或嗜睡', 'anticoagulant_head_strike': '抗凝药使用者头部撞击',
    'hip_fracture': '疑似髋部骨折', 'spine_injury': '腰背或颈部受伤可能', 'heavy_bleeding': '大量出血',
    'suspected_fracture': '疑似骨折', 'alone_cannot_rise': '独居且无法起身',
    'long_lie': '倒地时间较长', 'syncope_fall': '头晕或晕厥导致跌倒', 'recurrent_falls': '反复跌倒',
    'minor_fall': '跌倒后暂无警示症状',
}


def triage(text: str, assessment: SafetyAssessment, profile: SafetyProfile) -> SafetyTriage:
    findings = assessment.post_fall or postfall.assess_post_fall(text, profile)
    post_level = postfall.level_of(findings) if findings else 'L4'
    risk = assessment.risk_level
    if post_level == 'L1': level = 'L1'
    elif post_level == 'L2': level = 'L2'
    elif risk == 'high': level = 'L2'
    elif risk == 'medium' or post_level == 'L3': level = 'L3'
    else: level = 'L4'
    rules = [item.id for item in findings if item.severity in {'high', 'moderate'}]
    if not rules and risk == 'high': rules = ['high_fall_risk']
    elif not rules and risk == 'medium': rules = ['moderate_fall_risk']
    elif not rules and findings: rules = [findings[0].id]
    actions = {'L1': 'call_120', 'L2': 'safety_referral', 'L3': 'safety_referral', 'L4': 'self_care'}
    red_flags = [LABELS.get(rule, '跌倒风险较高' if 'risk' in rule else rule) for rule in rules]
    return SafetyTriage(level=level, rule_ids=rules, required_action=actions[level],
                        red_flags=red_flags, table_version=hazards.TABLE_VERSION)
