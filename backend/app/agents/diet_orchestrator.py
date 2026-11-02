"""Request-scoped dietitian workflow. Portions, allergies and triage are code-owned."""
import logging
import re
from datetime import date
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from app.core.exceptions import BusinessError
from app.schemas.chat import Citation
from app.schemas.diet import (
    AdviceItem, DietAnswer, DietDraft, DietParagraph, DietQuestion, DietReview, DietTriage,
    DietUnderstanding, NutritionAssessment, PortionReference, RouteSuggestion,
)
from app.schemas.retrieval import SearchRequest
from app.services.chat.grounding import evidence_spans, normalized
from app.services.chat.metrics import MeasuredLLM, PolicyMetrics as DietMetrics
from app.services.diet import answer_scope, checks, prompts
from app.services.diet import foods as food_rules
from app.services.diet import nutrition, triage as triage_rules
from app.services.diet.dialogue_state import build_dialogue, infer_profile
from app.services.retrieval import hybrid

logger = logging.getLogger(__name__)

SCOPE_TEXT = '我是膳食营养师，可以帮您安排一日三餐、补充蛋白质、控盐控油控糖，以及调整食物的质地和做法。'
ROUTE_REASONS = {
    'health': '指标解读和就医时机属于健康管家的范围。',
    'medication': '药物剂量、漏服和相互作用属于用药管家的范围。',
    'policy': '补贴、长期护理保险与报销属于政策顾问的范围。',
    'safety': '跌倒预防与居家改造属于安全守护的范围。',
    'mind': '情绪与社交问题属于心灵陪伴的范围。',
    'none': '这个问题不属于膳食营养师的服务范围。',
}
BOUNDARY_INTENTS = {'prescription_diet', 'supplement_dose', 'extreme_diet', 'replace_medication'}
SUPPLEMENT = re.compile(r'蛋白粉|乳清蛋白|肠内营养|营养液|营养剂|剂量|怎么补.*粉')
EXTREME = re.compile(r'生酮|断食|辟谷|排毒|只吃一种|单一饮食')
REPLACE_MED = re.compile(r'替代药物|代替药|不吃药|停药|停掉药')
PRESCRIPTION = re.compile(r'治疗食谱|饮食处方|肾病食谱|肝病食谱|肿瘤营养|给我.*处方|治好')
PORTION_INTENTS = {'meal_plan', 'protein', 'salt_control', 'condition_diet', 'fruit_staple'}
FRESHNESS = re.compile(r'最新|新版|更新|修订|2024|2025|2026')


class DietState(TypedDict, total=False):
    decision: DietUnderstanding
    assessment: NutritionAssessment
    triage: DietTriage
    intent: str
    foods: list
    findings: list
    unknown_foods: list
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
    portion_reference: PortionReference | None
    nutrition_risks: list
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


