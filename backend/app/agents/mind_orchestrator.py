"""Request-scoped mind companion workflow. Crisis protocol and safety plan are code-owned."""
import logging
import re
from datetime import date
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from app.core.exceptions import BusinessError
from app.schemas.chat import Citation
from app.schemas.mind import (
    AdviceItem, MindAnswer, MindAssessment, MindDraft, MindParagraph, MindProfile, MindQuestion,
    MindReview, MindTriage, MindUnderstanding, RouteSuggestion, ScreeningResult, RiskSignal,
)
from app.schemas.retrieval import SearchRequest
from app.services.chat.grounding import evidence_spans, normalized
from app.services.chat.metrics import MeasuredLLM, PolicyMetrics as MindMetrics
from app.services.mind import answer_scope, checks, emotions, prompts, risk
from app.services.mind.dialogue_state import build_dialogue, infer_profile
from app.services.retrieval import hybrid

logger = logging.getLogger(__name__)

SCOPE_TEXT = '我是心灵陪伴，可以陪你聊聊情绪、孤独、丧亲、睡眠和家庭关系，也可以一起想一些能做的小事。'
ROUTE_REASONS = {
    'health': '身体不适和疾病问题属于健康管家的范围。',
    'medication': '药物剂量与调整属于用药管家的范围。',
    'safety': '居家安全与跌倒问题属于安全守护的范围。',
    'diet': '膳食与营养问题属于膳食营养师的范围。',
    'policy': '补贴与政策问题属于政策顾问的范围。',
    'none': '这个问题不属于心灵陪伴的服务范围。',
}
BOUNDARY_INTENTS = {'therapy_request', 'medication_request'}
CONFIDENTIALITY_NOTE = ('关于保密：你说的话我会认真听，也不会随意转述；但如果你有伤害自己或他人的想法，'
                        '我会建议你立刻联系家人和专业人员，这一点我不能承诺替你保密。')
FRESHNESS = re.compile(r'最新|新版|更新|修订|2025|2026')


class MindState(TypedDict, total=False):
    decision: MindUnderstanding
    assessment: MindAssessment
    triage: MindTriage
    intent: str
    signals: list
    screening: ScreeningResult
    risk_level: str
    safety_plan: list
    crisis_notice: str | None
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
    web_attempted: bool
    answer_checks: dict
    urgency: str
    required_action: str
    red_flags_observed: list
    triage_rule_ids: list
    missing_info: list
    route_suggestion: RouteSuggestion | None
    boundary: str | None
    advice: list
    coverage: str
    missing_topics: list
    general_info: list
    disclaimer: str
    rejection: str
    status: str
    answer: str
    reason: str
    steps: list[str]
    log_id: str | None
    vector_count: int


