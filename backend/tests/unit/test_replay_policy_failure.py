import json
from scripts import replay_policy_failure as script
from test_policy_graph import Model,decision,hit


def test_replay_preserves_exact_question_source_order_and_failed_drafts(monkeypatch,tmp_path):
 question='上城区户籍90岁老人的高龄老年人养老服务补贴，是不是按杭民发〔2024〕142号每月领9999元？'
 source=hit().model_copy(update={'text':'上城区户籍90周岁及以上高龄老人每人每月100元。'})
 original={'question':question,'preceding_turns':[],'response':{'retrieved_hits':[source.model_dump(mode='json')],'web_sources':[],'retrieval_log_id':'old-log','vector_count':43,'knowledge_scope':['general']}}
 path=tmp_path/'snapshot.json';path.write_text(json.dumps(original,ensure_ascii=False))
 bad={'sufficient':True,'paragraphs':[{'text':'每人每月9999元。','sources':[1]}]}
 model=Model(decision(),bad,bad)
 monkeypatch.setattr(script,'get_llm',lambda:model)
 monkeypatch.setattr(script,'BACKEND_DIR',tmp_path)
 assert script.main([str(path)])==0
 replay=json.loads(next((tmp_path/'var'/'diagnostics').glob('replay-*.json')).read_text())
 assert replay['question']==question and replay['source_chunk_ids']==[source.chunk_id]
 assert replay['response']['reason']=='unsupported_numeric_expansion'
 failures=[e for e in replay['trace_events'] if e['stage']=='generation_numeric_rejection']
 assert len(failures)==2 and '9999元' in failures[-1]['data']['draft']['paragraphs'][0]['text']
 assert model.calls[1]['evidence'][0]['text']==source.text


def test_replay_reuses_saved_web_body_without_calling_tavily(monkeypatch,tmp_path):
 question='温州市22岁户籍居民能否申请最新高龄津贴？'
 source=hit().model_copy(update={'text':'杭州市养老服务补贴资料。'})
 body='温州市2023年文件：为80周岁以上老年人发放高龄津贴，每人每月不低于60元。'
 original={'question':question,'preceding_turns':[],'response':{'retrieved_hits':[source.model_dump(mode='json')],'web_sources':[{'title':'温州市基本公共服务标准','url':'https://wenzhou.gov.cn/policy','content':body,'retrieved_at':'2026-10-30T00:00:00Z'}],'web_status':'success','retrieval_log_id':'old-log','vector_count':43,'knowledge_scope':['general']}}
 path=tmp_path/'snapshot.json';path.write_text(json.dumps(original,ensure_ascii=False))
 model=Model(decision(needs_freshness=True),{'sufficient':True,'paragraphs':[{'text':'您提供的年龄为22岁，低于所引温州市2023年文件写明80周岁以上的年龄要求，原文高龄津贴每人每月不低于60元。','sources':[2]}]})
 monkeypatch.setattr(script,'get_llm',lambda:model)
 monkeypatch.setattr(script,'BACKEND_DIR',tmp_path)
 assert script.main([str(path)])==0
 replay=json.loads(next((tmp_path/'var'/'diagnostics').glob('replay-*.json')).read_text())
 assert replay['saved_web_urls']==['https://wenzhou.gov.cn/policy']
 assert replay['response']['status']=='answered'
 assert replay['response']['web_sources'][0]['content']==body
 assert replay['response']['citations'][0]['source_type']=='web'
