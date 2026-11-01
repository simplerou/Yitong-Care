import json
import httpx
import pytest
from pydantic import SecretStr
from app.core.config import Settings
from app.services.web.tavily import TavilySearch,WebSearchError
from app.services.web.cache import SearchCache
from app.services.web.query_plan import fallback_queries
from app.services.chat.policy_checks import relevance_reason

QUERY='温州市龙湾区 长期护理保险 护理服务目录 服务项目'
BUDGET='温州市财政报告：推进长期护理保险制度建设，加强资金保障。'
CATALOG='温州市长期护理保险护理服务目录：护理服务项目包括生活照护和医疗护理，具体支付条件按文件规定执行。'


def client(monkeypatch,handler,**settings):
 monkeypatch.setattr('app.services.web.cache.search_cache',SearchCache())
 original=httpx.Client
 monkeypatch.setattr('app.services.web.tavily.httpx.Client',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
 return TavilySearch(Settings(_env_file=None,tavily_api_key=SecretStr('unit-test'),**settings))


def test_city_fallback_retrieves_new_catalog_deduplicates_and_tags_scope(monkeypatch):
 calls=[];queries=[]
 def handler(request):
  data=json.loads(request.content);calls.append((request.url.path,data))
  if request.url.path=='/search':
   queries.append(data['query'])
   items=[{'title':'温州市财政报告','url':'https://wenzhou.gov.cn/report'}]
   if len(queries)>1: items.append({'title':'温州市长期护理保险护理服务目录','url':'https://wenzhou.gov.cn/catalog'})
   return httpx.Response(200,json={'results':items})
  if len(queries)==1: return httpx.Response(200,json={'results':[{'url':'https://wenzhou.gov.cn/report','raw_content':BUDGET}]})
  assert data['urls']==['https://wenzhou.gov.cn/catalog']
  return httpx.Response(200,json={'results':[{'url':'https://wenzhou.gov.cn/catalog','raw_content':CATALOG}]})
 report=client(monkeypatch,handler).search_with_diagnostics(QUERY)
 assert len(queries)==2 and '龙湾区' in queries[0] and '龙湾区' not in queries[1] and '医疗保障局' in queries[1]
 assert len(report.sources)==1 and report.sources[0].search_scope=='city_fallback'
 assert report.sources[0].search_query==queries[1]
 d=report.diagnostics
 assert len(d.attempts)==2 and d.search_count==3 and d.extraction_requested==2 and d.accepted_count==1
 assert d.rejected_counts=={'service_catalog_missing':1,'duplicate_previous_url':1}
 assert d.attempts[0].rejected_counts=={'service_catalog_missing':1} and d.attempts[0].accepted_count==0


def test_all_rounds_fail_stops_at_three_searches(monkeypatch):
 searches=[];extracts=[]
 def handler(request):
  data=json.loads(request.content)
  if request.url.path=='/search':
   searches.append(data['query']);return httpx.Response(200,json={'results':[{'title':'温州市财政报告','url':f'https://wenzhou.gov.cn/report{len(searches)}'}]})
  extracts.append(data['urls'])
  return httpx.Response(200,json={'results':[{'url':data['urls'][0],'raw_content':BUDGET}]})
 report=client(monkeypatch,handler).search_with_diagnostics(QUERY)
 assert not report.sources and len(searches)==3 and len(extracts)==3 and len(report.diagnostics.attempts)==3
 assert report.diagnostics.rejected_counts['service_catalog_missing']==3


def test_success_first_round_never_adds_searches(monkeypatch):
 paths=[]
 def handler(request):
  paths.append(request.url.path)
  if request.url.path=='/search': return httpx.Response(200,json={'results':[{'title':'温州市长护险服务目录','url':'https://wenzhou.gov.cn/catalog'}]})
  return httpx.Response(200,json={'results':[{'url':'https://wenzhou.gov.cn/catalog','raw_content':CATALOG}]})
 report=client(monkeypatch,handler).search_with_diagnostics(QUERY)
 assert paths==['/search','/extract'] and report.sources[0].search_scope=='requested' and len(report.diagnostics.attempts)==1


def test_budget_zero_disables_fallback(monkeypatch):
 searches=[]
 def handler(request):
  searches.append(request.url.path);return httpx.Response(200,json={'results':[]})
 report=client(monkeypatch,handler,tavily_fallback_searches=0).search_with_diagnostics(QUERY)
 assert searches==['/search'] and not report.sources


def test_fallback_timeout_stops_further_requests_and_keeps_prior_diagnostics(monkeypatch):
 searches=[]
 def handler(request):
  if request.url.path=='/search':
   searches.append(json.loads(request.content)['query'])
   if len(searches)>1: raise httpx.ReadTimeout('unit timeout',request=request)
   return httpx.Response(200,json={'results':[]})
 with pytest.raises(WebSearchError) as error: client(monkeypatch,handler).search_with_diagnostics(QUERY)
 assert len(searches)==2 and len(error.value.diagnostics.attempts)==2
 assert error.value.diagnostics.attempts[-1].stage=='search'


def test_fallback_stays_in_requested_city_and_respects_explicit_file():
 variants=fallback_queries('宁波市某区 长期护理保险 服务项目 最新政策')
 assert len(variants)==2 and all('宁波市' in q and '最新' in q for q in variants)
 assert not fallback_queries('温州市杭民发〔2024〕142号 长期护理保险 服务项目')
 assert not fallback_queries('长期护理保险 服务项目')
 assert not fallback_queries('温州市 高龄津贴')


def test_aliases_and_service_list_wording_are_equivalent_not_general_construction():
 assert relevance_reason('温州市 长护险 护理服务目录','温州市医保局',CATALOG) is None
 assert relevance_reason(QUERY,'温州市医保局','温州市长护险护理服务清单：提供生活护理和基础护理项目。') is None
 assert relevance_reason(QUERY,'温州市财政报告',BUDGET)=='service_catalog_missing'


def test_repeated_report_is_not_extracted_again_in_fallbacks(monkeypatch):
 paths=[]
 def handler(request):
  paths.append(request.url.path)
  if request.url.path=='/search': return httpx.Response(200,json={'results':[{'title':'温州市财政报告','url':'https://wenzhou.gov.cn/same'}]})
  return httpx.Response(200,json={'results':[{'url':'https://wenzhou.gov.cn/same','raw_content':BUDGET}]})
 report=client(monkeypatch,handler).search_with_diagnostics(QUERY)
 assert not report.sources and paths.count('/search')==3 and paths.count('/extract')==1
 assert report.diagnostics.rejected_counts['duplicate_previous_url']==2


def test_real_basic_elderly_services_and_nurse_training_are_not_longcare_catalog():
 from pathlib import Path
 from app.services.web.query_plan import relevant_service_text
 fixture=json.loads((Path(__file__).parents[1]/'fixtures/policy_longcare_training_false_positive.json').read_text())
 assert not relevant_service_text(fixture['content'])
 assert relevance_reason(fixture['query'],fixture['title'],fixture['content'],fixture['url'])=='service_catalog_missing'


def test_real_false_positive_triggers_city_fallback_instead_of_stopping(monkeypatch):
 from pathlib import Path
 fixture=json.loads((Path(__file__).parents[1]/'fixtures/policy_longcare_training_false_positive.json').read_text())
 queries=[]
 def handler(request):
  data=json.loads(request.content)
  if request.url.path=='/search':
   queries.append(data['query'])
   meta={'title':fixture['title'],'url':fixture['url']} if len(queries)==1 else {'title':'温州市医保局长期护理保险服务目录','url':'https://wenzhou.gov.cn/catalog'}
   return httpx.Response(200,json={'results':[meta]})
  url=data['urls'][0]
  return httpx.Response(200,json={'results':[{'url':url,'raw_content':fixture['content'] if url==fixture['url'] else CATALOG}]})
 report=client(monkeypatch,handler).search_with_diagnostics(fixture['query'])
 assert len(queries)==2 and report.sources[0].search_scope=='city_fallback'
 assert report.diagnostics.attempts[0].accepted_count==0
 assert report.sources[0].url=='https://wenzhou.gov.cn/catalog'


def test_actual_service_categories_remain_usable_not_training():
 from app.services.web.query_plan import relevant_service_text
 assert relevant_service_text('温州市长期护理保险规定，居家护理服务包括生活照护和医疗护理，具体按目录支付。')
 assert not relevant_service_text('温州市长期护理保险制度试点提质扩面。加强人才队伍保障，开展医疗护理人员职业技能培训。')


def test_real_medical_bureau_duties_are_not_longcare_service_items():
 from pathlib import Path
 from app.services.web.query_plan import relevant_service_text
 fixture=json.loads((Path(__file__).parents[1]/'fixtures/policy_longcare_budget_false_positive.json').read_text())
 assert not relevant_service_text(fixture['content'])
 assert relevance_reason(fixture['query'],fixture['title'],fixture['content'],fixture['url'])=='service_catalog_missing'


def test_new_numbered_medical_insurance_duty_cannot_supply_service_relation():
 from app.services.web.query_plan import relevant_service_text
 assert not relevant_service_text('2.组织拟订并实施长期护理保险制度改革方案。3.管理基金。4.组织实施药品、医用耗材、医疗服务项目、医保目录等政策。')
 assert relevant_service_text('温州市长期护理保险服务规定。居家护理服务包括生活照护和医疗护理。')
