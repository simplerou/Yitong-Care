"""Live fixed-case evaluation for the mind companion; no API server required."""
import argparse
import json
import subprocess
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.agents.mind_orchestrator import run_mind
from app.core.config import BACKEND_DIR, get_settings
from app.core.exceptions import BusinessError
from app.db.session import SessionLocal
from app.evaluation.mind import DATASET_PATH, check_answer, load_dataset, write_report
from app.models import DocumentChunk, KnowledgeDocument, VectorIndex
from app.schemas.chat import ChatTurn
from app.schemas.mind import MindAnswer, MindQuestion
from app.services.chat.llm import get_llm
from app.services.mind import emotions
from app.services.mind.dialogue_state import build_dialogue
from app.services.embedding.openai_compatible import get_embedder
from app.services.vectorstore.index_manager import get_index_manager
from app.services.web.tavily import get_web_search


class LocalOnly:
    configured = False


CODE_PATHS = [
    'app/agents/mind_orchestrator.py', 'app/services/mind/emotions.py', 'app/services/mind/risk.py',
    'app/services/mind/risk.py', 'app/services/mind/checks.py',
    'app/services/mind/prompts.py', 'app/services/mind/answer_scope.py',
    'app/services/mind/dialogue_state.py', 'app/schemas/mind.py', 'app/evaluation/mind.py',
    'app/services/chat/grounding.py', 'app/services/retrieval/hybrid.py', 'scripts/evaluate_mind.py',
]


