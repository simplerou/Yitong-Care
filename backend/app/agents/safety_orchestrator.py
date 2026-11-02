"""Request-scoped safety workflow. Post-fall triage and dimensions are code-owned."""
import logging
import re
from datetime import date
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from app.core.exceptions import BusinessError
from app.schemas.chat import Citation
from app.schemas.safety import (
    AdviceItem, HazardFinding, PostFallFinding, RiskFactor, RouteSuggestion, SafetyAnswer, SafetyAssessment,
    SafetyDraft, SafetyParagraph, SafetyProfile, SafetyQuestion, SafetyReview, SafetyTriage, SafetyUnderstanding,
)
from app.schemas.retrieval import SearchRequest
from app.services.chat.grounding import evidence_spans, normalized
from app.services.chat.metrics import MeasuredLLM, PolicyMetrics as SafetyMetrics
from app.services.retrieval import hybrid
from app.services.safety import answer_scope, checks, hazards as hazard_rules, postfall, triage as triage_rules
from app.services.safety.dialogue_state import build_dialogue, infer_profile

logger = logging.getLogger(__name__)

SCOPE_TEXT = '我是安全守护，可以帮您做居家防跌倒改造、跌倒后应急处置、独居与夜间防护、助行器选择和平衡训练的一般建议。'
ROUTE_REASONS = {
    'health': '疾病诊断和指标解读属于健康管家的范围。',
    'medication': '药物剂量与调整属于用药管家的范围。',
    'policy': '补贴、长期护理保险与报销属于政策顾问的范围。',
    'diet': '膳食与营养问题属于膳食营养师的范围。',
    'mind': '情绪与社交问题属于心灵陪伴的范围。',
    'none': '这个问题不属于安全守护的服务范围。',
}
BOUNDARY_INTENTS = {'rehab_prescription', 'construction_quote', 'restraint'}
REHAB = re.compile(r'康复处方|训练处方|每天\s*\d+\s*组|每次\s*\d+\s*个|疗程')
QUOTE = re.compile(r'报价|多少钱|材料费|包工包料|施工队|人工费')
RESTRAINT = re.compile(r'约束带|绑起来|约束(?:带|住)|捆住')
FRESHNESS = re.compile(r'最新|新版|更新|修订|2024|2025|2026')


class SafetyState(TypedDict, total=False):
    decision: SafetyUnderstanding
    assessment: SafetyAssessment
    triage: SafetyTriage
    intent: str
    hazards: list
    risk_factors: list
    risk_level: str
    post_fall: list
    post_fall_advice: str | None
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


