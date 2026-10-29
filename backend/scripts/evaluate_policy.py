"""Live fixed-case evaluation; no API server required. All reports exclude credentials."""
import argparse
import json
from datetime import datetime, UTC
from hashlib import sha256
from pathlib import Path
from time import perf_counter
import subprocess
from sqlalchemy import select, text, func
from sqlalchemy.exc import SQLAlchemyError
from app.services.chat.grounding import normalized
from app.evaluation.policy import DATASET_PATH, load_dataset, check_answer, write_report
from app.schemas.chat import PolicyQuestion, ChatTurn
from app.core.config import get_settings, BACKEND_DIR
from app.core.exceptions import BusinessError
from app.db.session import SessionLocal
from app.models import KnowledgeDocument, DocumentChunk, VectorIndex
from app.agents.orchestrator import run_policy
from app.services.chat.llm import get_llm
from app.services.embedding.openai_compatible import get_embedder
from app.services.vectorstore.index_manager import get_index_manager
from app.services.web.tavily import get_web_search


class LocalOnly:
    configured=False


def main(argv=None):
    parser=argparse.ArgumentParser(description='固定政策业务评测（真实模型调用；报告仍需人工核对）')
    parser.add_argument('--validate-only',action='store_true',help='只校验数据集及基准原文，不访问数据库或模型')
    parser.add_argument('--recheck-report',type=Path,help='离线重查历史report.json，不调用任何服务')
    parser.add_argument('--web',action='store_true',help='同时执行联网时效用例，允许 Tavily 搜索与提取')
    parser.add_argument('--case',action='append',default=[],help='只运行指定ID，可重复；联网ID仍需 --web')
    parser.add_argument('--output',type=Path,default=BACKEND_DIR/'var/evaluations')
    args=parser.parse_args(argv)
    try: dataset,cases=load_dataset()
    except (ValueError,KeyError,OSError) as error:
        print('评测集校验失败：'+type(error).__name__);return 2
    if args.recheck_report:
        report=json.loads(args.recheck_report.read_text())
        if report['reference']['text_sha256']!=dataset['reference']['text_sha256']:
            print('基准原文已变更，不能直接重查旧回答。');return 2
        by_id={c.id:c for c in cases}
        report['recheck_of']=str(args.recheck_report.resolve())
        report['original_dataset_version']=report['dataset_version']
        report['dataset_version']=dataset['version']
        report['dataset_sha256']=sha256(DATASET_PATH.read_bytes()).hexdigest()
        report['mode']='offline_recheck_of_saved_responses'
        from app.schemas.chat import PolicyAnswer
        for row in report['results']:
            if row['automatic_status'] in {'not_run','blocked'} or not row.get('turns'): continue
            case=by_id[row['id']]
            intermediate=[c for c in row.get('checks',[]) if c['name'].startswith('context_turn_')]
            row['checks']=intermediate+check_answer(case,PolicyAnswer.model_validate(row['turns'][-1]['response']))
            row['automatic_status']='automated_pass' if all(c['passed'] for c in row['checks']) else 'automated_fail'
        report['summary']={status:sum(row['automatic_status']==status for row in report['results']) for status in ['automated_pass','automated_fail','blocked','not_run']}
        report['rechecked_at']=datetime.now(UTC).isoformat()
        report['checker_sha256']=sha256((BACKEND_DIR/'app/evaluation/policy.py').read_bytes()).hexdigest()
        output=write_report(report,args.output)
        print('原回答离线重查（没有新模型调用）：'+str(report['summary']))
        print('报告：'+str(output/'report.md'))
        return 0
    known={c.id for c in cases}
    if set(args.case)-known: print('不存在的用例ID：'+','.join(sorted(set(args.case)-known)));return 2
    selected=[c for c in cases if (not args.case or c.id in args.case) and (args.web or c.mode=='local')]
    if not selected: print('没有可执行用例；联网用例需要 --web。');return 2
    if args.validate_only:
        print(f'基准哈希、原文摘录、用例ID及正则校验通过：全部{len(cases)}条，当前选择{len(selected)}条；未调用模型。')
        return 0
    settings=get_settings()
    report={'status':'running','started_at':datetime.now(UTC).isoformat(),'mode':'live_with_web' if args.web else 'live_local_only',
        'dataset_version':dataset['version'],'dataset_sha256':sha256(DATASET_PATH.read_bytes()).hexdigest(),
        'reference':dataset['reference'],'model':settings.llm_model,'embedding_model':settings.embedding_key,
        'knowledge_scope':settings.policy_kb_ids,'retrieval_parameters':{'top_k':5,'semantic_threshold':0.12,'rrf_k':60},'results':[],'manual_review':'pending'}
    for case in selected:
        report['results'].append({'id':case.id,'topic':case.topic,'automatic_status':'not_run','manual_status':'not_run',
            'manual_checks':case.manual_checks,'reference_pages':case.reference_pages,'reference_quotes':case.reference_quotes,'turns':[]})
    paths=['app/agents/orchestrator.py','app/services/chat/prompt_builder.py','app/services/chat/grounding.py','app/services/chat/policy_checks.py','app/services/chat/evidence_limits.py','app/services/retrieval/hybrid.py','app/services/web/tavily.py','app/evaluation/policy.py','scripts/evaluate_policy.py']
    report['code_hashes']={name:sha256((BACKEND_DIR/name).read_bytes()).hexdigest() for name in paths}
    try:
        report['git_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=BACKEND_DIR,text=True,stderr=subprocess.DEVNULL).strip()
        report['git_dirty']=bool(subprocess.check_output(['git','status','--porcelain'],cwd=BACKEND_DIR,text=True,stderr=subprocess.DEVNULL).strip())
    except (OSError,subprocess.SubprocessError): report['git_commit']=None
    llm=get_llm();embedder=get_embedder();manager=get_index_manager();web=get_web_search() if args.web else LocalOnly()
    try:
        llm.ensure_configured();embedder.ensure_configured()
        with SessionLocal() as db:
            db.execute(text('SELECT 1'))
            docs=db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.kb_id.in_(settings.policy_kb_ids))).all()
            report['corpus']=[{'id':d.id,'name':d.name,'kb_id':d.kb_id,'status':d.status,'updated_at':str(d.updated_at),'content_sha256':sha256((d.content or '').encode()).hexdigest()} for d in docs]
            ready = db.scalar(select(func.count()).select_from(DocumentChunk).join(KnowledgeDocument,KnowledgeDocument.id==DocumentChunk.doc_id).where(
                DocumentChunk.kb_id.in_(settings.policy_kb_ids),DocumentChunk.embedding_model==settings.embedding_key,
                DocumentChunk.embedding_dim==settings.embedding_dimensions,DocumentChunk.vector_status=='ready',
                DocumentChunk.embedding.is_not(None),KnowledgeDocument.status=='vectorized'))
            report['ready_chunk_count']=ready
            indices=db.scalars(select(VectorIndex).where(VectorIndex.kb_id.in_(settings.policy_kb_ids),VectorIndex.model==settings.embedding_key)).all()
            report['indices']=[{'kb_id':i.kb_id,'version':i.version,'sha256':i.sha256,'status':i.status,'vector_count':i.vector_count} for i in indices]
            if any(c.mode=='local' and c.reference_quotes for c in selected) and not ready:
                raise BusinessError('本地基准用例缺少当前知识范围和模型的已入库向量，未执行评测。',503)
            if any(c.mode=='local' and c.reference_quotes for c in selected):
                marker=normalized(dataset['reference']['document_number']).replace('〔','').replace('〕','')
                corpus_text=''.join(normalized(d.content or '').replace('〔','').replace('〕','') for d in docs if d.status=='vectorized')
                if marker not in corpus_text:
                    raise BusinessError('未在已入库文档中找到基准文号，需先核对基准PDF及知识范围。',503)
    except (BusinessError,SQLAlchemyError) as error:
        report['status']='blocked'
        report['blocking_reason']=error.message if isinstance(error,BusinessError) else '数据库预检失败，尚未执行任何业务用例。'
    if report['status']!='blocked':
        for case,row in zip(selected,report['results']):
            if case.mode=='web' and not web.configured:
                row.update(automatic_status='blocked',error='Tavily Key未配置，联网用例未执行。');continue
            case_web=web if case.mode=='web' else LocalOnly()
            history=[];started=perf_counter();checks=[]
            try:
                for i,question in enumerate(case.turns):
                    events=[]
                    with SessionLocal() as db:
                        response=run_policy(PolicyQuestion(question=question,history=history[-6:]),db,embedder,manager,llm,settings.policy_kb_ids,web=case_web,trace=lambda stage,data:events.append({'stage':stage,'data':data}))
                    row['turns'].append({'question':question,'response':response.model_dump(mode='json'),'trace_events':events})
                    history += [ChatTurn(role='user',content=question),ChatTurn(role='assistant',content=response.answer[:6000])]
                    if i<len(case.turns)-1:
                        checks.append({'name':f'context_turn_{i+1}_answered','passed':response.status=='answered','detail':'多轮前置回答是否成功'})
                checks+=check_answer(case,response)
                row.update(checks=checks,automatic_status='automated_pass' if all(c['passed'] for c in checks) else 'automated_fail',manual_status='pending')
                if response.reason=='grounding_review_failed' or response.web_status=='error':
                    row['automatic_status']='blocked';row['error']='模型审查或联网服务错误，不计作事实准确性结果。'
                    report['status']='blocked';report['blocking_reason']='遇到审查或联网服务错误，停止后续用例。'
                    break
            except (BusinessError,SQLAlchemyError) as error:
                row.update(automatic_status='blocked',error=error.message if isinstance(error,BusinessError) else '数据库执行失败。')
                report['status']='blocked';report['blocking_reason']='遇到基础服务错误，停止后续用例，避免重复失败调用。'
                break
            except Exception as error:
                row.update(automatic_status='blocked',error='执行异常：'+type(error).__name__)
                report['status']='blocked';report['blocking_reason']='执行异常，后续用例未运行。'
                break
            finally:
                row['elapsed_ms']=round((perf_counter()-started)*1000)
                if row['turns']: row['manual_status']='pending'
            print(case.id+': '+row['automatic_status'],flush=True)
        if report['status']=='running': report['status']='partial' if any(r['automatic_status']=='blocked' for r in report['results']) else 'completed'
    report['summary']={status:sum(row['automatic_status']==status for row in report['results']) for status in ['automated_pass','automated_fail','blocked','not_run']}
    report['completed_at']=datetime.now(UTC).isoformat()
    output=write_report(report,args.output)
    print('报告：'+str(output/'report.md'))
    print('状态：'+report['status']+'；'+str(report['summary']))
    print('注意：自动断言不等于政策事实正确，须逐条人工核对原文。')
    return 0 if report['status']=='completed' and not report['summary']['automated_fail'] else 1


if __name__=='__main__':
    raise SystemExit(main())
