"""Conservative relevance and temporal-claim checks, not a legal validity verifier."""
import re
from html import unescape
import jieba
from urllib.parse import urlsplit


def clean_title(text: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', unescape(text))).strip()


STOP = {'的','是','了','有哪些','什么','怎么样','如何','怎么','最新','政策','现行','有效','目前','现在','是否','申请','规定','办法','通知','标准','杭州市','杭州'}
TOPICS = ('高龄','津贴','养老','补贴','长护险','长期护理','适老化','助餐','失能','困难老年人')


def relevance_reason(query: str, title: str, content: str, url: str = '') -> str | None:
    # Require an actual topic in the body; a title/snippet alone is not evidence.
    requested = [word for word in TOPICS if word in query]
    body = content.lower()
    text = (title + ' ' + content).lower()
    regions = [w for w in jieba.cut(query,HMM=False) if len(w)>2 and w.endswith(('市','省','自治区'))]
    cities = [w for w in regions if w.endswith('市')]
    regions = cities or regions
    host = (urlsplit(url).hostname or '').lower()
    hangzhou_origin = host == 'hangzhou.gov.cn' or host.endswith('.hangzhou.gov.cn')
    if '杭州' in query and '杭州' not in text and not hangzhou_origin: return 'region_mismatch'
    if regions and not any(region in text or region.rstrip('市省') in text or ('杭州' in region and hangzhou_origin) for region in regions):
        return 'region_mismatch'
    for benefit in ('津贴','补贴'):
        if benefit in query and not any(alias in body for alias in ('津贴','补贴','补助')): return 'benefit_missing'
    if '养老' in query and '补贴' in query:
        if not re.search(r'(?:养老|老年|高龄).{0,160}(?:补贴|津贴|补助)|(?:补贴|津贴|补助).{0,160}(?:养老|老年|高龄)',body,re.S): return 'topic_not_coincident'
    specific = [w for w in requested if w not in {'养老','补贴','津贴'}]
    if specific and not any(word in body for word in specific): return 'specific_topic_missing'
    if requested and not any(word in body for word in requested): return 'topic_missing'
    terms = {w for w in jieba.cut(query, HMM=False) if len(w)>1 and w not in STOP and re.search(r'[\u4e00-\u9fffa-zA-Z]',w)}
    return None if requested or any(word in body for word in terms) else 'topic_missing'


def relevance(query: str, title: str, content: str, url: str = '') -> bool:
    return relevance_reason(query, title, content, url) is None


def unsupported_validity_claim(text: str) -> bool:
    # No authoritative policy-validity metadata exists yet: do not certify present validity.
    if re.search(r'最新统一调整|标准系最新|属于最新(?:的)?调整',text): return True
    for sentence in re.split(r'[。！？；\n]', text):
        if re.search(r'(?:未发现|未检索到|未搜到|未找到|无证据).{0,50}(?:废止|更新|调整)',sentence) and re.search(r'因此|所以|故|有效|为准',text):
            return True
        if re.search(r'无法确认|不能确认|尚不能确认|无法判断|不能判断|不代表|不等于|尚未核实|有待核实|待核实',sentence) and not re.search(r'但是|但仍|因此仍|所以仍',sentence):
            continue
        if re.search(r'(?:现行[^。！？；\n]{0,18}(?:补贴|津贴|标准|适用效力)|现行有效|仍(?:然|为)?有效|目前.{0,8}有效|当前.{0,8}有效|(?:当前|目前)[^。！？；\n]{0,10}(?:执行依据|执行标准)|截至.{0,15}有效|最新[^。！？；\n]{0,18}(?:政策|规定|标准)|未被废止|未被更新|尚未废止)',sentence):
            return True
    return False
