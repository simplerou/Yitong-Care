import json
import httpx
from app.schemas.policy import DialogueState
from app.core.config import Settings
from pydantic import SecretStr
from app.services.web.query_plan import focused_query,source_priority
from app.services.web.tavily import TavilySearch
from app.services.chat.policy_checks import relevance_reason


def test_search_query_focuses_catalog_without_personal_age_or_wrong_amount():
 state=DialogueState(region='温州市',district='龙湾区',benefit='长期护理保险',aspect='服务项目',age=22)
 query=focused_query('温州市龙湾区长期护理保险服务项目，用户22岁',state)
 assert '温州市龙湾区' in query and '护理服务目录' in query and '服务项目' in query and '22' not in query
 assert focused_query('杭民发〔2024〕142号补贴标准',DialogueState())=='杭民发〔2024〕142号补贴标准'


def test_excerpt_prioritizes_catalog_after_long_irrelevant_report():
 content=('温州市长期护理保险工作统计与制度建设。'*500)+'\n长期护理保险护理服务目录：居家护理服务项目包括生活照护、医疗护理，按具体目录执行。'+'政策附件说明。'*100
 excerpt=TavilySearch.excerpt('温州市长期护理保险护理服务目录 服务项目',content)
 assert '护理服务目录' in excerpt and '生活照护' in excerpt and excerpt in content and len(excerpt)<=4000


def test_specific_service_search_rejects_budget_mention_but_accepts_item_clauses():
 query='温州市长期护理保险护理服务目录 服务项目'
 irrelevant='温州市财政预算报告：推进长期护理保险制度建设，保障工作经费，完善养老体系。'
 relevant='温州市长期护理保险护理服务目录：服务项目包括生活照护和医疗护理，具体目录附后。'
 assert relevance_reason(query,'温州市财政报告',irrelevant)=='service_catalog_missing'
 assert relevance_reason(query,'温州市护理服务目录',relevant) is None
 # A mixed question can still use a payment-only source for a partial answer.
 assert relevance_reason(query+' 待遇标准','温州市长期护理保险支付办法','温州市长期护理保险支付比例按待遇条件确定。') is None
 assert source_priority(query,'长期护理保险服务项目目录',relevant)>source_priority(query,'财政预算执行报告',irrelevant)


def test_tavily_orders_specialized_source_before_report_and_logs_query(monkeypatch):
 from app.services.web.cache import SearchCache
 monkeypatch.setattr('app.services.web.cache.search_cache',SearchCache())
 def handler(request):
  if request.url.path=='/search':
   return httpx.Response(200,json={'results':[{'title':'温州市财政预算执行报告','url':'https://wenzhou.gov.cn/budget'},{'title':'温州市长期护理保险护理服务项目目录','url':'https://wenzhou.gov.cn/catalog'}]})
  return httpx.Response(200,json={'results':[{'url':'https://wenzhou.gov.cn/budget','raw_content':'温州市推进长期护理保险制度建设，资金管理按财政预算执行。'},{'url':'https://wenzhou.gov.cn/catalog','raw_content':'温州市长期护理保险护理服务项目目录：居家护理包括生活照护和医疗护理。'}]})
 original=httpx.Client
 monkeypatch.setattr('app.services.web.tavily.httpx.Client',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
 service=TavilySearch(Settings(_env_file=None,tavily_api_key=SecretStr('unit-test'),tavily_max_results=1))
 query='温州市长期护理保险护理服务目录 服务项目'
 report=service.search_with_diagnostics(query)
 assert len(report.sources)==1 and report.sources[0].url.endswith('/catalog')
 assert report.diagnostics.search_query==query and report.diagnostics.rejected_counts['service_catalog_missing']==1
