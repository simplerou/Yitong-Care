"""Editorial concept help and finite gap labels, separate from cited local policy facts."""
GAPS = {
    'local_service_catalog':'当地长期护理保险服务目录或具体支付项目',
    'payment_rates':'当地待遇标准、支付比例或限额',
    'eligibility':'当地参保及待遇享受条件',
    'application_process':'当地办理流程与材料',
    'current_validity':'文件截至今日的有效状态',
    'full_policy_scope':'问题涉及的完整政策范围',
}


def requested_gaps(text):
    gaps=[]
    if any(word in text for word in ('服务项目','服务目录','护理目录','服务内容')): gaps.append('local_service_catalog')
    if any(word in text for word in ('待遇标准','支付比例','报销比例','限额','金额','多少钱')): gaps.append('payment_rates')
    if any(word in text for word in ('申请条件','参保条件','能申请','能领','资格')): gaps.append('eligibility')
    if any(word in text for word in ('办理流程','申请流程','材料')): gaps.append('application_process')
    if any(word in text for word in ('最新','现行','有效','废止')): gaps.append('current_validity')
    return gaps or ['full_policy_scope']


def gap_message(gaps, partial=False):
    labels='、'.join(GAPS[key] for key in dict.fromkeys(gaps) if key in GAPS)
    return ('本次仅回答已有原文支持的部分；' if partial else '')+'本次取得的资料尚不足以核实'+(labels or '所问结论')+'。这表示当前依据不足，不代表相关政策或待遇不存在。'


def concept_help(text):
    if any(term in text for term in ('长期护理保险','长护险')) and any(term in text for term in ('服务项目','服务目录','护理目录','服务内容')):
        return [
            '生活照护是日常起居等方面的照料；医疗护理是与健康状况相关的护理。这里仅解释概念，不列举当地可支付项目。',
            '护理服务目录用于明确具体制度纳入哪些项目及其要求；某项服务是否纳入、可在哪种场景提供、能否支付及支付多少，须核对当地目录和待遇规则。',
        ]
    return []
