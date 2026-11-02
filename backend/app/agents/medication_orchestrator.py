"""Request-scoped medication workflow. Interactions, dose boundaries and triage are code-owned."""
import logging
import re
from datetime import date
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from app.core.exceptions import BusinessError
from app.schemas.chat import Citation
from app.schemas.medication import (
    MedicationAnswer, MedicationAssessment, MedicationDraft, MedicationParagraph, MedicationQuestion,
    MedicationReview, MedicationTriage, MedicationUnderstanding, RouteSuggestion,
)
from app.schemas.retrieval import SearchRequest
from app.services.chat.grounding import evidence_spans, normalized
from app.services.chat.metrics import MeasuredLLM, PolicyMetrics as MedicationMetrics
from app.services.medication import answer_scope, checks, prompts
from app.services.medication import drugs as rules
from app.services.medication.dialogue_state import build_dialogue
from app.services.retrieval import hybrid

logger = logging.getLogger(__name__)

SCOPE_TEXT = '我是用药管家，可以帮您核对服药时间、漏服处理、药物相互作用风险和常见不良反应。'
ROUTE_REASONS = {
    'health': '疾病诊断和指标解读属于健康管家的范围。',
    'policy': '补贴、长期护理保险与报销属于政策顾问的范围。',
    'safety': '跌倒预防与居家改造属于安全守护的范围。',
    'diet': '具体食谱与热量安排属于膳食营养师的范围。',
    'mind': '情绪与社交问题属于心灵陪伴的范围。',
    'none': '这个问题不属于用药管家的服务范围。',
}
FRESHNESS = re.compile(r'最新|新版|更新|修订|现行|2024|2025|2026')
DOSE_REQUEST = re.compile(r'加量|减量|加一片|减一片|多吃|少吃|加倍|减半|停药|停掉|换药|换成|换一种|改药|'
                           r'(?:加|减|吃|改|换)(?:到|至|成)\s*[0-9一二三四五六七八九十两半]+\s*(?:片|粒|mg|毫克)')
STOP_REQUEST = re.compile(r'停药|停掉|换药|换成|换一种|不吃了')


class MedicationState(TypedDict, total=False):
    decision: MedicationUnderstanding
    assessment: MedicationAssessment
    triage: MedicationTriage
    topic: str
    drugs: list
    interactions: list
    unknown_names: list
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
    web_refine_found: bool
    answer_checks: dict
    urgency: str
    required_action: str
    red_flags_observed: list
    triage_rule_ids: list
    missing_info: list
    route_suggestion: RouteSuggestion | None
    boundary: str | None
    missed_dose_advice: str | None
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


