"""Reproduce one saved question with the exact saved evidence. Calls the chat model only."""
import argparse
from datetime import datetime, UTC
import json
import os
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from types import SimpleNamespace
from app.agents.orchestrator import run_policy
from app.core.config import BACKEND_DIR, get_settings
from app.core.exceptions import BusinessError
from app.schemas.chat import PolicyQuestion, WebSource, WebDiagnostics
from app.services.web.tavily import SearchReport
from app.schemas.retrieval import SearchHit
from app.services.chat.llm import get_llm


def main(argv=None):
    parser=argparse.ArgumentParser(description='使用失败快照的原问题和原有来源复现；调用聊天模型，不检索、不联网、不写会话')
    parser.add_argument('snapshot',type=Path)
    args=parser.parse_args(argv)
    payload=json.loads(args.snapshot.read_text())
    response=payload['response']
    sources=[WebSource.model_validate(item) for item in response.get('web_sources',[])]
    diagnostic=WebDiagnostics.model_validate(response['web_diagnostics']) if response.get('web_diagnostics') else WebDiagnostics(stage='complete')
    class SavedWeb:
        configured=bool(sources)
        def search_with_diagnostics(self,query): return SearchReport(sources,diagnostic)
    saved_web=SavedWeb() if sources else None
    hits=[SearchHit.model_validate(item) for item in response['retrieved_hits']]
    history=[]
    for turn in payload.get('preceding_turns',[]):
        history.extend([{'role':'user','content':turn['question']},{'role':'assistant','content':turn['answer'][:6000]}])
    request=PolicyQuestion(question=payload['question'],history=history,dialogue_state=response.get('dialogue_state'))
    events=[]
    record={'mode':'exact_saved_evidence_live_chat_model','source_snapshot':str(args.snapshot.resolve()),
            'question':request.question,'history':history,'source_chunk_ids':[h.chunk_id for h in hits],'saved_web_urls':[source.url for source in sources],'trace_events':events}
    result=SimpleNamespace(hits=hits,log_id=response.get('retrieval_log_id'),vector_count=response.get('vector_count',0))
    # CLI-local patch fixes evidence and ranking to the saved request; never run in the API process.
    try:
        with patch('app.agents.orchestrator.hybrid.search',return_value=result):
            answer=run_policy(request,None,SimpleNamespace(ensure_configured=lambda:None),None,get_llm(),response.get('knowledge_scope') or get_settings().policy_kb_ids,web=saved_web,
                trace=lambda stage,data:events.append({'stage':stage,'data':data}))
        record['response']=answer.model_dump(mode='json')
    except BusinessError as error:
        record['error']={'status_code':error.status_code,'message':error.message}
    directory=BACKEND_DIR/'var'/'diagnostics'
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=directory/('replay-'+datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]+'.json')
    with open(path,'x',encoding='utf-8',opener=lambda name,flags:os.open(name,flags,0o600)) as handle:
        json.dump(record,handle,ensure_ascii=False,indent=2)
    print('结果：'+(record.get('response',{}).get('reason') or '聊天服务未完成'))
    print('轨迹文件：'+str(path))
    print('未重新检索、未调用Embedding或Tavily、未修改会话。')
    return 1 if 'error' in record else 0


if __name__=='__main__': raise SystemExit(main())
