"""Request-scoped health workflow. Deterministic vitals classification and triage run
before generation, and an L1 red flag never waits for the model."""
import logging
import re
from datetime import date
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from app.core.exceptions import BusinessError
from app.schemas.chat import Citation
from app.schemas.health import (
    HealthAnswer, HealthDraft, HealthParagraph, HealthQuestion, HealthReview, HealthUnderstanding,
    RouteSuggestion, Triage, VitalsAssessment, AdviceItem, MissingField,
)
from app.schemas.retrieval import SearchRequest
from app.services.chat.grounding import evidence_spans, normalized
from app.services.chat.metrics import MeasuredLLM, PolicyMetrics as HealthMetrics
from app.services.health import answer_scope, checks, prompts, triage as triage_rules, vitals
from app.services.health.dialogue_state import build_dialogue
from app.services.retrieval import hybrid

logger = logging.getLogger(__name__)

ROUTE_REASONS = {
    'medication': '用药剂量与配伍属于用药管家的范围，健康管家不提供剂量或停药建议。',
    'policy': '补贴、长期护理保险与报销属于政策顾问的范围。',
    'safety': '跌倒预防与居家改造属于安全守护的范围。',
    'diet': '具体食谱与热量安排属于膳食营养师的范围。',
    'mind': '情绪与社交问题属于心灵陪伴的范围。',
    'none': '我是健康管家，可以帮您解读血压、血糖、血氧等指标，并提供慢病生活方式建议。',
}
SCOPE_TEXT = '我是健康管家，可以帮您解读血压、血糖、血氧等测量指标和慢病生活方式问题。'
FRESHNESS = re.compile(r'最新|新版|更新|修订|现行|2024|2025|2026')


class HealthState(TypedDict, total=False):
    decision: HealthUnderstanding
    vitals: VitalsAssessment
    triage: Triage
    hits: list
    draft: dict
    candidates: list
    withheld: list
    citations: list
    web_sources: list
    web_status: str
    web_diagnostics: object
    web_warning: str | None
    web_query: str
    web_refine_found: bool
    web_attempted: bool
    answer_checks: dict
    advice: list
    missing_topics: list
    coverage: str
    general_info: list
    urgency: str
    required_action: str
    vitals_assessment: VitalsAssessment
    red_flags_observed: list
    triage_rule_ids: list
    missing_info: list
    route_suggestion: RouteSuggestion | None
    disclaimer: str
    rejection: str
    status: str
    answer: str
    reason: str
    steps: list[str]
    log_id: str | None
    vector_count: int