def run_medication(request: MedicationQuestion, db, embedder, manager, llm, kb_ids: list[str],
                   web=None, trace=None, progress=None) -> MedicationAnswer:
    metrics = MedicationMetrics()
    llm = MeasuredLLM(llm, metrics)
    llm.ensure_configured()
    history = [turn.model_dump() for turn in request.history]
    user_history = [turn.content for turn in request.history if turn.role == 'user']
    text_all = request.question + '\n' + '\n'.join(user_history)
    dialogue = request.dialogue_state or build_dialogue([*user_history, request.question], profile=request.profile)

    def understand(state):
        payload = {'question': request.question, 'history': history,
                   'provided_medications': [item.model_dump(mode='json') for item in request.medications],
                   'profile': request.profile.model_dump(mode='json'),
                   'dialogue_state': dialogue.model_dump(mode='json'),
                   'today': date.today().isoformat()}
        decision = None
        for attempt in range(2):
            raw = llm.complete_json(prompts.UNDERSTAND, payload)
            try:
                decision = MedicationUnderstanding.model_validate(raw)
                break
            except ValidationError as error:
                issues = [{'field': '.'.join(map(str, item['loc'])), 'type': item['type']} for item in error.errors()]
                logger.warning('Medication understanding schema mismatch attempt=%s issues=%s', attempt + 1, issues)
                if attempt:
                    raise BusinessError('模型返回的问题分析格式不符合要求，请重试。', 502) from None
                payload = {**payload, 'format_retry': {
                    'instruction': '上次输出未通过结构校验。请重新分析原问题，严格遵守 JSON 字段类型，只填当前分支需要的字段。',
                    'issues': issues}}
        if decision.supported and not decision.needs_clarification and not decision.query:
            decision = decision.model_copy(update={'query': request.question})
        if not decision.supported and decision.needs_clarification and not decision.clarification:
            decision = decision.model_copy(update={'clarification': SCOPE_TEXT})
        if trace: trace('understanding', decision.model_dump())
        return {'decision': decision, 'steps': ['understand']}

    def extract_medications(state):
        provided = request.medications
        assessment = rules.assess(text_all, provided, request.profile)
        # Deterministic topic guard: a model that mislabels a dose request must not bypass the boundary.
        topic = state['decision'].topic
        if STOP_REQUEST.search(request.question): topic = 'stop_or_switch'
        elif DOSE_REQUEST.search(request.question): topic = 'dose_change'
        if trace: trace('medications', {'drugs': [d.name for d in assessment.drugs],
                                        'interactions': [f.id for f in assessment.interactions],
                                        'topic': topic, 'frequency': assessment.frequency})
        return {'assessment': assessment, 'topic': topic, 'steps': state['steps'] + ['extract_medications']}

    def screen_safety(state):
        result = rules.triage(state['assessment'], text_all, request.profile)
        if trace: trace('triage', result.model_dump(mode='json'))
        return {'triage': result, 'steps': state['steps'] + ['screen_safety']}

    def route(state):
        triage = state['triage']
        assessment = state['assessment']
        decision = state['decision']
        topic = state['topic']
        if triage.level == 'L1': return 'emergency'
        if topic in {'dose_change', 'stop_or_switch'}: return 'boundary'
        if not decision.supported: return 'clarify'
        if topic == 'interaction' and len(assessment.drugs) < 2: return 'clarify'
        if topic == 'missed_dose' and not assessment.drugs: return 'clarify'
        if decision.needs_clarification and not assessment.drugs: return 'clarify'
        return 'retrieve'

    def base_fields(state):
        triage = state['triage']
        assessment = state['assessment']
        return dict(urgency=triage.level, required_action=triage.required_action,
                    drugs=assessment.drugs, interactions=assessment.interactions,
                    unknown_names=assessment.unknown_names,
                    red_flags_observed=triage.red_flags, triage_rule_ids=triage.rule_ids,
                    dialogue_state=dialogue, table_version=rules.TABLE_VERSION,
                    model=llm.model, knowledge_scope=kb_ids, web_status=state.get('web_status', 'not_used'),
                    web_warning=state.get('web_warning'), web_sources=state.get('web_sources', []),
                    web_diagnostics=state.get('web_diagnostics'), vector_count=state.get('vector_count', 0),
                    retrieved_hits=state.get('hits', []), citations=state.get('citations', []),
                    retrieval_log_id=state.get('log_id'), steps=state['steps'])

    def emergency(state):
        triage = state['triage']
        return {**base_fields(state), 'status': 'emergency', 'reason': 'red_flag',
                'answer': checks.emergency_text(triage, state['assessment']),
                'disclaimer': checks.DISCLAIMER, 'answer_checks': None, 'boundary': None,
                'steps': state['steps'] + ['emergency']}

    def boundary(state):
        topic = state['topic']
        assessment = state['assessment']
        text = checks.boundary_text(topic)
        parts = [text]
        block = checks.drug_block(assessment)
        if block: parts.append(block)
        interactions = checks.interaction_block(assessment)
        if interactions:
            parts.append(interactions)
            note = checks.high_severity_note(assessment)
            if note: parts.append(note)
        parts.append(checks.EMERGENCY_CHECKLIST)
        parts.append(checks.DISCLAIMER)
        return {**base_fields(state), 'status': 'boundary', 'reason': f'{topic}_not_allowed',
                'answer': '\n\n'.join(parts), 'boundary': text, 'disclaimer': checks.DISCLAIMER,
                'steps': state['steps'] + ['boundary']}

    def clarify(state):
        decision = state['decision']
        assessment = state['assessment']
        if not decision.supported:
            text = decision.clarification or SCOPE_TEXT
            suggestion = None
            if decision.route not in {'medication', 'none'}:
                text = text + '\n\n' + ROUTE_REASONS[decision.route]
                suggestion = RouteSuggestion(agent=decision.route, reason=ROUTE_REASONS[decision.route])
        else:
            text = decision.clarification or _clarification(assessment, state['topic'])
            suggestion = None
        parts = [block for block in (checks.drug_block(assessment), text) if block]
        parts.append(checks.EMERGENCY_CHECKLIST)
        parts.append(checks.DISCLAIMER)
        return {**base_fields(state), 'status': 'clarification',
                'reason': 'outside_scope' if not decision.supported else 'missing_conditions',
                'answer': '\n\n'.join(parts), 'route_suggestion': suggestion, 'disclaimer': checks.DISCLAIMER,
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
                    'web_warning': '联网检索尚未配置，本次未核验说明书更新。'}
        query = answer_scope.web_query([drug.name for drug in state['assessment'].drugs], state['topic'])
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
                   'profile': request.profile.model_dump(mode='json'),
                   'topic': state['topic'],
                   'assessment': {'drugs': [drug.model_dump(mode='json') for drug in assessment.drugs],
                                  'interactions': [finding.model_dump(mode='json') for finding in assessment.interactions],
                                  'frequency': assessment.frequency},
                   'already_shown': ([finding.title for finding in assessment.interactions]
                                     + ['药物清单与常见服用时间'] if assessment.drugs else []),
                   'evidence': evidence, 'today': date.today().isoformat(),
                   'freshness_requested': wants_freshness(state),
                   'web_status': state.get('web_status', 'not_used'), 'web_warning': state.get('web_warning')}
        draft = None
        rejection = ''
        for attempt in range(2):
            raw = llm.complete_json(prompts.GENERATE, payload, max_tokens=1600)
            try:
                draft = MedicationDraft.model_validate(raw)
                if draft.sufficient:
                    if not draft.paragraphs: raise ValueError('empty_paragraphs')
                    for paragraph in draft.paragraphs:
                        if not paragraph.text.strip() or re.search(r'【.*?】', paragraph.text):
                            raise ValueError('citation_format')
                        if any(index < 1 or index > len(evidence) for index in paragraph.sources):
                            raise ValueError('citation_range')
                        if checks.paragraph_issues(paragraph, state['triage'].level):
                            raise ValueError('unsafe_paragraph')
                break
            except (ValidationError, ValueError) as error:
                rejection = str(error)
                if trace: trace('generation_rejection', {'attempt': attempt + 1, 'error': rejection})
                draft = MedicationDraft(sufficient=False, coverage='partial', paragraphs=[])
                if not attempt:
                    payload = {**payload, 'format_retry': {
                        'instruction': '上次输出未通过格式、引用或用药安全校验。只输出规定 JSON；'
                                       '不写任何剂量、片数或服药次数；不建议加减量、停药或换药；'
                                       '不断言可以同服或没有相互作用；每段 sources 用 evidence 整数编号；'
                                       '资料不足可返回 sufficient=false。',
                        'issues': [rejection]}}
        if trace: trace('generation', draft.model_dump())
        return {'draft': draft.model_dump(), 'rejection': rejection, 'steps': state['steps'] + ['generate']}

    def validate(state):
        draft = MedicationDraft.model_validate(state['draft'])
        if not draft.sufficient:
            rejection = state.get('rejection', '')
            if 'dose_advice' in rejection or 'unsafe_paragraph' in rejection:
                return insufficient(state, 'unsafe_paragraph')
            if rejection: return insufficient(state, 'invalid_output')
            return insufficient(state, 'model_insufficient')
        evidence = evidence_for(state)
        candidates: list[MedicationParagraph] = []
        withheld: list[str] = []
        for paragraph in draft.paragraphs:
            if not paragraph.text.strip() or re.search(r'【.*?】', paragraph.text):
                withheld.append('citation_format'); continue
            if any(index < 1 or index > len(evidence) for index in paragraph.sources):
                withheld.append('citation_range'); continue
            issues = checks.paragraph_issues(paragraph, state['triage'].level)
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
                   'topic': state['topic'],
                   'assessment': {'drugs': [drug.model_dump(mode='json') for drug in state['assessment'].drugs],
                                  'interactions': [finding.model_dump(mode='json') for finding in state['assessment'].interactions]},
                   'triage': {'level': state['triage'].level},
                   'paragraphs': [{'paragraph': i, 'text': p.text, 'sources': p.sources}
                                  for i, p in enumerate(candidates, 1)],
                   'evidence': [dict(item, spans=evidence_spans(item['text'])) for item in evidence
                                if any(item['index'] in p.sources for p in candidates)]}
        try:
            raw = llm.review_json(prompts.GENERATE_REVIEW, payload)
            review = MedicationReview.model_validate(raw)
            accepted = _evaluate_review(review, candidates, evidence_by_index)
        except (ValidationError, ValueError) as error:
            logger.warning('Medication grounding review unusable type=%s', type(error).__name__)
            return insufficient(state, 'grounding_review_failed')
        if not accepted:
            result = insufficient(state, 'unsupported_medication_claim')
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
                'citations': [], 'coverage': 'none', 'missing_topics': ['full_medication_scope'],
                'disclaimer': checks.DISCLAIMER, 'boundary': None, 'missed_dose_advice': None,
                'answer_checks': state.get('answer_checks'), 'steps': state['steps'] + ['insufficient']}

    def finish(state, accepted: list[MedicationParagraph]):
        assessment = state['assessment']
        evidence_count = len(state.get('hits', []))
        used: set[int] = set()
        rendered = []
        for paragraph in accepted:
            indices = sorted(set(paragraph.sources))
            used.update(indices)
            text = paragraph.text.strip()
            # A model sometimes repeats the source index as prose ("...风险1。").
            stray = re.search(r'(\d{1,2})([。！？])$', text)
            if stray and int(stray[1]) in indices:
                text = text[:stray.start()] + stray[2]
            rendered.append(text + ''.join(f'【{index}】' for index in indices))
        citations = []
        for index in sorted(used):
            if index <= evidence_count:
                citations.append(Citation(index=index, hit=state['hits'][index - 1]))
            else:
                citations.append(Citation(index=index, source_type='web',
                                          web=state['web_sources'][index - evidence_count - 1]))
        parts = []
        for block in (checks.drug_block(assessment), checks.interaction_block(assessment)):
            if block: parts.append(block)
        note = checks.high_severity_note(assessment)
        if note: parts.append(note)
        parts.extend(rendered)
        missed = None
        if state['topic'] == 'missed_dose':
            missed = rules.missed_dose_advice(assessment)
            parts.append(missed + '\n' + checks.MISSED_DOSE_NOTE)
        referral = checks.referral_text(state['triage'])
        if referral: parts.append(referral)
        parts.append(checks.EMERGENCY_CHECKLIST)
        if state.get('web_warning'): parts.append(state['web_warning'])
        parts.append(checks.DISCLAIMER)
        draft = MedicationDraft.model_validate(state['draft'])
        return {**base_fields(state), 'status': 'answered', 'reason': 'grounded_answer',
                'answer': '\n\n'.join(parts), 'citations': citations,
                'missed_dose_advice': missed, 'boundary': None,
                'coverage': draft.coverage, 'missing_topics': draft.missing_topics,
                'general_info': answer_scope.concept_help(request.question) if draft.coverage == 'partial' else [],
                'answer_checks': {'status': 'partial' if state.get('withheld') else 'passed',
                                  'checked_paragraphs': len(state['candidates']),
                                  'accepted_paragraphs': len(accepted), 'issues': state.get('withheld', []),
                                  'review_attempts': 1},
                'steps': state['steps'] + ['verify_grounding']}

    graph = StateGraph(MedicationState)
    for name, node in [('understand', understand), ('extract_medications', extract_medications),
                       ('screen_safety', screen_safety), ('emergency', emergency), ('boundary', boundary),
                       ('clarify', clarify), ('retrieve', retrieve), ('web_search', web_search),
                       ('generate', generate), ('validate', validate),
                       ('verify_grounding', verify_grounding), ('insufficient', insufficient)]:
        def with_progress(state, _name=name, _node=node):
            if progress: progress(_name)
            return _node(state)
        graph.add_node(name, metrics.measure_node(name, with_progress))
    graph.add_edge(START, 'understand')
    graph.add_edge('understand', 'extract_medications')
    graph.add_edge('extract_medications', 'screen_safety')
    graph.add_conditional_edges('screen_safety', route,
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
        logger.info('Medication execution metrics=%s', metrics.snapshot())

    return MedicationAnswer(
        status=state['status'], urgency=state.get('urgency'), required_action=state.get('required_action'),
        answer=state['answer'], drugs=state.get('drugs', []), interactions=state.get('interactions', []),
        unknown_names=state.get('unknown_names', []), missed_dose_advice=state.get('missed_dose_advice'),
        boundary=state.get('boundary'), red_flags_observed=state.get('red_flags_observed', []),
        triage_rule_ids=state.get('triage_rule_ids', []), missing_info=state.get('missing_info', []),
        route_suggestion=state.get('route_suggestion'), coverage=state.get('coverage'),
        missing_topics=state.get('missing_topics', []), general_info=state.get('general_info', []),
        dialogue_state=dialogue, citations=state.get('citations', []), retrieved_hits=state.get('hits', []),
        web_sources=state.get('web_sources', []), web_status=state.get('web_status', 'not_used'),
        web_warning=state.get('web_warning'), web_diagnostics=state.get('web_diagnostics'),
        answer_checks=state.get('answer_checks'), metrics=metrics.snapshot(),
        disclaimer=state.get('disclaimer', checks.DISCLAIMER), table_version=rules.TABLE_VERSION,
        vector_count=state.get('vector_count', 0), reason=state.get('reason'),
        retrieval_log_id=state.get('log_id'), model=llm.model, knowledge_scope=kb_ids, steps=state['steps'])


def _clarification(assessment: MedicationAssessment, topic: str) -> str:
    if topic == 'interaction':
        return '请补充您正在同时使用的另一种药（或保健品）的名称，我才能核对相互作用风险。'
    if topic == 'missed_dose':
        return '请补充漏服的是哪种药、每天服用几次，以及上次服药的时间。'
    if topic == 'adverse_reaction':
        return '请补充具体症状、出现时间，以及最近开始服用或调整的药名。'
    if topic == 'duplication':
        return '请补充您正在服用的所有感冒药、退烧药和止痛药的名称，我帮您核对是否含相同成分。'
    return '请补充涉及的具体药名，以及您想了解的用药问题。'


def _evaluate_review(review: MedicationReview, paragraphs: list[MedicationParagraph],
                     evidence_by_index: dict[int, dict]) -> list[MedicationParagraph]:
    if len(review.assessments) != len(paragraphs):
        raise ValueError('review_coverage')
    if {item.paragraph for item in review.assessments} != set(range(1, len(paragraphs) + 1)):
        raise ValueError('review_coverage')
    accepted: list[MedicationParagraph] = []
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


__all__ = ['run_medication', 'MedicationState']
