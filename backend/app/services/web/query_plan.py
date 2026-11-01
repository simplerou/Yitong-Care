"""Focused official queries and bounded city fallback; never infer eligibility."""
import re


def requested_aspects(query):
    aspects=[]
    if re.search(r'服务项目|服务目录|护理目录|服务内容|护理项目',query): aspects.append('services')
    if re.search(r'待遇标准|支付比例|报销比例|限额|支付标准',query): aspects.append('payment')
    return aspects


def focus_terms(query):
    terms=[]
    aspects=requested_aspects(query)
    if 'services' in aspects: terms+=['护理服务目录','护理服务项目','服务项目','服务目录','生活照护','医疗护理','居家护理','机构护理','护理服务清单','生活护理','基础护理']
    if 'payment' in aspects: terms+=['待遇标准','支付标准','支付比例','支付限额','报销比例']
    return terms


def focused_query(original, dialogue, freshness=False):
    if dialogue.benefit!='长期护理保险' or not requested_aspects(original+' '+dialogue.aspect): return original
    region=dialogue.region+dialogue.district
    document=re.search(r'[\u4e00-\u9fff]{1,10}[〔\[]20\d{2}[〕\]]\d+号',original)
    words=[region,'长期护理保险']
    aspects=requested_aspects(original+' '+dialogue.aspect)
    if 'services' in aspects: words+=['护理服务目录','服务项目']
    if 'payment' in aspects: words+=['待遇标准','支付比例']
    if document: words.append(document[0])
    if freshness: words.append('最新政策')
    return ' '.join(word for word in words if word)[:1000]


def relevant_service_text(content):
    """Tie a service statement to the same scheme clause, not another numbered duty."""
    service_terms=r'护理服务(?:清单|目录|项目)|服务目录|服务项目|护理项目|生活照护|生活照料|生活护理|基础护理|医疗护理|居家护理|机构护理'
    for scheme in re.finditer(r'长期护理保险|长护险',content):
        before=content[max(0,scheme.start()-160):scheme.start()]
        start=scheme.start()-len(re.split(r'[。；;\n]',before)[-1])
        tail=content[scheme.end():scheme.end()+420]
        end=re.search(r'[。；;\n]',tail)
        first=tail[:end.start()] if end else tail
        window=content[start:scheme.end()]+first
        if end:
            following=tail[end.end():].lstrip()
            # A direct continuation is allowed, but a new numbered duty is not.
            if re.match(r'(?:其中|具体)?(?:服务项目|护理服务|居家护理|机构护理|生活照护|医疗护理|支付范围|服务目录)',following):
                window+='。'+re.split(r'[。；;\n]',following,maxsplit=1)[0]
        for service in re.finditer(service_terms,window):
            suffix=window[service.end():service.end()+12]
            local=window[max(0,service.start()-65):service.end()+65]
            if re.match(r'(?:员|人员|职业|专业|人才)',suffix): continue
            if re.search(r'培训|人才|从业人员|职业技能|招生|持证',local) and not re.search(r'支付范围|待遇范围|服务项目|服务目录|护理服务清单',local): continue
            if re.search(r'目录|清单|项目',service[0]): return True
            if re.search(r'包括|包含|提供|支付|享受|分为|涵盖|纳入|照护服务|护理服务',local): return True
    return False


def source_priority(query,title,content='',url=''):
    score=0
    if re.search(r'长期护理保险|长护险',title): score+=30
    if any(word in title for word in focus_terms(query)): score+=25
    if relevant_service_text(content) and 'services' in requested_aspects(query): score+=30
    if re.search(r'预算执行|政府工作报告|财政预算|经济社会发展',title): score-=25
    if 'ybj.' in url: score+=3
    return score


def fallback_queries(query):
    """At most two city/department variants; never broaden an explicit numbered file."""
    if not re.search(r'长期护理保险|长护险',query) or not requested_aspects(query): return []
    if re.search(r'[〔\[]20\d{2}[〕\]]\s*\d+号',query): return []
    import jieba
    cities=[token for token in jieba.cut(query,HMM=False) if len(token)>2 and token.endswith('市')]
    if not cities: return []
    city=cities[-1]
    suffix=' 最新政策' if re.search(r'最新|现行|当前|有效|20\d{2}',query) else ''
    if 'services' in requested_aspects(query):
        variants=[city+' 医疗保障局 长期护理保险 护理服务项目',city+' 长护险 护理服务清单 护理服务目录']
    else:
        variants=[city+' 医疗保障局 长期护理保险 待遇标准 支付比例',city+' 长护险 待遇支付标准 实施办法']
    return list(dict.fromkeys(value+suffix for value in variants if value+suffix!=query))[:2]