def run_health(request: HealthQuestion, db, embedder, manager, llm, kb_ids: list[str],
               web=None, trace=None, progress=None) -> HealthAnswer:
    metrics = HealthMetrics()
    llm = MeasuredLLM(llm, metrics)
    llm.ensure_configured()
    history = [turn.model_dump() for turn in request.history]
    user_history = [turn.content for turn in request.history if turn.role == 'user']
    dialogue = request.dialogue_state or build_dialogue([*user_history, request.question], profile=request.profile)
    text_all = request.question + '\n' + '\n'.join(user_history)

    def understand(state):
        payload = {'question': request.question, 'history': history,
                   'provided_vitals': [item.model_dump(mode='json') for item in request.vitals],
                   'profile': request.profile.model_dump(mode='json'),
                   'dialogue_state': dialogue.model_dump(mode='json'),
                   'today': date.today().isoformat()}
        decision = None
        for attempt in range(2):
            raw = llm.complete_json(prompts.UNDERSTAND, payload)
            try:
                decision = HealthUnderstanding.model_validate(raw)
                break
            except ValidationError as error:
                issues = [{'field': '.'.join(map(str, item['loc'])), 'type': item['type']} for item in error.errors()]
                logger.warning('Health understanding schema mismatch attempt=%s issues=%s', attempt + 1, issues)
                if attempt:
                    raise BusinessError('模型返回的问题分析格式不符合要求，请重试。', 502) from None
                payload = {**payload, 'format_retry': {
                    'instruction': '上次输出未通过结构校验。请重新分析原问题，严格遵守 JSON 字段类型，只填当前分支需要的字段。',
                    'issues': issues}}
        if decision.needs_clarification and not decision.supported:
            decision = decision.model_copy(update={'clarification': decision.clarification or SCOPE_TEXT})
        if trace: trace('understanding', decision.model_dump())
        return {'decision': decision, 'steps': ['understand']}

    def assess_vitals(state):
        assessment = vitals.assess(request.question, user_history, request.vitals, request.profile,
                                   reported_value=state['decision'].reported_value)
        if trace: trace('vitals', assessment.model_dump(mode='json'))
        return {'vitals': assessment, 'steps': state['steps'] + ['assess_vitals']}

    def triage_node(state):
        result = triage_rules.triage_of(state['vitals'], text_all, request.profile)
        if trace: trace('triage', result.model_dump(mode='json'))
        return {'triage': result, 'steps': state['steps'] + ['triage']}

    decisive = {'explicit_value', 'diastolic_value', 'measurement_context', 'fasting_status'}

    def route(state):
        tri = state['triage']
        decision = state['decision']
        assessment = state['vitals']
        if tri.level == 'L1': return 'emergency'
        if not decision.supported: return 'clarify'
        if decision.needs_clarification and (not assessment.readings or assessment.missing): return 'clarify'
        if decisive & set(assessment.missing): return 'clarify'
        return 'retrieve'

    def base_fields(state):
        assessment = state['vitals']
        tri = state['triage']
        decision = state['decision']
        return dict(urgency=tri.level, required_action=tri.required_action, vitals_assessment=assessment,
                    red_flags_observed=tri.red_flags, triage_rule_ids=tri.rule_ids,
                    missing_info=[field for field in assessment.missing if field in MissingField.__args__],
                    dialogue_state=dialogue, table_version=vitals.TABLE_VERSION,
                    model=llm.model, knowledge_scope=kb_ids, web_status=state.get('web_status', 'not_used'),
                    web_warning=state.get('web_warning'), web_sources=state.get('web_sources', []),
                    web_diagnostics=state.get('web_diagnostics'), vector_count=state.get('vector_count', 0),
                    retrieved_hits=state.get('hits', []), citations=state.get('citations', []),
                    retrieval_log_id=state.get('log_id'), steps=state['steps'])

    def emergency(state):
        tri = state['triage']
        return {**base_fields(state), 'status': 'emergency', 'reason': 'red_flag',
                'answer': checks.emergency_text(tri, state['vitals']),
                'disclaimer': checks.DISCLAIMER, 'answer_checks': None,
                'steps': state['steps'] + ['emergency']}

    def clarify(state):
        decision = state['decision']
        assessment = state['vitals']
        suggestion = None
        if not decision.supported:
            text = decision.clarification or SCOPE_TEXT
            if decision.route not in {'health', 'none'}:
                text = (text + '\n\n' if text else '') + ROUTE_REASONS[decision.route]
                suggestion = RouteSuggestion(agent=decision.route, reason=ROUTE_REASONS[decision.route])
        else:
            text = decision.clarification or vitals.clarification(assessment) or '请补充具体的测量数值和测量情境。'
        block = checks.assessment_block(assessment)
        answer = (block + '\n\n' if block else '') + text + '\n\n' + checks.EMERGENCY_CHECKLIST + '\n\n' + checks.DISCLAIMER
        return {**base_fields(state), 'status': 'clarification',
                'reason': 'outside_scope' if not decision.supported else 'missing_conditions',
                'answer': answer, 'disclaimer': checks.DISCLAIMER, 'route_suggestion': suggestion,
                'steps': state['steps'] + ['clarify']}

    def retrieve(state):
        embedder.ensure_configured()
        query = state['decision'].query or request.question
        result = hybrid.search(db, SearchRequest(query=query, top_k=5), embedder, manager, allowed_kb_ids=kb_ids)
        hits = []
        remaining = 20000
        for hit in result.hits:
            text = hit.text[:min(4000, remaining)]
            if not text: break
            hits.append(hit.model_copy(update={'text': text, 'chars': len(text), 'end': hit.start + len(text)}))
            remaining -= len(text)
        return {'hits': hits, 'log_id': result.log_id, 'vector_count': result.vector_count,
                'steps': state['steps'] + ['retrieve']}

    def wants_freshness(state):
        return bool(state['decision'].needs_freshness or FRESHNESS.search(text_all))

    def web_search(state):
        from app.services.web.tavily import WebSearchError
        update = {'web_attempted': True, 'steps': state['steps'] + ['web_search']}
        if web is None or not getattr(web, 'configured', False):
            return {**update, 'web_status': 'not_configured', 'web_sources': [],
                    'web_warning': '联网检索尚未配置，本次未核验指南版本。'}
        primary = state['vitals'].primary
        query = answer_scope.web_query(primary.metric if primary else state['decision'].metric, request.question)
        try:
            if hasattr(web, 'search_with_diagnostics'):
                report = web.search_with_diagnostics(query)
                sources, diagnostic = report.sources, report.diagnostics
            else:
                sources, diagnostic = web.search(query), None
            if trace: trace('web_query', {'query': query, 'count': len(sources)})
            return {**update, 'web_query': query, 'web_diagnostics': diagnostic, 'web_sources': sources,
                    'web_status': 'success' if sources else 'no_results',
                    'web_warning': None if sources else '联网检索未取得可用的官方网页正文，本次未核验指南版本。'}
        except WebSearchError as error:
            return {**update, 'web_sources': [], 'web_status': 'error',
                    'web_diagnostics': error.diagnostics, 'web_warning': str(error)}

    def can_refine(state):
        from app.services.web.tavily import TavilySearch
        return bool(isinstance(web, TavilySearch) and state.get('web_status') == 'success'
                    and state.get('web_diagnostics') and state.get('web_query')
                    and web.remaining_queries(state['web_query'], state['web_diagnostics']))

    def web_refine(state):
        from app.services.web.tavily import WebSearchError
        update = {'steps': state['steps'] + ['web_refine'], 'web_refine_found': False}
        old = {source.url for source in state.get('web_sources', [])}
        try:
            report = web.refine_with_diagnostics(state['web_query'], state.get('web_sources', []), state['web_diagnostics'])
            found = any(source.url not in old for source in report.sources)
            return {**update, 'web_refine_found': found, 'web_sources': report.sources,
                    'web_diagnostics': report.diagnostics}
        except WebSearchError as error:
            return {**update, 'web_status': 'error', 'web_warning': str(error), 'web_diagnostics': error.diagnostics}

    def evidence_for(state):
        local = [{'index': i, 'kind': 'local', 'document': hit.doc_name, 'source': hit.source,
                  'heading': hit.heading, 'text': hit.text, 'coverage': 'chunk'}
                 for i, hit in enumerate(state.get('hits', []), 1)]
        remote = [{'index': len(local) + i, 'kind': 'web', 'document': item.title, 'url': item.url,
                   'published_date': item.published_date, 'retrieved_at': item.retrieved_at,
                   'text': item.content, 'coverage': item.coverage, 'is_truncated': item.is_truncated}
                  for i, item in enumerate(state.get('web_sources', []), 1)]
        return local + remote

    def assessment_texts(state):
        assessment = state['vitals']
        texts = []
        for reading in assessment.readings:
            texts.extend([reading.display, reading.category, reading.reference_basis])
        return texts

    def generate(state):
        evidence = evidence_for(state)
        payload = {'question': state['decision'].query or request.question,
                   'user_question': request.question,
                   'profile': request.profile.model_dump(mode='json'),
                   'assessment': state['vitals'].model_dump(mode='json'),
                   'triage': {'level': state['triage'].level, 'required_action': state['triage'].required_action},
                   'evidence': evidence, 'today': date.today().isoformat(),
                   'freshness_requested': wants_freshness(state),
                   'web_status': state.get('web_status', 'not_used'),
                   'web_warning': state.get('web_warning')}
        evidence_by_index = {item['index']: item['text'] for item in evidence}
        draft = None
        rejection = ''
        for attempt in range(2):
            raw = llm.complete_json(prompts.GENERATE, payload, max_tokens=1600)
            try:
                draft = HealthDraft.model_validate(raw)
                if draft.sufficient:
                    if not draft.paragraphs: raise ValueError('empty_paragraphs')
                    for paragraph in draft.paragraphs:
                        if not paragraph.text.strip() or re.search(r'【.*?】', paragraph.text):
                            raise ValueError('citation_format')
                        if any(index < 1 or index > len(evidence) for index in paragraph.sources):
                            raise ValueError('citation_range')
                        if checks.paragraph_issues(paragraph, state['triage'].level):
                            raise ValueError('unsafe_paragraph')
                        if checks.context_claim_issues(paragraph.text, state['vitals']):
                            raise ValueError('wrong_category')
                    numeric = checks.numeric_support_issues(draft.paragraphs, evidence_by_index, assessment_texts(state))
                    if numeric:
                        if trace: trace('numeric_rejection', {'issues': numeric, 'attempt': attempt + 1})
                        raise ValueError('unsupported_number')
                break
            except (ValidationError, ValueError) as error:
                if trace: trace('generation_rejection', {'attempt': attempt + 1, 'error': str(error)})
                rejection = str(error)
                if not attempt:
                    payload = {**payload, 'format_retry': {
                        'instruction': '上次输出未通过格式、引用或安全校验。只输出规定 JSON；'
                                       '每段 sources 使用 evidence 中的整数编号，text 不写【】；'
                                       '只使用 assessment 或引用原文中出现的带单位数值；'
                                       '不给剂量、不诊断、不使用绝对化表述；'
                                       '判读类别必须与 assessment 一致，context 为 unknown 时不要写家庭自测或诊室；'
                                       '资料不足可返回 sufficient=false。',
                        'issues': [str(error)]}}
                draft = HealthDraft(sufficient=False, coverage='partial', paragraphs=[])
        if trace: trace('generation', draft.model_dump())
        return {'draft': draft.model_dump(), 'rejection': rejection, 'steps': state['steps'] + ['generate']}

    def validate(state):
        draft = HealthDraft.model_validate(state['draft'])
        if not draft.sufficient:
            rejection = state.get('rejection', '')
            if 'unsafe_paragraph' in rejection: return insufficient(state, 'unsafe_paragraph')
            if 'unsupported_number' in rejection: return insufficient(state, 'unsupported_number')
            if rejection: return insufficient(state, 'invalid_output')
            return insufficient(state, 'model_insufficient')
        evidence = evidence_for(state)
        evidence_by_index = {item['index']: item['text'] for item in evidence}
        candidates: list[HealthParagraph] = []
        withheld: list[str] = []
        for paragraph in draft.paragraphs:
            if not paragraph.text.strip() or re.search(r'【.*?】', paragraph.text):
                withheld.append('citation_format')
                continue
            if any(index < 1 or index > len(evidence) for index in paragraph.sources):
                withheld.append('citation_range')
                continue
            issues = checks.paragraph_issues(paragraph, state['triage'].level)
            if checks.context_claim_issues(paragraph.text, state['vitals']): issues.append('wrong_category')
            if issues:
                withheld.extend(issues)
                continue
            numeric = checks.numeric_support_issues([paragraph], evidence_by_index, assessment_texts(state))
            if numeric:
                withheld.append('unsupported_number')
                continue
            candidates.append(paragraph)
        if not candidates:
            return insufficient(state, 'invalid_output' if not withheld else 'unsafe_paragraph')
        return {'candidates': candidates, 'withheld': withheld, 'steps': state['steps'] + ['validate']}

    def verify_grounding(state):
        candidates = state['candidates']
        evidence = evidence_for(state)
        evidence_by_index = {item['index']: item for item in evidence}
        payload = {'question': state['decision'].query or request.question,
                   'user_question': request.question,
                   'assessment': state['vitals'].model_dump(mode='json'),
                   'triage': {'level': state['triage'].level},
                   'paragraphs': [{'paragraph': i, 'text': p.text, 'sources': p.sources}
                                  for i, p in enumerate(candidates, 1)],
                   'evidence': [dict(item, spans=evidence_spans(item['text']))
                                for item in evidence
                                if any(item['index'] in p.sources for p in candidates)]}
        if trace: trace('review_input', payload)
        try:
            raw = llm.review_json(prompts.GENERATE_REVIEW, payload)
            review = HealthReview.model_validate(raw)
            accepted = _evaluate_review(review, candidates, evidence_by_index)
        except (ValidationError, ValueError) as error:
            logger.warning('Health grounding review unusable type=%s', type(error).__name__)
            return insufficient(state, 'grounding_review_failed')
        if not accepted:
            result = insufficient(state, 'unsupported_health_claim')
            result['answer_checks'] = {'status': 'blocked', 'checked_paragraphs': len(candidates),
                                       'accepted_paragraphs': 0, 'issues': ['no_supported_paragraph']}
            return result
        return finish(state, accepted)

    def insufficient(state, reason=None):
        assessment = state['vitals']
        tri = state['triage']
        reason = reason or state.get('reason') or ('no_hits' if not state.get('hits') else 'invalid_output')
        answer = checks.insufficient_text(assessment, tri, reason)
        if state.get('web_warning'): answer += '\n\n' + state['web_warning']
        answer += '\n\n' + checks.DISCLAIMER
        return {**base_fields(state), 'status': 'insufficient', 'reason': reason, 'answer': answer,
                'citations': [], 'disclaimer': checks.DISCLAIMER,
                'coverage': 'none', 'missing_topics': ['full_health_scope'],
                'answer_checks': state.get('answer_checks'),
                'steps': state['steps'] + ['insufficient']}

    def finish(state, accepted: list[HealthParagraph]):
        evidence_count = len(state.get('hits', []))
        used: set[int] = set()
        rendered = []
        advice = []
        for paragraph in accepted:
            indices = sorted(set(paragraph.sources))
            used.update(indices)
            rendered.append(paragraph.text.strip() + ''.join(f'【{index}】' for index in indices))
            advice.append(AdviceItem(kind=paragraph.kind, text=paragraph.text.strip(), sources=indices))
        citations = []
        for index in sorted(used):
            if index <= evidence_count:
                citations.append(Citation(index=index, hit=state['hits'][index - 1]))
            else:
                citations.append(Citation(index=index, source_type='web',
                                          web=state['web_sources'][index - evidence_count - 1]))
        parts = []
        block = checks.assessment_block(state['vitals'])
        if block: parts.append(block)
        parts.extend(rendered)
        referral = checks.referral_text(state['triage'])
        if referral: parts.append(referral)
        parts.append(checks.EMERGENCY_CHECKLIST)
        if state.get('web_warning'): parts.append(state['web_warning'])
        parts.append(checks.DISCLAIMER)
        checks_state = {'status': 'partial' if state.get('withheld') else 'passed',
                        'checked_paragraphs': len(state['candidates']),
                        'accepted_paragraphs': len(accepted),
                        'issues': state.get('withheld', [])}
        draft = HealthDraft.model_validate(state['draft'])
        general = answer_scope.concept_help(request.question) if draft.coverage == 'partial' else []
        return {**base_fields(state), 'status': 'answered', 'reason': 'grounded_answer',
                'answer': '\n\n'.join(parts), 'citations': citations, 'advice': advice,
                'answer_checks': checks_state, 'coverage': draft.coverage,
                'missing_topics': draft.missing_topics, 'general_info': general,
                'steps': state['steps'] + ['verify_grounding']}

    graph = StateGraph(HealthState)
    for name, node in [('understand', understand), ('assess_vitals', assess_vitals), ('triage', triage_node),
                       ('emergency', emergency), ('clarify', clarify), ('retrieve', retrieve),
                       ('web_search', web_search), ('web_refine', web_refine), ('generate', generate),
                       ('validate', validate), ('verify_grounding', verify_grounding), ('insufficient', insufficient)]:
        def with_progress(state, _name=name, _node=node):
            if progress: progress(_name)
            return _node(state)
        graph.add_node(name, metrics.measure_node(name, with_progress))
    graph.add_edge(START, 'understand')
    graph.add_edge('understand', 'assess_vitals')
    graph.add_edge('assess_vitals', 'triage')
    graph.add_conditional_edges('triage', route,
                                {'emergency': 'emergency', 'clarify': 'clarify', 'retrieve': 'retrieve'})
    graph.add_conditional_edges('retrieve', lambda s: 'web_search' if wants_freshness(s) or not s['hits'] else 'generate',
                                {'generate': 'generate', 'web_search': 'web_search'})
    graph.add_conditional_edges('web_search', lambda s: 'generate' if s.get('web_sources') or s.get('hits') else 'insufficient',
                                {'generate': 'generate', 'insufficient': 'insufficient'})
    graph.add_conditional_edges('validate', lambda s: 'verify_grounding' if s.get('candidates') else END,
                                {'verify_grounding': 'verify_grounding', END: END})
    graph.add_edge('generate', 'validate')
    graph.add_conditional_edges('verify_grounding', lambda s: END, {END: END})
    for terminal in ('clarify', 'emergency', 'insufficient'):
        graph.add_edge(terminal, END)
    try:
        state = graph.compile().invoke({})
    finally:
        logger.info('Health execution metrics=%s', metrics.snapshot())

    return HealthAnswer(
        status=state['status'], urgency=state.get('urgency'), required_action=state.get('required_action'),
        answer=state['answer'], vitals_assessment=state.get('vitals_assessment'),
        red_flags_observed=state.get('red_flags_observed', []),
        missing_info=state.get('missing_info', []), advice=state.get('advice', []),
        triage_rule_ids=state.get('triage_rule_ids', []), route_suggestion=state.get('route_suggestion'),
        coverage=state.get('coverage'), missing_topics=state.get('missing_topics', []),
        general_info=state.get('general_info', []), dialogue_state=dialogue,
        citations=state.get('citations', []), retrieved_hits=state.get('hits', []),
        web_sources=state.get('web_sources', []), web_status=state.get('web_status', 'not_used'),
        web_warning=state.get('web_warning'), web_diagnostics=state.get('web_diagnostics'),
        answer_checks=state.get('answer_checks'), metrics=metrics.snapshot(),
        disclaimer=state.get('disclaimer', checks.DISCLAIMER), table_version=vitals.TABLE_VERSION,
        vector_count=state.get('vector_count', 0), reason=state.get('reason'),
        retrieval_log_id=state.get('log_id'), model=llm.model, knowledge_scope=kb_ids,
        steps=state['steps'])


