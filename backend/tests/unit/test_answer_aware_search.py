from types import SimpleNamespace
from pydantic import SecretStr
from app.core.config import Settings
from app.services.web.tavily import TavilySearch,SearchReport
from app.services.web.cache import SearchCache
from app.schemas.chat import PolicyQuestion,WebSource,WebDiagnostics,WebPageDiagnostic
from app.agents.orchestrator import run_policy
from test_policy_graph import Model,hit,setup_retrieval

QUESTION='我22岁，温州市龙湾区户籍，想了解长期护理保险的服务项目'
SOURCE='温州市长期护理保险服务目录：服务项目包括生活照护和医疗护理，是否享受须核对具体待遇条件。'
EMPTY={'sufficient':False,'paragraphs':[]}


def setup(monkeypatch,final_good):
 setup_retrieval(monkeypatch,[hit().model_copy(update={'text':'杭州养老服务补贴资料。'})])
 monkeypatch.setattr('app.services.web.cache.search_cache',SearchCache())
 web=TavilySearch(Settings(_env_file=None,tavily_api_key=SecretStr('unit-test')))
 queries=[]
 def fetch(query,*,excluded_urls=frozenset()):
  queries.append(query)
  url=f'https://wenzhou.gov.cn/source{len(queries)}'
  assert url not in excluded_urls
  content=SOURCE if final_good and len(queries)==3 else '温州市长期护理保险参考资料，尚需核对目录附件。'
  return SearchReport([WebSource(title='温州市长护险资料',url=url,content=content,retrieved_at='2026-10-30T00:00:00Z')],WebDiagnostics(search_query=query,stage='complete',search_count=1,official_count=1,extraction_requested=1,extraction_returned=1,body_count=1,accepted_count=1,pages=[WebPageDiagnostic(title='温州市长护险资料',url=url,outcome='accepted',reason='relevant')]))
 monkeypatch.setattr(web,'_search_with_diagnostics',fetch)
 return web,queries


def execute(web,model):
 return run_policy(PolicyQuestion(question=QUESTION),None,SimpleNamespace(ensure_configured=lambda:None),None,model,['general'],web=web)


def test_candidate_acceptance_does_not_stop_remaining_budget_after_insufficient_answer(monkeypatch):
 web,queries=setup(monkeypatch,True)
 good={'sufficient':True,'paragraphs':[{'text':'所引温州市长期护理保险目录列出生活照护和医疗护理项目，能否享受仍须核对待遇条件。','sources':[2]}]}
 model=Model({'supported':True,'needs_clarification':False,'query':QUESTION},EMPTY,EMPTY,EMPTY,good)
 answer=execute(web,model)
 assert len(queries)==3 and len(answer.web_diagnostics.attempts)==3
 assert answer.steps.count('web_refine')==2 and answer.status=='answered'
 assert answer.citations[0].source_type=='web' and answer.citations[0].web.url.endswith('source3')
 assert answer.citations[0].web.search_scope=='city_fallback'
 assert model.review_calls[0]['evidence'][0]['search_scope']=='city_fallback'


def test_no_supported_answer_after_three_rounds_stops_without_fabrication(monkeypatch):
 web,queries=setup(monkeypatch,False)
 model=Model({'supported':True,'needs_clarification':False,'query':QUESTION},EMPTY,EMPTY,EMPTY,EMPTY)
 answer=execute(web,model)
 assert len(queries)==3 and len(answer.web_diagnostics.attempts)==3
 assert answer.status=='insufficient' and not answer.citations and not model.review_calls
 assert '服务目录' in answer.answer and answer.general_info


def test_numeric_rejection_does_not_trigger_search_for_hallucinated_support(monkeypatch):
 web,queries=setup(monkeypatch,False)
 bad={'sufficient':True,'paragraphs':[{'text':'每月支付9999元。','sources':[2]}]}
 model=Model({'supported':True,'needs_clarification':False,'query':QUESTION},EMPTY,bad,bad)
 answer=execute(web,model)
 assert len(queries)==1 and answer.reason=='unsupported_numeric_expansion'
 assert not answer.citations and not answer.general_info
