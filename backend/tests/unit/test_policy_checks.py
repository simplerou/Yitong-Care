import pytest
from app.services.chat.policy_checks import relevance, unsupported_validity_claim, clean_title


def test_unrelated_economic_policy_does_not_pass():
    assert not relevance('杭州市最新高龄津贴政策','杭州市推动经济高质量发展若干政策','促进工业发展，扶持企业，给予企业补贴。')
    assert not relevance('杭州市养老补贴','杭州市经济政策','养老产业发展。'+'经济发展。'*100+'企业补贴政策。')
    assert not relevance('杭州市高龄津贴政策','外地政策','南京市高龄老年人津贴标准。')
    assert relevance('杭州市高龄津贴政策','杭州市补贴通知','本市高龄老年人津贴按年龄分档发放。')
    assert relevance('浙江省杭州市养老补贴','杭州市补贴通知','本市高龄老年人补贴按年龄发放。')


def test_html_in_search_title_is_plain_text():
    assert clean_title('推动经济<br>高质量发展 &amp; 政策')=='推动经济 高质量发展 & 政策'


@pytest.mark.parametrize('text',[
 '目前仍为有效文件，故以此为准。',
 '杭州市现行有效的高龄津贴政策依据为该通知。',
 '未搜到废止文件，所以仍然有效。',
 '因无证据显示被更新，故以该政策为准。',
 '这是最新政策。',
])
def test_present_validity_claims_are_blocked(text):
    assert unsupported_validity_claim(text)


@pytest.mark.parametrize('text',[
 '根据2024年通知，申请对象为80周岁以上老人。',
 '文件原文规定自2025年1月1日起施行。',
 '尚不能确认该文件是否现行有效。',
 '搜索到官方文件不代表政策仍然有效。',
])
def test_historical_terms_and_uncertainty_are_allowed(text):
    assert not unsupported_validity_claim(text)


def test_benefit_aliases_and_official_origin_do_not_false_reject():
    assert relevance('杭州市最新高龄津贴政策','关于健全补贴制度的通知','本市高龄老年人补贴按年龄分档发放。','https://mz.hangzhou.gov.cn/policy')
    assert relevance('杭州市养老补贴','杭州市补助通知','本市老年人可申请养老服务补助。')
    assert not relevance('杭州市高龄津贴','南京市高龄补贴','本市高龄老年人补贴。','https://nanjing.gov.cn/policy')
    assert not relevance('杭州市高龄津贴','补贴通知','企业员工高龄人才奖励补贴。','https://evilhangzhou.gov.cn/policy')


def test_latest_adjustment_claim_cannot_hide_behind_uncertainty_suffix():
    assert unsupported_validity_claim('表明该标准系最新统一调整。但无法确认截至今日该文件是否已被后续文件废止。')


def test_latest_policy_with_topic_modifiers_is_still_a_claim():
    assert unsupported_validity_claim('杭州市最新高龄津贴政策依据该文件。')
    assert unsupported_validity_claim('表明该文件为当前执行依据。')
    assert not unsupported_validity_claim('尚不能确认其是否为最新高龄津贴政策。')


def test_actual_web_answers_with_unverified_current_wording_are_not_passes():
    import json
    from pathlib import Path
    fixture=json.loads((Path(__file__).parents[1]/'fixtures/policy_current_wording.json').read_text())
    assert all(unsupported_validity_claim(case['answer']) for case in fixture)
    assert not unsupported_validity_claim('不能确认现行高龄补贴标准，以下仅解释文件原文。')