def _evaluate_review(review: HealthReview, paragraphs: list[HealthParagraph],
                     evidence_by_index: dict[int, dict]) -> list[HealthParagraph]:
    """Keep a paragraph only when the reviewer's quotes can be located in cited evidence."""
    if len(review.assessments) != len(paragraphs):
        raise ValueError('review_coverage')
    if {item.paragraph for item in review.assessments} != set(range(1, len(paragraphs) + 1)):
        raise ValueError('review_coverage')
    accepted: list[HealthParagraph] = []
    for item in sorted(review.assessments, key=lambda entry: entry.paragraph):
        paragraph = paragraphs[item.paragraph - 1]
        if not item.supported or item.reason != 'supported' or not item.addresses_question:
            continue
        if not item.quotes:
            continue
        valid = True
        for quote in item.quotes:
            source = evidence_by_index.get(quote.source_index)
            if quote.source_index not in paragraph.sources or source is None:
                valid = False
                break
            text = source['text']
            if quote.span_ids:
                spans = {span['span'] for span in evidence_spans(text)}
                if any(index not in spans for index in quote.span_ids):
                    valid = False
                    break
            elif not quote.text.strip() or normalized(quote.text) not in normalized(text):
                valid = False
                break
        if valid:
            accepted.append(paragraph)
    return accepted


def run_health_trace(request, db, embedder, manager, llm, kb_ids, **kwargs):
    return run_health(request, db, embedder, manager, llm, kb_ids, **kwargs)


__all__ = ['run_health', 'HealthState']