def run_mind(request: MindQuestion, db, embedder, manager, llm, kb_ids: list[str],
             web=None, trace=None, progress=None) -> MindAnswer:
    metrics = MindMetrics()
    llm = MeasuredLLM(llm, metrics)
    llm.ensure_configured()
    history = [turn.model_dump() for turn in request.history]
    user_history = [turn.content for turn in request.history if turn.role == 'user']
    text_all = request.question + '\n' + '\n'.join(user_history)
    profile = infer_profile(request.profile, text_all)
    dialogue = request.dialogue_state or build_dialogue([*user_history, request.question])

    def understand(state):
        payload = {'question': request.question, 'history': history,
                   'profile': profile.model_dump(mode='json'),
                   'dialogue_state': dialogue.model_dump(mode='json'),
                   'today': date.today().isoformat()}
        decision = None
        for attempt in range(2):
            raw = llm.complete_json(prompts.UNDERSTAND, payload)
            try:
                decision = MindUnderstanding.model_validate(raw)
                break
            except ValidationError as error:
                issues = [{'field': '.'.join(map(str, item['loc'])), 'type': item['type']} for item in error.errors()]
                logger.warning('Mind understanding schema mismatch attempt=%s issues=%s', attempt + 1, issues)
                if attempt:
                    # Never fail a distress message with a 502: fall back to a neutral decision.
                    # The deterministic risk rules still decide whether this is a crisis.
                    logger.warning('Mind understanding unusable; falling back to a neutral decision')
                    decision = MindUnderstanding(supported=True, needs_clarification=False,
                                                 query=request.question[:1000], intent='emotional_support')
                    break
                payload = {**payload, 'format_retry': {
                    'instruction': '上次输出未通过结构校验。请重新分析原问题，严格遵守 JSON 字段类型，只填当前分支需要的字段。',
                    'issues': issues}}
        if not decision.supported and decision.needs_clarification and not decision.clarification:
            decision = decision.model_copy(update={'clarification': SCOPE_TEXT})
        if trace: trace('understanding', decision.model_dump())
        return {'decision': decision, 'steps': ['understand']}

    def assess_mind(state):
        assessment = emotions.assessment(text_all, profile)
        triage = risk.triage(text_all, assessment, profile)
        # Deterministic intent guard: therapy or medication requests cannot bypass the boundary.
        intent = state['decision'].intent
        if re.search(r'治疗方案|治疗计划|练习步骤|疗程|认知行为|CBT|心理治疗怎么做', request.question):
            intent = 'therapy_request'
        elif re.search(r'安眠药|抗抑郁药|吃什么药|剂量|几片', request.question):
            intent = 'medication_request'
        if trace: trace('mind', {'signals': [signal.id for signal in assessment.signals],
                                 'risk_level': assessment.risk_level, 'screening': assessment.screening.model_dump(),
                                 'triage': triage.model_dump(), 'intent': intent})
        return {'assessment': assessment, 'triage': triage, 'intent': intent,
                'signals': assessment.signals, 'screening': assessment.screening,
                'risk_level': assessment.risk_level, 'steps': state['steps'] + ['assess_mind']}

    def route(state):
        triage = state['triage']
        assessment = state['assessment']
        decision = state['decision']
        intent = state['intent']
        if triage.level == 'L1': return 'crisis'
        if intent in BOUNDARY_INTENTS: return 'boundary'
        if not decision.supported: return 'clarify'
        risk_signals = [signal for signal in assessment.signals if signal.kind == 'risk']
        if decision.needs_clarification and not risk_signals: return 'clarify'
        return 'retrieve'

    def base_fields(state):
        triage = state['triage']
        assessment = state['assessment']
        return dict(urgency=triage.level, required_action=triage.required_action,
                    signals=assessment.signals, screening=assessment.screening,
                    risk_level=assessment.risk_level, safety_plan=risk.safety_plan_text() if triage.level == 'L2' else [],
                    crisis_notice=checks.crisis_block(triage) if triage.level == 'L1' else None,
                    red_flags_observed=triage.red_flags, triage_rule_ids=triage.rule_ids,
                    dialogue_state=dialogue, table_version=emotions.TABLE_VERSION,
                    model=llm.model, knowledge_scope=kb_ids, web_status=state.get('web_status', 'not_used'),
                    web_warning=state.get('web_warning'), web_sources=state.get('web_sources', []),
                    web_diagnostics=state.get('web_diagnostics'), vector_count=state.get('vector_count', 0),
                    retrieved_hits=state.get('hits', []), citations=state.get('citations', []),
                    retrieval_log_id=state.get('log_id'), steps=state['steps'])

    def crisis(state):
        triage = state['triage']
        parts = [checks.crisis_block(triage), checks.EMERGENCY_CHECKLIST, checks.DISCLAIMER]
        return {**base_fields(state), 'status': 'crisis', 'reason': 'crisis_protocol',
                'answer': '\n\n'.join(parts), 'citations': [], 'boundary': None, 'advice': [],
                'answer_checks': None, 'steps': state['steps'] + ['crisis']}

    def boundary(state):
        assessment = state['assessment']
        text = checks.boundary_text(state['intent'])
        parts = [text, checks.tips_block('emotional_support'),
                 checks.referral_text(state['triage']), checks.EMERGENCY_CHECKLIST, checks.DISCLAIMER]
        suggestion = RouteSuggestion(agent='medication', reason=ROUTE_REASONS['medication']) \
            if state['intent'] == 'medication_request' else None
        return {**base_fields(state), 'status': 'boundary', 'reason': f'{state["intent"]}_not_allowed',
                'answer': '\n\n'.join(part for part in parts if part), 'boundary': text,
                'route_suggestion': suggestion, 'disclaimer': checks.DISCLAIMER, 'advice': [],
                'steps': state['steps'] + ['boundary']}

    def clarify(state):
        decision = state['decision']
        assessment = state['assessment']
        if not decision.supported:
            text = decision.clarification or SCOPE_TEXT
            suggestion = None
            if decision.route not in {'mind', 'none'}:
                text = text + '\n\n' + ROUTE_REASONS[decision.route]
                suggestion = RouteSuggestion(agent=decision.route, reason=ROUTE_REASONS[decision.route])
        else:
            text = checks.WARM_OPEN + '\n' + (decision.clarification or '如果你愿意，可以说说这种状态大概持续多久了？')
            suggestion = None
        parts = [checks.screening_block(assessment), text, checks.EMERGENCY_CHECKLIST, checks.DISCLAIMER]
        return {**base_fields(state), 'status': 'clarification',
                'reason': 'outside_scope' if not decision.supported else 'missing_conditions',
                'answer': '\n\n'.join(part for part in parts if part), 'route_suggestion': suggestion,
                'disclaimer': checks.DISCLAIMER, 'advice': [], 'steps': state['steps'] + ['clarify']}

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
                    'web_warning': '联网检索尚未配置，本次未核验资料版本。'}
        query = answer_scope.web_query(state['intent'], request.question)
        try:
            if hasattr(web, 'search_with_diagnostics'):
                report = web.search_with_diagnostics(query)
                sources, diagnostic = report.sources, report.diagnostics
            else:
                sources, diagnostic = web.search(query), None
            return {**update, 'web_query': query, 'web_diagnostics': diagnostic, 'web_sources': sources,
                    'web_status': 'success' if sources else 'no_results',
                    'web_warning': None if sources else '联网检索未取得可用的官方网页正文。'}
        except WebSearchError as error:
            return {**update, 'web_sources': [], 'web_status': 'error',
                    'web_diagnostics': error.diagnostics, 'web_warning': str(error)}

    def evidence_for(state):
        local = [{'index': i, 'kind': 'local', 'document': hit.doc_name, 'source': hit.source,
                  'heading': hit.heading, 'text': hit.text, 'coverage': 'chunk'}
                 for i, hit in enumerate(state.get('hits', []), 1)]
        remote = [{'index': len(local) + i, 'kind': 'web', 'document': item.title, 'url': item.url,
                   'published_date': item.published_date, 'retrieved_at': item.retrieved_at,
                   'text': item.content, 'coverage': item.coverage, 'is_truncated': item.is_truncated}
                  for i, item in enumerate(state.get('web_sources', []), 1)]
        return local + remote

    def generate(state):
        evidence = evidence_for(state)
        assessment = state['assessment']
        payload = {'question': state['decision'].query or request.question, 'user_question': request.question,
                   'intent': state['intent'], 'profile': profile.model_dump(mode='json'),
                   'assessment': {'signals': [signal.model_dump(mode='json') for signal in assessment.signals],
                                  'screening': assessment.screening.model_dump(mode='json'),
                                  'risk_level': assessment.risk_level},
                   'evidence': evidence, 'today': date.today().isoformat(),
                   'freshness_requested': wants_freshness(state), 'web_status': state.get('web_status', 'not_used')}
        draft = None
        rejection = ''
        for attempt in range(2):
            raw = llm.complete_json(prompts.GENERATE, payload, max_tokens=1800)
            try:
                draft = MindDraft.model_validate(raw)
                if draft.sufficient:
                    if not draft.paragraphs: raise ValueError('empty_paragraphs')
                    for paragraph in draft.paragraphs:
                        if not paragraph.text.strip() or re.search(r'【.*?】', paragraph.text):
                            raise ValueError('citation_format')
                        if paragraph.kind != 'empathy':
                            if any(index < 1 or index > len(evidence) for index in paragraph.sources):
                                raise ValueError('citation_range')
                        if checks.paragraph_issues(paragraph, state['triage'].level):
                            raise ValueError('unsafe_paragraph')
                break
            except (ValidationError, ValueError) as error:
                rejection = str(error)
                if trace: trace('generation_rejection', {'attempt': attempt + 1, 'error': rejection})
                draft = MindDraft(sufficient=False, coverage='partial', paragraphs=[])
                if not attempt:
                    payload = {**payload, 'format_retry': {
                        'instruction': '上次输出未通过格式或安全校验。只输出规定 JSON；'
                                       'empathy 段落 sources 必须为空，advice 段落必须有 sources；'
                                       '不诊断、不建议用药、不写伤害方法、不说想开点或一定会好；'
                                       '没有资料时只写 empathy 段落。',
                        'issues': [rejection]}}
        if trace: trace('generation', draft.model_dump())
        return {'draft': draft.model_dump(), 'rejection': rejection, 'steps': state['steps'] + ['generate']}

    def validate(state):
        draft = MindDraft.model_validate(state['draft'])
        if not draft.sufficient:
            if state['intent'] == 'education': return insufficient(state, 'model_insufficient')
            return supportive(state)
        evidence = evidence_for(state)
        candidates: list[MindParagraph] = []
        withheld: list[str] = []
        for paragraph in draft.paragraphs:
            if not paragraph.text.strip() or re.search(r'【.*?】', paragraph.text):
                withheld.append('citation_format'); continue
            if paragraph.kind != 'empathy' and any(index < 1 or index > len(evidence) for index in paragraph.sources):
                withheld.append('citation_range'); continue
            issues = checks.paragraph_issues(paragraph, state['triage'].level)
            if issues:
                withheld.extend(issues); continue
            candidates.append(paragraph)
        if not candidates:
            if state['intent'] == 'education': return insufficient(state, 'unsafe_paragraph' if withheld else 'invalid_output')
            return supportive(state)
        return {'candidates': candidates, 'withheld': withheld, 'steps': state['steps'] + ['validate']}

    def verify_grounding(state):
        candidates = state['candidates']
        evidence = evidence_for(state)
        evidence_by_index = {item['index']: item for item in evidence}
        payload = {'question': state['decision'].query or request.question, 'user_question': request.question,
                   'intent': state['intent'],
                   'assessment': {'risk_level': state['assessment'].risk_level},
                   'triage': {'level': state['triage'].level},
                   'paragraphs': [{'paragraph': i, 'text': p.text, 'sources': p.sources, 'kind': p.kind}
                                  for i, p in enumerate(candidates, 1)],
                   'evidence': [dict(item, spans=evidence_spans(item['text'])) for item in evidence
                                if any(item['index'] in p.sources for p in candidates)]}
        try:
            raw = llm.review_json(prompts.GENERATE_REVIEW, payload)
            review = MindReview.model_validate(raw)
            accepted = _evaluate_review(review, candidates, evidence_by_index)
        except (ValidationError, ValueError) as error:
            logger.warning('Mind grounding review unusable type=%s', type(error).__name__)
            if all(paragraph.kind == 'empathy' for paragraph in candidates):
                return finish(state, candidates)
            return insufficient(state, 'grounding_review_failed')
        if not accepted:
            if all(paragraph.kind == 'empathy' for paragraph in candidates): return finish(state, candidates)
            return insufficient(state, 'unsupported_mind_claim')
        return finish(state, accepted)

    def insufficient(state, reason=None):
        assessment = state['assessment']
        triage = state['triage']
        reason = reason or ('no_hits' if not state.get('hits') else 'invalid_output')
        answer = checks.insufficient_text(assessment, triage, reason)
        if state.get('web_warning'): answer += '\n\n' + state['web_warning']
        return {**base_fields(state), 'status': 'insufficient', 'reason': reason, 'answer': answer,
                'citations': [], 'coverage': 'none', 'missing_topics': ['evidence'],
                'disclaimer': checks.DISCLAIMER, 'boundary': None, 'advice': [],
                'answer_checks': state.get('answer_checks'), 'steps': state['steps'] + ['insufficient']}

    def supportive(state):
        assessment = state['assessment']
        triage = state['triage']
        parts = [checks.tips_block(state['intent'])]
        screening = checks.screening_block(assessment)
        if screening: parts.append(screening)
        if triage.level == 'L2': parts.append(checks.safety_plan_block())
        referral = checks.referral_text(triage)
        if referral: parts.append(referral)
        parts.append(checks.EMERGENCY_CHECKLIST)
        parts.append(checks.DISCLAIMER)
        return {**base_fields(state), 'status': 'answered', 'reason': 'supportive_fallback',
                'answer': '\n\n'.join(part for part in parts if part), 'citations': [], 'advice': [],
                'coverage': 'partial', 'missing_topics': ['evidence'], 'boundary': None,
                'answer_checks': {'status': 'partial', 'checked_paragraphs': 0, 'accepted_paragraphs': 0,
                                  'issues': ['supportive_fallback'], 'review_attempts': 0},
                'steps': state['steps'] + ['supportive_fallback']}

    def finish(state, accepted: list[MindParagraph]):
        assessment = state['assessment']
        evidence_count = len(state.get('hits', []))
        used: set[int] = set()
        rendered: list[str] = []
        advice: list[AdviceItem] = []
        for paragraph in accepted:
            if paragraph.kind == 'empathy':
                rendered.append(paragraph.text.strip())
                advice.append(AdviceItem(kind='empathy', text=paragraph.text.strip(), sources=[]))
                continue
            indices = sorted(set(paragraph.sources))
            used.update(indices)
            text = paragraph.text.strip()
            stray = re.search(r'(\d{1,2})([。！？])$', text)
            if stray and int(stray[1]) in indices:
                text = text[:stray.start()] + stray[2]
            rendered.append(text + ''.join(f'【{index}】' for index in indices))
            advice.append(AdviceItem(kind='advice', text=text, sources=indices))
        citations = []
        for index in sorted(used):
            if index <= evidence_count:
                citations.append(Citation(index=index, hit=state['hits'][index - 1]))
            else:
                citations.append(Citation(index=index, source_type='web',
                                          web=state['web_sources'][index - evidence_count - 1]))
        parts = list(rendered)
        screening = checks.screening_block(assessment)
        if screening: parts.append(screening)
        if state['triage'].level == 'L2': parts.append(checks.safety_plan_block())
        if state['triage'].level in {'L3', 'L4'} or not any(item.kind == 'advice' for item in accepted):
            parts.append(checks.tips_block(state['intent']))
        if state['intent'] == 'confidentiality': parts.append(CONFIDENTIALITY_NOTE)
        referral = checks.referral_text(state['triage'])
        if referral: parts.append(referral)
        parts.append(checks.EMERGENCY_CHECKLIST)
        if state.get('web_warning'): parts.append(state['web_warning'])
        parts.append(checks.DISCLAIMER)
        draft = MindDraft.model_validate(state['draft'])
        return {**base_fields(state), 'status': 'answered', 'reason': 'grounded_answer',
                'answer': '\n\n'.join(part for part in parts if part), 'citations': citations, 'advice': advice,
                'boundary': None, 'coverage': draft.coverage, 'missing_topics': draft.missing_topics,
                'general_info': answer_scope.concept_help(request.question) if draft.coverage == 'partial' else [],
                'answer_checks': {'status': 'partial' if state.get('withheld') else 'passed',
                                  'checked_paragraphs': len(state['candidates']),
                                  'accepted_paragraphs': len(accepted), 'issues': state.get('withheld', []),
                                  'review_attempts': 1},
                'steps': state['steps'] + ['verify_grounding']}

    graph = StateGraph(MindState)
    for name, node in [('understand', understand), ('assess_mind', assess_mind), ('crisis', crisis),
                       ('boundary', boundary), ('clarify', clarify), ('retrieve', retrieve),
                       ('web_search', web_search), ('generate', generate), ('validate', validate),
                       ('verify_grounding', verify_grounding), ('insufficient', insufficient)]:
        def with_progress(state, _name=name, _node=node):
            if progress: progress(_name)
            return _node(state)
        graph.add_node(name, metrics.measure_node(name, with_progress))
    graph.add_edge(START, 'understand')
    graph.add_edge('understand', 'assess_mind')
    graph.add_conditional_edges('assess_mind', route,
                                {'crisis': 'crisis', 'boundary': 'boundary', 'clarify': 'clarify',
                                 'retrieve': 'retrieve'})
    graph.add_conditional_edges('retrieve', lambda s: 'web_search' if wants_freshness(s) or not s['hits'] else 'generate',
                                {'generate': 'generate', 'web_search': 'web_search'})
    # Emotional support may continue with empathy alone when nothing was retrieved;
    # education questions without evidence stay "insufficient".
    graph.add_conditional_edges('web_search',
                                lambda s: 'generate' if (s.get('web_sources') or s.get('hits') or s['intent'] != 'education') else 'insufficient',
                                {'generate': 'generate', 'insufficient': 'insufficient'})
    graph.add_edge('generate', 'validate')
    graph.add_conditional_edges('validate', lambda s: 'verify_grounding' if s.get('candidates') else END,
                                {'verify_grounding': 'verify_grounding', END: END})
    graph.add_edge('verify_grounding', END)
    for terminal in ('clarify', 'crisis', 'boundary', 'insufficient'):
        graph.add_edge(terminal, END)
    try:
        state = graph.compile().invoke({})
    finally:
        logger.info('Mind execution metrics=%s', metrics.snapshot())

    return MindAnswer(
        status=state['status'], urgency=state.get('urgency'), required_action=state.get('required_action'),
        answer=state['answer'], signals=state.get('signals', []), screening=state.get('screening'),
        risk_level=state.get('risk_level'), safety_plan=state.get('safety_plan', []),
        crisis_notice=state.get('crisis_notice'), boundary=state.get('boundary'),
        advice=state.get('advice', []), red_flags_observed=state.get('red_flags_observed', []),
        triage_rule_ids=state.get('triage_rule_ids', []), missing_info=state.get('missing_info', []),
        route_suggestion=state.get('route_suggestion'), coverage=state.get('coverage'),
        missing_topics=state.get('missing_topics', []), general_info=state.get('general_info', []),
        dialogue_state=dialogue, citations=state.get('citations', []), retrieved_hits=state.get('hits', []),
        web_sources=state.get('web_sources', []), web_status=state.get('web_status', 'not_used'),
        web_warning=state.get('web_warning'), web_diagnostics=state.get('web_diagnostics'),
        answer_checks=state.get('answer_checks'), metrics=metrics.snapshot(),
        disclaimer=state.get('disclaimer', checks.DISCLAIMER), table_version=emotions.TABLE_VERSION,
        vector_count=state.get('vector_count', 0), reason=state.get('reason'),
        retrieval_log_id=state.get('log_id'), model=llm.model, knowledge_scope=kb_ids, steps=state['steps'])