def run_safety(request: SafetyQuestion, db, embedder, manager, llm, kb_ids: list[str],
               web=None, trace=None, progress=None) -> SafetyAnswer:
    metrics = SafetyMetrics()
    llm = MeasuredLLM(llm, metrics)
    llm.ensure_configured()
    history = [turn.model_dump() for turn in request.history]
    user_history = [turn.content for turn in request.history if turn.role == 'user']
    text_all = request.question + '\n' + '\n'.join(user_history)
    profile = infer_profile(request.profile, text_all)
    dialogue = request.dialogue_state or build_dialogue([*user_history, request.question], profile=profile)

    def understand(state):
        payload = {'question': request.question, 'history': history,
                   'profile': profile.model_dump(mode='json'),
                   'dialogue_state': dialogue.model_dump(mode='json'),
                   'today': date.today().isoformat()}
        decision = None
        for attempt in range(2):
            raw = llm.complete_json(prompts_module().UNDERSTAND, payload)
            try:
                decision = SafetyUnderstanding.model_validate(raw)
                break
            except ValidationError as error:
                issues = [{'field': '.'.join(map(str, item['loc'])), 'type': item['type']} for item in error.errors()]
                logger.warning('Safety understanding schema mismatch attempt=%s issues=%s', attempt + 1, issues)
                if attempt:
                    raise BusinessError('模型返回的问题分析格式不符合要求，请重试。', 502) from None
                payload = {**payload, 'format_retry': {
                    'instruction': '上次输出未通过结构校验。请重新分析原问题，严格遵守 JSON 字段类型，只填当前分支需要的字段。',
                    'issues': issues}}
        if not decision.supported and decision.needs_clarification and not decision.clarification:
            decision = decision.model_copy(update={'clarification': SCOPE_TEXT})
        if trace: trace('understanding', decision.model_dump())
        return {'decision': decision, 'steps': ['understand']}

    def extract_hazards(state):
        hazard_list, risk_factors, risk_level = hazard_rules.assess(text_all, profile)
        post_fall = postfall.assess_post_fall(text_all, profile)
        assessment = SafetyAssessment(hazards=hazard_list, risk_factors=risk_factors, risk_level=risk_level,
                                      post_fall=post_fall, table_version=hazard_rules.TABLE_VERSION)
        # Deterministic intent guard: a mislabelled request must not bypass the boundary.
        intent = state['decision'].intent
        if RESTRAINT.search(request.question): intent = 'restraint'
        elif QUOTE.search(request.question): intent = 'construction_quote'
        elif REHAB.search(request.question): intent = 'rehab_prescription'
        if trace: trace('safety', {'hazards': [item.id for item in hazard_list],
                                   'factors': [item.id for item in risk_factors],
                                   'risk_level': risk_level, 'post_fall': [item.id for item in post_fall],
                                   'intent': intent})
        return {'assessment': assessment, 'intent': intent, 'hazards': hazard_list,
                'risk_factors': risk_factors, 'risk_level': risk_level, 'post_fall': post_fall,
                'steps': state['steps'] + ['extract_hazards']}

    def assess_safety(state):
        result = triage_rules.triage(text_all, state['assessment'], profile)
        if trace: trace('triage', result.model_dump(mode='json'))
        return {'triage': result, 'steps': state['steps'] + ['assess_safety']}

    def route(state):
        triage = state['triage']
        assessment = state['assessment']
        decision = state['decision']
        intent = state['intent']
        if triage.level == 'L1': return 'emergency'
        if intent in BOUNDARY_INTENTS: return 'boundary'
        if not decision.supported: return 'clarify'
        if decision.needs_clarification and not assessment.hazards and not assessment.risk_factors:
            return 'clarify'
        return 'retrieve'

    def base_fields(state):
        triage = state['triage']
        assessment = state['assessment']
        fall_advice = postfall.POST_FALL_ADVICE if assessment.post_fall else None
        return dict(urgency=triage.level, required_action=triage.required_action,
                    hazards=assessment.hazards, risk_factors=assessment.risk_factors,
                    risk_level=assessment.risk_level, post_fall=assessment.post_fall,
                    post_fall_advice=fall_advice,
                    red_flags_observed=triage.red_flags, triage_rule_ids=triage.rule_ids,
                    dialogue_state=dialogue, table_version=hazard_rules.TABLE_VERSION,
                    model=llm.model, knowledge_scope=kb_ids, web_status=state.get('web_status', 'not_used'),
                    web_warning=state.get('web_warning'), web_sources=state.get('web_sources', []),
                    web_diagnostics=state.get('web_diagnostics'), vector_count=state.get('vector_count', 0),
                    retrieved_hits=state.get('hits', []), citations=state.get('citations', []),
                    retrieval_log_id=state.get('log_id'), steps=state['steps'])

    def emergency(state):
        triage = state['triage']
        return {**base_fields(state), 'status': 'emergency', 'reason': 'red_flag',
                'answer': checks.emergency_text(triage, state['assessment']),
                'disclaimer': checks.DISCLAIMER, 'answer_checks': None, 'boundary': None, 'advice': [],
                'steps': state['steps'] + ['emergency']}

    def boundary(state):
        assessment = state['assessment']
        text = checks.boundary_text(state['intent'])
        parts = [text]
        for block in (checks.hazards_block(assessment), checks.risk_block(assessment)):
            if block: parts.append(block)
        parts.append(checks.EMERGENCY_CHECKLIST)
        parts.append(checks.DISCLAIMER)
        return {**base_fields(state), 'status': 'boundary', 'reason': f'{state["intent"]}_not_allowed',
                'answer': '\n\n'.join(parts), 'boundary': text, 'disclaimer': checks.DISCLAIMER,
                'advice': [], 'steps': state['steps'] + ['boundary']}

    def clarify(state):
        decision = state['decision']
        assessment = state['assessment']
        if not decision.supported:
            text = decision.clarification or SCOPE_TEXT
            suggestion = None
            if decision.route not in {'safety', 'none'}:
                text = text + '\n\n' + ROUTE_REASONS[decision.route]
                suggestion = RouteSuggestion(agent=decision.route, reason=ROUTE_REASONS[decision.route])
        else:
            text = decision.clarification or '请补充是哪个房间、地面是否防滑、老人是否独居，以及过去一年是否跌倒过。'
            suggestion = None
        parts = [block for block in (checks.hazards_block(assessment), checks.risk_block(assessment), text) if block]
        parts.append(checks.EMERGENCY_CHECKLIST)
        parts.append(checks.DISCLAIMER)
        return {**base_fields(state), 'status': 'clarification',
                'reason': 'outside_scope' if not decision.supported else 'missing_conditions',
                'answer': '\n\n'.join(parts), 'route_suggestion': suggestion, 'disclaimer': checks.DISCLAIMER,
                'advice': [], 'steps': state['steps'] + ['clarify']}

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

    def support_for(paragraph, by_index, assessment) -> str:
        cited = '\n'.join(by_index.get(index, '') for index in paragraph.sources)
        return cited + '\n' + checks.hazard_support(assessment)

    def generate(state):
        evidence = evidence_for(state)
        assessment = state['assessment']
        payload = {'question': state['decision'].query or request.question, 'user_question': request.question,
                   'intent': state['intent'], 'profile': profile.model_dump(mode='json'),
                   'assessment': assessment.model_dump(mode='json'),
                   'evidence': evidence, 'today': date.today().isoformat(),
                   'freshness_requested': wants_freshness(state),
                   'web_status': state.get('web_status', 'not_used'), 'web_warning': state.get('web_warning')}
        by_index = {item['index']: item['text'] for item in evidence}
        draft = None
        rejection = ''
        for attempt in range(2):
            raw = llm.complete_json(prompts_module().GENERATE, payload, max_tokens=1800)
            try:
                draft = SafetyDraft.model_validate(raw)
                if draft.sufficient:
                    if not draft.paragraphs: raise ValueError('empty_paragraphs')
                    for paragraph in draft.paragraphs:
                        if not paragraph.text.strip() or re.search(r'【.*?】', paragraph.text):
                            raise ValueError('citation_format')
                        if any(index < 1 or index > len(evidence) for index in paragraph.sources):
                            raise ValueError('citation_range')
                        support = support_for(paragraph, by_index, assessment)
                        if checks.paragraph_issues(paragraph, state['triage'].level, support):
                            raise ValueError('unsafe_paragraph')
                break
            except (ValidationError, ValueError) as error:
                rejection = str(error)
                if trace: trace('generation_rejection', {'attempt': attempt + 1, 'error': rejection})
                draft = SafetyDraft(sufficient=False, coverage='partial', paragraphs=[])
                if not attempt:
                    payload = {**payload, 'format_retry': {
                        'instruction': '上次输出未通过格式、引用或安全校验。只输出规定 JSON；'
                                       '跌倒后先说明不要急着扶起，怀疑髋部或脊柱损伤或意识不清时不要搬动并拨打 120；'
                                       '不写康复组数疗程、不写改造报价、不诊断骨折；'
                                       '尺寸只能引用 assessment 或 evidence 中的数值；每段 sources 用 evidence 整数编号。',
                        'issues': [rejection]}}
        if trace: trace('generation', draft.model_dump())
        return {'draft': draft.model_dump(), 'rejection': rejection, 'steps': state['steps'] + ['generate']}

    def validate(state):
        draft = SafetyDraft.model_validate(state['draft'])
        assessment = state['assessment']
        if not draft.sufficient:
            rejection = state.get('rejection', '')
            if 'unsafe_paragraph' in rejection: return insufficient(state, 'unsafe_paragraph')
            if rejection: return insufficient(state, 'invalid_output')
            return insufficient(state, 'model_insufficient')
        evidence = evidence_for(state)
        by_index = {item['index']: item['text'] for item in evidence}
        candidates: list[SafetyParagraph] = []
        withheld: list[str] = []
        for paragraph in draft.paragraphs:
            if not paragraph.text.strip() or re.search(r'【.*?】', paragraph.text):
                withheld.append('citation_format'); continue
            if any(index < 1 or index > len(evidence) for index in paragraph.sources):
                withheld.append('citation_range'); continue
            support = support_for(paragraph, by_index, assessment)
            issues = checks.paragraph_issues(paragraph, state['triage'].level, support)
            if issues:
                withheld.extend(issues); continue
            candidates.append(paragraph)
        if not candidates:
            return insufficient(state, 'unsafe_paragraph' if withheld else 'invalid_output')
        return {'candidates': candidates, 'withheld': withheld, 'steps': state['steps'] + ['validate']}

    def verify_grounding(state):
        candidates = state['candidates']
        evidence = evidence_for(state)
        evidence_by_index = {item['index']: item for item in evidence}
        payload = {'question': state['decision'].query or request.question, 'user_question': request.question,
                   'intent': state['intent'], 'profile': profile.model_dump(mode='json'),
                   'assessment': state['assessment'].model_dump(mode='json'),
                   'triage': {'level': state['triage'].level},
                   'paragraphs': [{'paragraph': i, 'text': p.text, 'sources': p.sources}
                                  for i, p in enumerate(candidates, 1)],
                   'evidence': [dict(item, spans=evidence_spans(item['text'])) for item in evidence
                                if any(item['index'] in p.sources for p in candidates)]}
        try:
            raw = llm.review_json(prompts_module().GENERATE_REVIEW, payload)
            review = SafetyReview.model_validate(raw)
            accepted = _evaluate_review(review, candidates, evidence_by_index)
        except (ValidationError, ValueError) as error:
            logger.warning('Safety grounding review unusable type=%s', type(error).__name__)
            return insufficient(state, 'grounding_review_failed')
        if not accepted:
            result = insufficient(state, 'unsupported_safety_claim')
            result['answer_checks'] = {'status': 'blocked', 'checked_paragraphs': len(candidates),
                                       'accepted_paragraphs': 0, 'issues': ['no_supported_paragraph']}
            return result
        return finish(state, accepted)

    def insufficient(state, reason=None):
        assessment = state['assessment']
        triage = state['triage']
        reason = reason or ('no_hits' if not state.get('hits') else 'invalid_output')
        answer = checks.insufficient_text(assessment, triage, reason)
        if state.get('web_warning'): answer += '\n\n' + state['web_warning']
        return {**base_fields(state), 'status': 'insufficient', 'reason': reason, 'answer': answer,
                'citations': [], 'coverage': 'none', 'missing_topics': ['full_safety_scope'],
                'disclaimer': checks.DISCLAIMER, 'boundary': None, 'advice': [],
                'answer_checks': state.get('answer_checks'), 'steps': state['steps'] + ['insufficient']}

    def finish(state, accepted: list[SafetyParagraph]):
        assessment = state['assessment']
        evidence_count = len(state.get('hits', []))
        used: set[int] = set()
        rendered = []
        advice: list[AdviceItem] = []
        for paragraph in accepted:
            indices = sorted(set(paragraph.sources))
            used.update(indices)
            text = paragraph.text.strip()
            stray = re.search(r'(\d{1,2})([。！？])$', text)
            if stray and int(stray[1]) in indices:
                text = text[:stray.start()] + stray[2]
            rendered.append(text + ''.join(f'【{index}】' for index in indices))
            advice.append(AdviceItem(kind=paragraph.kind, text=text, sources=indices))
        citations = []
        for index in sorted(used):
            if index <= evidence_count:
                citations.append(Citation(index=index, hit=state['hits'][index - 1]))
            else:
                citations.append(Citation(index=index, source_type='web',
                                          web=state['web_sources'][index - evidence_count - 1]))
        parts = []
        for block in (checks.hazards_block(assessment), checks.risk_block(assessment),
                      checks.postfall_block(assessment.post_fall)):
            if block: parts.append(block)
        if assessment.post_fall: parts.append(postfall.POST_FALL_ADVICE)
        parts.extend(rendered)
        referral = checks.referral_text(state['triage'])
        if referral: parts.append(referral)
        parts.append(checks.EMERGENCY_CHECKLIST)
        if state.get('web_warning'): parts.append(state['web_warning'])
        parts.append(checks.DISCLAIMER)
        draft = SafetyDraft.model_validate(state['draft'])
        return {**base_fields(state), 'status': 'answered', 'reason': 'grounded_answer',
                'answer': '\n\n'.join(parts), 'citations': citations, 'advice': advice, 'boundary': None,
                'coverage': draft.coverage, 'missing_topics': draft.missing_topics,
                'general_info': answer_scope.concept_help(request.question) if draft.coverage == 'partial' else [],
                'answer_checks': {'status': 'partial' if state.get('withheld') else 'passed',
                                  'checked_paragraphs': len(state['candidates']),
                                  'accepted_paragraphs': len(accepted), 'issues': state.get('withheld', []),
                                  'review_attempts': 1},
                'steps': state['steps'] + ['verify_grounding']}

    graph = StateGraph(SafetyState)
    for name, node in [('understand', understand), ('extract_hazards', extract_hazards),
                       ('assess_safety', assess_safety), ('emergency', emergency), ('boundary', boundary),
                       ('clarify', clarify), ('retrieve', retrieve), ('web_search', web_search),
                       ('generate', generate), ('validate', validate),
                       ('verify_grounding', verify_grounding), ('insufficient', insufficient)]:
        def with_progress(state, _name=name, _node=node):
            if progress: progress(_name)
            return _node(state)
        graph.add_node(name, metrics.measure_node(name, with_progress))
    graph.add_edge(START, 'understand')
    graph.add_edge('understand', 'extract_hazards')
    graph.add_edge('extract_hazards', 'assess_safety')
    graph.add_conditional_edges('assess_safety', route,
                                {'emergency': 'emergency', 'boundary': 'boundary', 'clarify': 'clarify',
                                 'retrieve': 'retrieve'})
    graph.add_conditional_edges('retrieve', lambda s: 'web_search' if wants_freshness(s) or not s['hits'] else 'generate',
                                {'generate': 'generate', 'web_search': 'web_search'})
    graph.add_conditional_edges('web_search', lambda s: 'generate' if s.get('web_sources') or s.get('hits') else 'insufficient',
                                {'generate': 'generate', 'insufficient': 'insufficient'})
    graph.add_edge('generate', 'validate')
    graph.add_conditional_edges('validate', lambda s: 'verify_grounding' if s.get('candidates') else END,
                                {'verify_grounding': 'verify_grounding', END: END})
    graph.add_edge('verify_grounding', END)
    for terminal in ('clarify', 'emergency', 'boundary', 'insufficient'):
        graph.add_edge(terminal, END)
    try:
        state = graph.compile().invoke({})
    finally:
        logger.info('Safety execution metrics=%s', metrics.snapshot())

    return SafetyAnswer(
        status=state['status'], urgency=state.get('urgency'), required_action=state.get('required_action'),
        answer=state['answer'], hazards=state.get('hazards', []), risk_factors=state.get('risk_factors', []),
        risk_level=state.get('risk_level'), post_fall=state.get('post_fall', []),
        post_fall_advice=state.get('post_fall_advice'), boundary=state.get('boundary'),
        advice=state.get('advice', []), red_flags_observed=state.get('red_flags_observed', []),
        triage_rule_ids=state.get('triage_rule_ids', []), missing_info=state.get('missing_info', []),
        route_suggestion=state.get('route_suggestion'), coverage=state.get('coverage'),
        missing_topics=state.get('missing_topics', []), general_info=state.get('general_info', []),
        dialogue_state=dialogue, citations=state.get('citations', []), retrieved_hits=state.get('hits', []),
        web_sources=state.get('web_sources', []), web_status=state.get('web_status', 'not_used'),
        web_warning=state.get('web_warning'), web_diagnostics=state.get('web_diagnostics'),
        answer_checks=state.get('answer_checks'), metrics=metrics.snapshot(),
        disclaimer=state.get('disclaimer', checks.DISCLAIMER), table_version=hazard_rules.TABLE_VERSION,
        vector_count=state.get('vector_count', 0), reason=state.get('reason'),
        retrieval_log_id=state.get('log_id'), model=llm.model, knowledge_scope=kb_ids, steps=state['steps'])


def prompts_module():
    from app.services.safety import prompts
    return prompts


def _evaluate_review(review: SafetyReview, paragraphs: list[SafetyParagraph],
                     evidence_by_index: dict[int, dict]) -> list[SafetyParagraph]:
    if len(review.assessments) != len(paragraphs):
        raise ValueError('review_coverage')
    if {item.paragraph for item in review.assessments} != set(range(1, len(paragraphs) + 1)):
        raise ValueError('review_coverage')
    accepted: list[SafetyParagraph] = []
    for item in sorted(review.assessments, key=lambda entry: entry.paragraph):
        paragraph = paragraphs[item.paragraph - 1]
        if not item.supported or item.reason != 'supported' or not item.addresses_question: continue
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


__all__ = ['run_safety', 'SafetyState']