def main(argv=None):
    parser = argparse.ArgumentParser(description='心灵陪伴固定业务评测（真实模型调用；报告仍需人工核对）')
    parser.add_argument('--validate-only', action='store_true', help='只校验数据集及基准原文，不访问数据库或模型')
    parser.add_argument('--recheck-report', type=Path, help='离线重查历史 report.json，不调用任何服务')
    parser.add_argument('--web', action='store_true', help='同时执行联网用例，允许 Tavily 搜索与提取')
    parser.add_argument('--case', action='append', default=[], help='只运行指定 ID，可重复')
    parser.add_argument('--output', type=Path, default=BACKEND_DIR / 'var/evaluations')
    args = parser.parse_args(argv)
    try:
        dataset, cases = load_dataset()
    except (ValueError, KeyError, OSError) as error:
        print('评测集校验失败：' + type(error).__name__)
        return 2

    if args.recheck_report:
        report = json.loads(args.recheck_report.read_text())
        if report['reference']['text_sha256'] != dataset['reference']['text_sha256']:
            print('基准原文已变更，不能直接重查旧回答。')
            return 2
        by_id = {case.id: case for case in cases}
        report['recheck_of'] = str(args.recheck_report.resolve())
        report['original_dataset_version'] = report['dataset_version']
        report['dataset_version'] = dataset['version']
        report['dataset_sha256'] = sha256(DATASET_PATH.read_bytes()).hexdigest()
        report['mode'] = 'offline_recheck_of_saved_responses'
        for row in report['results']:
            if row['automatic_status'] in {'not_run', 'blocked'} or not row.get('turns'): continue
            intermediate = [item for item in row.get('checks', []) if item['name'].startswith('context_turn_')]
            row['checks'] = intermediate + check_answer(by_id[row['id']], MindAnswer.model_validate(row['turns'][-1]['response']))
            row['automatic_status'] = 'automated_pass' if all(item['passed'] for item in row['checks']) else 'automated_fail'
        report['summary'] = {status: sum(row['automatic_status'] == status for row in report['results'])
                             for status in ['automated_pass', 'automated_fail', 'blocked', 'not_run']}
        report['rechecked_at'] = datetime.now(UTC).isoformat()
        report['checker_sha256'] = sha256((BACKEND_DIR / 'app/evaluation/mind.py').read_bytes()).hexdigest()
        output = write_report(report, args.output)
        print('原回答离线重查（没有新模型调用）：' + str(report['summary']))
        print('报告：' + str(output / 'report.md'))
        return 0

    known = {case.id for case in cases}
    if set(args.case) - known:
        print('不存在的用例 ID：' + ','.join(sorted(set(args.case) - known)))
        return 2
    selected = [case for case in cases if (not args.case or case.id in args.case) and (args.web or case.mode == 'local')]
    if not selected:
        print('没有可执行用例；联网用例需要 --web。')
        return 2
    if args.validate_only:
        print(f'基准哈希、原文摘录、用例 ID 及正则校验通过：全部 {len(cases)} 条，当前选择 {len(selected)} 条；未调用模型。')
        return 0

    settings = get_settings()
    report = {'status': 'running', 'started_at': datetime.now(UTC).isoformat(),
              'mode': 'live_with_web' if args.web else 'live_local_only',
              'dataset_version': dataset['version'],
              'dataset_sha256': sha256(DATASET_PATH.read_bytes()).hexdigest(),
              'reference': dataset['reference'], 'model': settings.llm_model,
              'embedding_model': settings.embedding_key, 'knowledge_scope': settings.mind_kb_ids,
              'table_version': emotions.TABLE_VERSION,
              'retrieval_parameters': {'top_k': 5, 'semantic_threshold': 0.12},
              'results': [], 'manual_review': 'pending'}
    for case in selected:
        report['results'].append({'id': case.id, 'topic': case.topic, 'automatic_status': 'not_run',
                                 'manual_status': 'not_run', 'manual_checks': case.manual_checks,
                                 'reference_pages': case.reference_pages, 'reference_quotes': case.reference_quotes,
                                 'turns': []})
    report['code_hashes'] = {name: sha256((BACKEND_DIR / name).read_bytes()).hexdigest() for name in CODE_PATHS}
    try:
        report['git_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=BACKEND_DIR,
                                                       text=True, stderr=subprocess.DEVNULL).strip()
        report['git_dirty'] = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=BACKEND_DIR,
                                                           text=True, stderr=subprocess.DEVNULL).strip())
    except (OSError, subprocess.SubprocessError):
        report['git_commit'] = None

    llm = get_llm(); embedder = get_embedder(); manager = get_index_manager()
    web = get_web_search() if args.web else LocalOnly()
    try:
        llm.ensure_configured(); embedder.ensure_configured()
        with SessionLocal() as db:
            db.execute(text('SELECT 1'))
            docs = db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.kb_id.in_(settings.mind_kb_ids))).all()
            report['corpus'] = [{'id': doc.id, 'name': doc.name, 'kb_id': doc.kb_id, 'status': doc.status,
                                 'updated_at': str(doc.updated_at),
                                 'content_sha256': sha256((doc.content or '').encode()).hexdigest()} for doc in docs]
            ready = db.scalar(select(func.count()).select_from(DocumentChunk)
                              .join(KnowledgeDocument, KnowledgeDocument.id == DocumentChunk.doc_id)
                              .where(DocumentChunk.kb_id.in_(settings.mind_kb_ids),
                                     DocumentChunk.embedding_model == settings.embedding_key,
                                     DocumentChunk.embedding_dim == settings.embedding_dimensions,
                                     DocumentChunk.vector_status == 'ready',
                                     DocumentChunk.embedding.is_not(None),
                                     KnowledgeDocument.status == 'vectorized'))
            report['ready_chunk_count'] = ready
            indices = db.scalars(select(VectorIndex).where(VectorIndex.kb_id.in_(settings.mind_kb_ids),
                                                           VectorIndex.model == settings.embedding_key)).all()
            report['indices'] = [{'kb_id': item.kb_id, 'version': item.version, 'sha256': item.sha256,
                                  'status': item.status, 'vector_count': item.vector_count} for item in indices]
            if any(case.mode == 'local' for case in selected) and not ready:
                raise BusinessError('心理关怀基准用例缺少当前知识范围和模型的已入库向量，未执行评测。', 503)
    except (BusinessError, SQLAlchemyError) as error:
        report['status'] = 'blocked'
        report['blocking_reason'] = error.message if isinstance(error, BusinessError) else '数据库预检失败，尚未执行任何业务用例。'

    if report['status'] != 'blocked':
        for case, row in zip(selected, report['results']):
            if case.mode == 'web' and not web.configured:
                row.update(automatic_status='blocked', error='Tavily Key 未配置，联网用例未执行。')
                continue
            case_web = web if case.mode == 'web' else LocalOnly()
            history = []; dialogue = None; response = None; checks = []
            try:
                for index, question in enumerate(case.turns):
                    dialogue = build_dialogue([question], dialogue)
                    events = []
                    started = perf_counter()
                    with SessionLocal() as db:
                        response = run_mind(MindQuestion(question=question, history=history[-6:], dialogue_state=dialogue),
                                            db, embedder, manager, llm, settings.mind_kb_ids, web=case_web,
                                            trace=lambda stage, data, _events=events: _events.append({'stage': stage, 'data': data}))
                    row['turns'].append({'question': question, 'response': response.model_dump(mode='json'),
                                         'trace_events': events, 'elapsed_ms': round((perf_counter() - started) * 1000, 1)})
                    history += [ChatTurn(role='user', content=question),
                                ChatTurn(role='assistant', content=response.answer[:6000])]
                    if index < len(case.turns) - 1:
                        checks.append({'name': f'context_turn_{index + 1}_completed',
                                       'passed': response.status in {'answered', 'clarification', 'emergency', 'boundary'},
                                       'detail': '多轮前置回答是否正常完成'})
                checks += check_answer(case, response)
                row.update(checks=checks,
                           automatic_status='automated_pass' if all(item['passed'] for item in checks) else 'automated_fail',
                           manual_status='pending')
                if response.reason in {'grounding_review_failed', 'unsafe_paragraph', 'invalid_output'}:
                    row['error'] = '安全或一致性检查拦截，需人工确认是否为预期结果。'
                if response.web_status == 'error':
                    row['automatic_status'] = 'blocked'
                    row['error'] = '联网服务错误，不计作事实准确性结果。'
            except (BusinessError, SQLAlchemyError) as error:
                row.update(automatic_status='blocked',
                           error=error.message if isinstance(error, BusinessError) else '数据库执行失败。')
                report['status'] = 'blocked'
                report['blocking_reason'] = '遇到基础服务错误，停止后续用例，避免重复失败调用。'
                break
            except Exception as error:  # noqa: BLE001 - report type only, never payloads
                row.update(automatic_status='blocked', error='执行异常：' + type(error).__name__)
                report['status'] = 'blocked'
                report['blocking_reason'] = '执行异常，后续用例未运行。'
                break
    if report['status'] == 'running':
        summary = {status: sum(row['automatic_status'] == status for row in report['results'])
                   for status in ['automated_pass', 'automated_fail', 'blocked', 'not_run']}
        report['summary'] = summary
        report['status'] = 'completed' if summary['automated_fail'] == 0 and summary['blocked'] == 0 else 'completed_with_failures'
    report['finished_at'] = datetime.now(UTC).isoformat()
    output = write_report(report, args.output)
    print(f"评测状态：{report['status']}；结果：{report.get('summary', {})}")
    print('报告：' + str(output / 'report.md'))
    print('注意：机械检查通过不代表陪伴质量达标，人工核对尚未完成。')
    return 0 if report['status'] in {'completed', 'completed_with_failures'} else 2


if __name__ == '__main__':
    raise SystemExit(main())