def _evaluate_review(review: MindReview, paragraphs: list[MindParagraph],
                     evidence_by_index: dict[int, dict]) -> list[MindParagraph]:
    if len(review.assessments) != len(paragraphs):
        raise ValueError('review_coverage')
    if {item.paragraph for item in review.assessments} != set(range(1, len(paragraphs) + 1)):
        raise ValueError('review_coverage')
    accepted: list[MindParagraph] = []
    for item in sorted(review.assessments, key=lambda entry: entry.paragraph):
        paragraph = paragraphs[item.paragraph - 1]
        if not item.supported or item.reason != 'supported' or not item.addresses_question: continue
        if paragraph.kind == 'empathy':
            # Empathy carries no factual claim, so no quote is required.
            accepted.append(paragraph)
            continue
        if not item.quotes: continue
        valid = True
        for quote in item.quotes:
            source = evidence_by_index.get(quote.source_index)
            if quote.source_index not in paragraph.sources or source is None:
                valid = False; break
            text = source['text']
            if quote.span_ids:
                spans = {span['span'] for span in evidence_spans(text)}
                if any(index not in spans for index in quote.span_ids):
                    valid = False; break
            elif not quote.text.strip() or normalized(quote.text) not in normalized(text):
                valid = False; break
        if valid: accepted.append(paragraph)
    return accepted


__all__ = ['run_mind', 'MindState']