def run_diet(request: DietQuestion, db, embedder, manager, llm, kb_ids: list[str],
             web=None, trace=None, progress=None) -> DietAnswer:
    metrics = DietMetrics()
    llm = MeasuredLLM(llm, metrics)
    llm.ensure_configured()
    history = [turn.model_dump() for turn in request.history]
    user_history = [turn.content for turn in request.history if turn.role == 'user']
    text_all = request.question + '\n' + '\n'.join(user_history)
    profile = infer_profile(request.profile, text_all)
    dialogue = request.dialogue_state or build_dialogue([*user_history, request.question], profile=profile)

    def understand(state):
        payload = {'question': request.question, 'history': history,
                   'provided_foods': [item.model_dump(mode='json') for item in request.foods],
                   'profile': profile.model_dump(mode='json'),
                   'dialogue_state': dialogue.model_dump(mode='json'),
                   'today': date.today().isoformat()}
        decision = None
        for attempt in range(2):
            raw = llm.complete_json(prompts.UNDERSTAND, payload)
            try:
                decision = DietUnderstanding.model_validate(raw)
                break
            except ValidationError as error:
                issues = [{'field': '.'.join(map(str, item['loc'])), 'type': item['type']} for item in error.errors()]
                logger.warning('Diet understanding schema mismatch attempt=%s issues=%s', attempt + 1, issues)
                if attempt:
                    raise BusinessError('模型返回的问题分析格式不符合要求，请重试。', 502) from None
                payload = {**payload, 'format_retry': {
                    'instruction': '上次输出未通过结构校验。请重新分析原问题，严格遵守 JSON 字段类型，只填当前分支需要的字段。',
                    'issues': issues}}
        if not decision.supported and decision.needs_clarification and not decision.clarification:
            decision = decision.model_copy(update={'clarification': SCOPE_TEXT})
        if trace: trace('understanding', decision.model_dump())
        return {'decision': decision, 'steps': ['understand']}

    def extract_foods(state):
        mentions, unknown = food_rules.extract(text_all, request.foods)
        assessment = nutrition.assess(text_all, mentions, unknown, profile)
        # Deterministic intent guard: a mislabelled request must not bypass the boundary.
        intent = state['decision'].intent
        if EXTREME.search(request.question): intent = 'extreme_diet'
        elif SUPPLEMENT.search(request.question): intent = 'supplement_dose'
        elif REPLACE_MED.search(request.question): intent = 'replace_medication'
        elif PRESCRIPTION.search(request.question): intent = 'prescription_diet'
        if trace: trace('diet', {'foods': [food.name for food in mentions],
                                 'findings': [finding.id for finding in assessment.findings],
                                 'intent': intent, 'salt_load': assessment.salt_load,
                                 'bmi': assessment.bmi})
        return {'assessment': assessment, 'intent': intent, 'steps': state['steps'] + ['extract_foods']}

    def assess_nutrition(state):
        result = triage_rules.triage(text_all, state['assessment'], profile)
        if trace: trace('triage', result.model_dump(mode='json'))
        return {'triage': result, 'steps': state['steps'] + ['assess_nutrition']}

    def route(state):
        triage = state['triage']
        assessment = state['assessment']
        decision = state['decision']
        intent = state['intent']
        if triage.level == 'L1': return 'emergency'
        if intent in BOUNDARY_INTENTS: return 'boundary'
        if not decision.supported: return 'clarify'
        if decision.needs_clarification and not assessment.foods and not profile.conditions:
            return 'clarify'
        return 'retrieve'

    def base_fields(state):
        triage = state['triage']
        assessment = state['assessment']
        return dict(urgency=triage.level, required_action=triage.required_action,
                    foods=assessment.foods, findings=assessment.findings, unknown_foods=assessment.unknown_foods,
                    nutrition_risks=nutrition.risk_labels(assessment),
                    red_flags_observed=triage.red_flags, triage_rule_ids=triage.rule_ids,
                    dialogue_state=dialogue, table_version=food_rules.TABLE_VERSION,
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
                'portion_reference': None, 'advice': [], 'steps': state['steps'] + ['emergency']}

    def boundary(state):
        assessment = state['assessment']
        text = checks.boundary_text(state['intent'])
        parts = [text]
        for block in (checks.food_block(assessment), checks.findings_block(assessment)):
            if block: parts.append(block)
        parts.append(checks.EMERGENCY_CHECKLIST)
        parts.append(checks.DISCLAIMER)
        return {**base_fields(state), 'status': 'boundary', 'reason': f'{state["intent"]}_not_allowed',
                'answer': '\n\n'.join(parts), 'boundary': text, 'disclaimer': checks.DISCLAIMER,
                'portion_reference': None, 'advice': [], 'steps': state['steps'] + ['boundary']}

    def clarify(state):
        decision = state['decision']
        assessment = state['assessment']
        if not decision.supported:
            text = decision.clarification or SCOPE_TEXT
            suggestion = None
            if decision.route not in {'diet', 'none'}:
                text = text + '\n\n' + ROUTE_REASONS[decision.route]
                suggestion = RouteSuggestion(agent=decision.route, reason=ROUTE_REASONS[decision.route])
        else:
            text = decision.clarification or _clarification(state['intent'])
            suggestion = None
        parts = [block for block in (checks.food_block(assessment), checks.findings_block(assessment), text) if block]
        parts.append(checks.EMERGENCY_CHECKLIST)
        parts.append(checks.DISCLAIMER)
        return {**base_fields(state), 'status': 'clarification',
                'reason': 'outside_scope' if not decision.supported else 'missing_conditions',
                'answer': '\n\n'.join(parts), 'route_suggestion': suggestion, 'disclaimer': checks.DISCLAIMER,
                'portion_reference': None, 'advice': [], 'steps': state['steps'] + ['clarify']}

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

    def portion_for(state):
        if state['intent'] in PORTION_INTENTS or state['decision'].intent in PORTION_INTENTS:
            return food_rules.portion_reference()
        return None

    def generate(state):
        evidence = evidence_for(state)
        assessment = state['assessment']
        reference = portion_for(state)
        payload = {'question': state['decision'].query or request.question, 'user_question': request.question,
                   'intent': state['intent'],
                   'profile': profile.model_dump(mode='json'),
                   'assessment': {'foods': [food.model_dump(mode='json') for food in assessment.foods],
                                  'findings': [finding.model_dump(mode='json') for finding in assessment.findings],
                                  'salt_load': assessment.salt_load, 'protein_risk': assessment.protein_risk,
                                  'produce_risk': assessment.produce_risk, 'bmi': assessment.bmi},
                   'portion_reference': reference.model_dump(mode='json') if reference else None,
                   'evidence': evidence, 'today': date.today().isoformat(),
                   'freshness_requested': wants_freshness(state),
                   'web_status': state.get('web_status', 'not_used'), 'web_warning': state.get('web_warning')}
        def support_for(paragraph, by_index, reference) -> str:
            cited = '\n'.join(by_index.get(index, '') for index in paragraph.sources)
            ranges = '\n'.join(item.range_text for item in reference.items) if reference else ''
            return cited + '\n' + ranges

        draft = None
        rejection = ''
        for attempt in range(2):
            raw = llm.complete_json(prompts.GENERATE, payload, max_tokens=1800)
            try:
                draft = DietDraft.model_validate(raw)
                if draft.sufficient:
                    if not draft.paragraphs: raise ValueError('empty_paragraphs')
                    for paragraph in draft.paragraphs:
                        if not paragraph.text.strip() or re.search(r'【.*?】', paragraph.text):
                            raise ValueError('citation_format')
                        if any(index < 1 or index > len(evidence) for index in paragraph.sources):
                            raise ValueError('citation_range')
                        support = support_for(paragraph, {item['index']: item['text'] for item in evidence}, reference)
                        if checks.paragraph_issues(paragraph, state['triage'].level, profile.allergies, support):
                            raise ValueError('unsafe_paragraph')
                break
            except (ValidationError, ValueError) as error:
                rejection = str(error)
                if trace: trace('generation_rejection', {'attempt': attempt + 1, 'error': rejection})
                draft = DietDraft(sufficient=False, coverage='partial', paragraphs=[])
                if not attempt:
                    payload = {**payload, 'format_retry': {
                        'instruction': '上次输出未通过格式、引用或膳食安全校验。只输出规定 JSON；'
                                       '不写克数、热量、毫升等份量；不写治疗处方或"治好/替代药物"；'
                                       '不推荐生酮断食；过敏食物绝对不能出现；每段 sources 用 evidence 整数编号；'
                                       '资料不足可返回 sufficient=false。',
                        'issues': [rejection]}}
        if trace: trace('generation', draft.model_dump())
        return {'draft': draft.model_dump(), 'rejection': rejection, 'steps': state['steps'] + ['generate']}

    def validate(state):
        draft = DietDraft.model_validate(state['draft'])
        if not draft.sufficient:
            rejection = state.get('rejection', '')
            if 'unsafe_paragraph' in rejection or 'diet_prescription' in rejection:
                return insufficient(state, 'unsafe_paragraph')
            if rejection: return insufficient(state, 'invalid_output')
            return insufficient(state, 'model_insufficient')
        evidence = evidence_for(state)
        by_index = {item['index']: item['text'] for item in evidence}
        reference = portion_for(state)
        candidates: list[DietParagraph] = []
        withheld: list[str] = []
        for paragraph in draft.paragraphs:
            if not paragraph.text.strip() or re.search(r'【.*?】', paragraph.text):
                withheld.append('citation_format'); continue
            if any(index < 1 or index > len(evidence) for index in paragraph.sources):
                withheld.append('citation_range'); continue
            support = (('\n'.join(by_index.get(index, '') for index in paragraph.sources))
                       + '\n' + ('\n'.join(item.range_text for item in reference.items) if reference else ''))
            issues = checks.paragraph_issues(paragraph, state['triage'].level, profile.allergies, support)
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
                   'intent': state['intent'],
                   'profile': profile.model_dump(mode='json'),
                   'assessment': {'foods': [food.model_dump(mode='json') for food in state['assessment'].foods],
                                  'findings': [finding.model_dump(mode='json') for finding in state['assessment'].findings]},
                   'triage': {'level': state['triage'].level},
                   'paragraphs': [{'paragraph': i, 'text': p.text, 'sources': p.sources}
                                  for i, p in enumerate(candidates, 1)],
                   'evidence': [dict(item, spans=evidence_spans(item['text'])) for item in evidence
                                if any(item['index'] in p.sources for p in candidates)]}
        try:
            raw = llm.review_json(prompts.GENERATE_REVIEW, payload)
            review = DietReview.model_validate(raw)
            accepted = _evaluate_review(review, candidates, evidence_by_index)
        except (ValidationError, ValueError) as error:
            logger.warning('Diet grounding review unusable type=%s', type(error).__name__)
            return insufficient(state, 'grounding_review_failed')
        if not accepted:
            result = insufficient(state, 'unsupported_diet_claim')
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
                'citations': [], 'coverage': 'none', 'missing_topics': ['full_diet_scope'],
                'disclaimer': checks.DISCLAIMER, 'boundary': None, 'portion_reference': None,
                'advice': [], 'answer_checks': state.get('answer_checks'),
                'steps': state['steps'] + ['insufficient']}

    def finish(state, accepted: list[DietParagraph]):
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
        reference = portion_for(state)
        parts = []
        for block in (checks.food_block(assessment), checks.findings_block(assessment), checks.risk_block(assessment)):
            if block: parts.append(block)
        if reference: parts.append(checks.portion_block(reference))
        parts.extend(rendered)
        referral = checks.referral_text(state['triage'])
        if referral: parts.append(referral)
        parts.append(checks.EMERGENCY_CHECKLIST)
        if state.get('web_warning'): parts.append(state['web_warning'])
        parts.append(checks.DISCLAIMER)
        draft = DietDraft.model_validate(state['draft'])
        return {**base_fields(state), 'status': 'answered', 'reason': 'grounded_answer',
                'answer': '\n\n'.join(parts), 'citations': citations, 'advice': advice,
                'portion_reference': reference, 'boundary': None,
                'coverage': draft.coverage, 'missing_topics': draft.missing_topics,
                'general_info': answer_scope.concept_help(request.question) if draft.coverage == 'partial' else [],
                'answer_checks': {'status': 'partial' if state.get('withheld') else 'passed',
                                  'checked_paragraphs': len(state['candidates']),
                                  'accepted_paragraphs': len(accepted), 'issues': state.get('withheld', []),
                                  'review_attempts': 1},
                'steps': state['steps'] + ['verify_grounding']}

    graph = StateGraph(DietState)
    for name, node in [('understand', understand), ('extract_foods', extract_foods),
                       ('assess_nutrition', assess_nutrition), ('emergency', emergency), ('boundary', boundary),
                       ('clarify', clarify), ('retrieve', retrieve), ('web_search', web_search),
                       ('generate', generate), ('validate', validate),
                       ('verify_grounding', verify_grounding), ('insufficient', insufficient)]:
        def with_progress(state, _name=name, _node=node):
            if progress: progress(_name)
            return _node(state)
        graph.add_node(name, metrics.measure_node(name, with_progress))
    graph.add_edge(START, 'understand')
    graph.add_edge('understand', 'extract_foods')
    graph.add_edge('extract_foods', 'assess_nutrition')
    graph.add_conditional_edges('assess_nutrition', route,
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
        logger.info('Diet execution metrics=%s', metrics.snapshot())

    return DietAnswer(
        status=state['status'], urgency=state.get('urgency'), required_action=state.get('required_action'),
        answer=state['answer'], foods=state.get('foods', []), findings=state.get('findings', []),
        unknown_foods=state.get('unknown_foods', []), portion_reference=state.get('portion_reference'),
        nutrition_risks=state.get('nutrition_risks', []), boundary=state.get('boundary'),
        advice=state.get('advice', []), red_flags_observed=state.get('red_flags_observed', []),
        triage_rule_ids=state.get('triage_rule_ids', []), missing_info=state.get('missing_info', []),
        route_suggestion=state.get('route_suggestion'), coverage=state.get('coverage'),
        missing_topics=state.get('missing_topics', []), general_info=state.get('general_info', []),
        dialogue_state=dialogue, citations=state.get('citations', []), retrieved_hits=state.get('hits', []),
        web_sources=state.get('web_sources', []), web_status=state.get('web_status', 'not_used'),
        web_warning=state.get('web_warning'), web_diagnostics=state.get('web_diagnostics'),
        answer_checks=state.get('answer_checks'), metrics=metrics.snapshot(),
        disclaimer=state.get('disclaimer', checks.DISCLAIMER), table_version=food_rules.TABLE_VERSION,
        vector_count=state.get('vector_count', 0), reason=state.get('reason'),
        retrieval_log_id=state.get('log_id'), model=llm.model, knowledge_scope=kb_ids, steps=state['steps'])


def _clarification(intent: str) -> str:
    if intent == 'condition_diet':
        return '请补充老人的慢病情况（例如是否有高血压、糖尿病、肾病或心衰），以及近期体重变化，我才能给出合适的饮食原则。'
    if intent == 'texture':
        return '请补充是牙口不好还是吞咽容易呛，以及平时能接受的食物形态（软烂、糊状还是普通饮食）。'
    if intent == 'protein':
        return '请补充老人平时吃肉、蛋、奶和豆制品的情况，以及是否有肾病或正在透析。'
    return '请补充老人的慢病情况、牙口与吞咽情况，以及近三个月的体重变化。'


def _evaluate_review(review: DietReview, paragraphs: list[DietParagraph],
                     evidence_by_index: dict[int, dict]) -> list[DietParagraph]:
    if len(review.assessments) != len(paragraphs):
        raise ValueError('review_coverage')
    if {item.paragraph for item in review.assessments} != set(range(1, len(paragraphs) + 1)):
        raise ValueError('review_coverage')
    accepted: list[DietParagraph] = []
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


__all__ = ['run_diet', 'DietState']
