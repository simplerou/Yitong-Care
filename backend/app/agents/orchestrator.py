"""A request-scoped LangGraph; durable conversations are deliberately not implied."""
import re
import logging
from datetime import date
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from app.schemas.chat import PolicyAnswer, PolicyQuestion, Citation
from app.schemas.retrieval import SearchRequest
from app.services.chat.prompt_builder import UNDERSTAND, GENERATE
from app.services.chat.citation import Draft
from app.services.chat.evidence_limits import evidence_scope_issues
from app.services.chat.grounding import LABELS, review_with_repair, GroundingReviewError, evidence_spans, ages, numeric_support_issues, remove_extra_calculation, remove_denied_user_amount
from app.services.chat.policy_checks import unsupported_validity_claim
from app.services.retrieval import hybrid
from app.core.exceptions import BusinessError
from app.services.chat.clarification import confirmed_question, explicit_standard_question, same_clarification, age_followup_question, explicit_applicability_question, explicitly_provided_fields, remaining_clarification
from app.services.chat.answer_scope import requested_gaps,gap_message,concept_help
from app.services.web.query_plan import focused_query
from app.services.chat.dialogue_state import build_dialogue, context_query
from app.services.chat.metrics import PolicyMetrics, MeasuredLLM

logger = logging.getLogger(__name__)

INSUFFICIENT = '当前知识库资料不足以支持可靠回答。请补充相关地区的政策文件或咨询属地医保、民政部门；暂不能据此判断个人资格、补贴金额或政策是否仍有效。'


class Understanding(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    missing_fields: list[Literal['age','household_region','district','residence','benefit','income','disability']] = Field(default_factory=list, max_length=7)
    needs_freshness: bool = False
    supported: bool
    needs_clarification: bool
    clarification: str | None = Field(default=None, max_length=1000)
    query: str | None = Field(default=None, max_length=1000)

    @model_validator(mode='after')
    def validate_active_branch(self):
        if not self.supported:
            return self
        if self.needs_clarification:
            if not self.clarification or not self.clarification.strip():
                raise ValueError('clarification_required_for_clarify_branch')
            self.clarification = self.clarification.strip()
        else:
            if not self.query or not self.query.strip():
                raise ValueError('query_required_for_retrieve_branch')
            self.query = self.query.strip()
        return self


class State(TypedDict, total=False):
    answer_checks: dict
    policy_categories: list[str]
    decision: Understanding
    status: str
    answer: str
    hits: list
    draft: dict
    citations: list
    web_sources: list
    web_status: str
    web_diagnostics: object
    web_warning: str | None
    web_query: str
    web_refine_found: bool
    web_attempted: bool
    vector_count: int
    reason: str
    log_id: str | None
    steps: list[str]


def run_policy(request: PolicyQuestion, db, embedder, manager, llm, kb_ids: list[str], web=None, trace=None, progress=None) -> PolicyAnswer:
    metrics = PolicyMetrics()
    llm = MeasuredLLM(llm, metrics)
    llm.ensure_configured()
    history = [turn.model_dump() for turn in request.history]
    dialogue=request.dialogue_state or build_dialogue([*[turn.content for turn in request.history if turn.role=='user'],request.question])
    resolved_confirmation = confirmed_question(request.question, request.history)
    resolved_followup = age_followup_question(request.question, request.history)
    resolved_input = resolved_followup or resolved_confirmation or context_query(dialogue,request.question)
    provided_fields = explicitly_provided_fields(request.question,request.history)
    for field,value in [('age',dialogue.age is not None),('household_region',bool(dialogue.household)),('district',bool(dialogue.district)),('benefit',bool(dialogue.benefit))]:
        if value: provided_fields.add(field)
    user_ages = ages(request.question + '\n' + '\n'.join(turn.content for turn in request.history if turn.role=='user') + '\n' + (resolved_confirmation or ''))
    if dialogue.age is not None: user_ages.add(dialogue.age)
    if request.context.age is not None: user_ages.add(request.context.age)

    def effective_question(base=None):
        context = request.context.model_dump(exclude_none=True)
        values = {key: value for key, value in context.items() if value != ''}
        if not values: return base or request.question
        # Values are explicitly entered by the user, never inferred from assistant answers.
        import json
        original = base or request.question
        suffix = '\n本次咨询已确认条件（若与本条问题冲突，以本条问题为准）：' + json.dumps(values, ensure_ascii=False)
        # Preserve the complete question when extra context would exceed retrieval limits.
        return original + suffix if len(original + suffix) <= 1000 else original

    def understand(state):
        payload = {'question':resolved_input, 'user_reply':request.question, 'history':history, 'confirmed_context':request.context.model_dump(), 'provided_fields':sorted(provided_fields), 'dialogue_state':dialogue.model_dump(), 'today':date.today().isoformat()}
        for attempt in range(2):
            raw = llm.complete_json(UNDERSTAND, payload)
            try:
                decision = Understanding.model_validate(raw)
                break
            except ValidationError as error:
                # Log shape errors only, never raw model text, questions, keys, or history.
                issues = [{'field':'.'.join(map(str, item['loc'])), 'type':item['type']} for item in error.errors()]
                logger.warning('Policy understanding schema mismatch attempt=%s issues=%s', attempt + 1, issues)
                if attempt:
                    raise BusinessError('模型返回的问题分析格式不符合要求，请重试。', 502) from None
                payload = {**payload, 'format_retry': {
                    'instruction':'上次输出未通过结构校验。请重新分析原问题并严格遵守 JSON 字段类型；仅对当前分支填写必要字段。',
                    'issues':issues}}
        if decision.supported and decision.needs_clarification:
            complete_standard = explicit_standard_question(resolved_input)
            applicability = explicit_applicability_question(resolved_input)
            repeated_confirmation = bool(resolved_confirmation and request.history and
                same_clarification(decision.clarification or '', request.history[-1].content))
            if complete_standard or applicability or repeated_confirmation:
                decision.needs_clarification = False
                decision.clarification = None
                decision.query = resolved_input
                if trace: trace('clarification_guard', {'reason':'explicit_standard' if complete_standard else 'document_applicability' if applicability else 'confirmed_condition'})
        if decision.supported and decision.needs_clarification:
            refined=remaining_clarification(decision.clarification or '',provided_fields,decision.missing_fields)
            if refined is None:
                # If only known fields were requested, ask the unresolved benefit category
                # for broad eligibility questions, otherwise retrieve with user context.
                if 'benefit' not in provided_fields:
                    decision.clarification='请问您想了解哪类补贴或保障，例如养老服务补贴、失能护理补贴或长期护理保险？'
                    decision.missing_fields=['benefit']
                else:
                    decision.needs_clarification=False
                    user_context='\n'.join(turn.content for turn in request.history if turn.role=='user')
                    decision.query=(user_context+'\n'+request.question)[-1000:]
            else:
                decision.clarification=refined
                decision.missing_fields=[field for field in decision.missing_fields if field not in provided_fields]
            if trace: trace('clarification_fields',{'provided_fields':sorted(provided_fields),'missing_fields':decision.missing_fields})
        if decision.supported and decision.needs_clarification:
            if dialogue.region and dialogue.benefit:
                decision.needs_clarification=False
                decision.clarification=None
                decision.query=resolved_input
                if trace: trace('clarification_budget',{'reason':'region_and_benefit_ready_answer_first'})
            else:
                missing=[]
                if not dialogue.region: missing.append('咨询地区（城市）')
                if not dialogue.benefit: missing.append('想了解的补贴或保障类别')
                decision.clarification='请问'+ '、'.join(missing)+'？'
        if decision.supported and not decision.needs_clarification and not request.history:
            proposed=decision.query
            decision.query=effective_question()
            decision.needs_freshness=bool(re.search(r'最新|现行|当前|有效|废止|后续调整|目前|现在|今天|刚发布|新出台',request.question)) or any(int(year)>=date.today().year for year in re.findall(r'20\d{2}',request.question))
            if trace: trace('query_scope',{'proposed':proposed,'effective':decision.query,'strategy':'standalone_original'})
        if (resolved_followup or resolved_confirmation or resolved_input!=request.question) and decision.supported and not decision.needs_clarification:
            decision.query = resolved_input
        if request.history and request.context.model_dump(exclude_defaults=True) and decision.query:
            decision.query=effective_question(decision.query)
        if trace: trace('understanding',decision.model_dump())
        return {'decision':decision, 'steps':['understand']}

    def route(state):
        decision = state['decision']
        return 'clarify' if not decision.supported or decision.needs_clarification else 'retrieve'

    def clarify(state):
        decision = state['decision']
        return {'status':'clarification', 'reason':'missing_conditions' if decision.supported else 'outside_scope', 'answer':decision.clarification if decision.supported else '我是养老政策顾问，请提出养老政策、补贴、长期护理保险或相关办理问题。', 'steps':state['steps']+['clarify']}

    def retrieve(state):
        embedder.ensure_configured()
        result = hybrid.search(db, SearchRequest(query=state['decision'].query, top_k=5), embedder, manager, allowed_kb_ids=kb_ids)
        # Bound model context; citations return precisely the text sent to the model.
        hits = []
        remaining = 20000
        for hit in result.hits:
            text = hit.text[:min(4000, remaining)]
            if not text: break
            hits.append(hit.model_copy(update={'text':text, 'chars':len(text), 'end':hit.start+len(text)}))
            remaining -= len(text)
        return {'hits':hits, 'log_id':result.log_id, 'vector_count':result.vector_count, 'steps':state['steps']+['retrieve']}

    def insufficient(state, reason=None):
        reason = reason or (state.get('reason') if state.get('reason') == 'model_insufficient' else None) or ('no_vectors' if not state.get('vector_count') else 'no_hits')
        messages = {
            'no_vectors':'政策顾问当前知识范围内没有与当前向量模型匹配的已入库片段。请确认文档已完成向量入库，并核对知识库范围和模型配置。',
            'no_hits':'已执行混合检索，但未召回相关片段。请查看检索记录，核对问题关键词和文档知识范围。',
            'model_insufficient':gap_message(requested_gaps(state['decision'].query or resolved_input)),
            'invalid_output':'已检索到资料，但模型回答格式未通过校验，暂未展示草稿。请重试；这不代表知识库没有资料。',
            'invalid_citations':'已检索到资料，但模型的引用编号或引用格式未通过校验，暂未展示草稿。请重试；这不代表检索没有结果。',
        }
        return {'status':'insufficient', 'reason':reason, 'answer':messages[reason] + ('\n\n'+state['web_warning'] if state.get('web_warning') else ''), 'citations':[], 'steps':state['steps']+['insufficient']}

    def wants_freshness(state):
        text = request.question + ' ' + (state['decision'].query or '')
        return state['decision'].needs_freshness or bool(re.search(r'最新|现行|当前|仍.{0,2}有效|还.{0,2}有效|是否有效|有没有更新|有无调整|废止|现在.*政策', text))

    def web_search(state):
        from app.services.web.tavily import WebSearchError
        update = {'web_attempted':True, 'steps':state['steps']+['web_search']}
        if web is None or not web.configured:
            return {**update, 'web_status':'not_configured', 'web_sources':[], 'web_warning':'联网搜索尚未配置 TAVILY_API_KEY，本次未完成网络核验。'}
        try:
            search_query=focused_query(state['decision'].query,dialogue,wants_freshness(state))
            if trace: trace('web_query_plan',{'original':state['decision'].query,'effective':search_query})
            diagnostic = None
            if hasattr(web, 'search_with_diagnostics'):
                from app.services.web.tavily import TavilySearch
                report = web.search_with_diagnostics(search_query, bypass_cache=wants_freshness(state)) if isinstance(web,TavilySearch) else web.search_with_diagnostics(search_query)
                sources, diagnostic = report.sources, report.diagnostics
            else:
                sources = web.search(search_query)
            return {**update, 'web_query':search_query,'web_diagnostics':diagnostic, 'web_sources':sources, 'web_status':'success' if sources else 'no_results',
                    'web_warning':None if sources else '联网搜索未取得可用的官方网页正文，本次未完成网络核验。'}
        except WebSearchError as error:
            return {**update, 'web_sources':[], 'web_status':'error', 'web_diagnostics':error.diagnostics, 'web_warning':str(error)}

    def can_refine_web(state):
        from app.services.web.tavily import TavilySearch
        return bool(isinstance(web,TavilySearch) and state.get('web_status')=='success'
                    and state.get('web_diagnostics') and state.get('web_query')
                    and web.remaining_queries(state['web_query'],state['web_diagnostics']))

    def web_refine(state):
        from app.services.web.tavily import WebSearchError
        update={'steps':state['steps']+['web_refine'],'web_refine_found':False}
        old_urls={source.url for source in state.get('web_sources',[])}
        try:
            report=web.refine_with_diagnostics(state['web_query'],state.get('web_sources',[]),state['web_diagnostics'])
            found=any(source.url not in old_urls for source in report.sources)
            if trace: trace('answer_aware_search',{'new_source_found':found,'rounds':len(report.diagnostics.attempts)})
            return {**update,'web_refine_found':found,'web_sources':report.sources,'web_diagnostics':report.diagnostics}
        except WebSearchError as error:
            return {**update,'web_status':'error','web_warning':str(error),'web_diagnostics':error.diagnostics}

    def after_validate(state):
        if state.get('status')=='answered': return 'verify_grounding'
        if state.get('reason')=='model_insufficient':
            if not state.get('web_attempted'): return 'web_search'
            if can_refine_web(state): return 'web_refine'
        return END

    def evidence_for(state):
        local = [{'index':i, 'kind':'local', 'document':hit.doc_name, 'source':hit.source, 'heading':hit.heading, 'policy_metadata':hit.policy_metadata.model_dump(mode='json') if hit.policy_metadata else None, 'text':hit.text, 'coverage':'chunk', 'completeness_verified':False} for i, hit in enumerate(state.get('hits',[]), 1)]
        remote = [{'index':len(local)+i, 'kind':'web', 'document':item.title, 'url':item.url,
                   'search_scope':item.search_scope,'search_query':item.search_query,'published_date':item.published_date, 'retrieved_at':item.retrieved_at, 'text':item.content,
                   'coverage':item.coverage, 'is_truncated':item.is_truncated, 'original_content_chars':item.original_content_chars,
                   'excerpt_start':item.excerpt_start, 'completeness_verified':False}
                  for i, item in enumerate(state.get('web_sources',[]),1)]
        return local + remote

    def generate(state):
        evidence = evidence_for(state)
        payload = {'question':state['decision'].query, 'user_question':resolved_input, 'confirmed_context':request.context.model_dump(), 'evidence':evidence, 'today':date.today().isoformat(),
                   'freshness_requested':wants_freshness(state), 'web_status':state.get('web_status','not_used'),
                   'web_warning':state.get('web_warning')}
        for attempt in range(2):
            draft = llm.complete_json(GENERATE, payload)
            try:
                parsed = Draft.model_validate(draft)
                if not parsed.sufficient and parsed.paragraphs:
                    # Salvage only candidates, never bypass numeric/citation/semantic checks.
                    parsed=parsed.model_copy(update={'sufficient':True,'coverage':'partial'})
                    draft=parsed.model_dump()
                    if trace: trace('partial_candidates',{'paragraph_count':len(parsed.paragraphs)})
                if parsed.sufficient:
                    cleaned=[remove_extra_calculation(p,evidence,user_ages=user_ages) for p in parsed.paragraphs]
                    if cleaned!=parsed.paragraphs:
                        if trace: trace('calculation_removed',{'before':parsed.model_dump(),'after':[p.model_dump() for p in cleaned]})
                        parsed=parsed.model_copy(update={'paragraphs':cleaned})
                        draft=parsed.model_dump()
                    corrected=[remove_denied_user_amount(p,evidence,resolved_input,user_ages=user_ages) for p in parsed.paragraphs]
                    if corrected!=parsed.paragraphs:
                        if trace: trace('denied_user_amount_removed',{'before':parsed.model_dump(),'after':[p.model_dump() for p in corrected]})
                        parsed=parsed.model_copy(update={'paragraphs':corrected})
                        draft=parsed.model_dump()
                    if not parsed.paragraphs: raise ValueError('empty_paragraphs')
                    numeric_issues=numeric_support_issues(parsed.paragraphs,evidence,user_ages=user_ages)
                    if numeric_issues:
                        if trace: trace('generation_numeric_rejection',{'attempt':attempt+1,'issues':numeric_issues,'draft':draft})
                        payload={**payload,'numeric_retry':{'issues':numeric_issues,'instruction':'只保留引用原文支持的金额和政策分档；否定用户错误金额时用“不是”即可，不再复述该数字。用户年龄可匹配原文明确区间，不可改成新门槛。'}}
                        raise ValueError('unsupported_numeric_expansion')
                    for paragraph in parsed.paragraphs:
                        if not paragraph.text.strip() or re.search(r'【.*?】', paragraph.text): raise ValueError('citation_format')
                        if any(i < 1 or i > len(evidence) for i in paragraph.sources): raise ValueError('citation_range')
                        if unsupported_validity_claim(paragraph.text): raise ValueError('unsupported_validity_claim')
                        selected=[item for item in evidence if item['index'] in paragraph.sources]
                        if evidence_scope_issues(paragraph.text,selected): raise ValueError('unsupported_evidence_scope')
                break
            except (ValidationError, ValueError):
                if not attempt:
                    payload = {**payload, 'format_retry':'上次输出未通过格式或引用校验。仅按规定 JSON 字段重新输出；每段 text 不要带【编号】，sources 使用 evidence 中的整数编号。不得断言政策最新、现行有效或未被废止；不能从未搜到调整文件推导有效性。改为解释所引用文件的原文规定，并明确尚不能确认当前效力。不得新增原文没有的年龄分档或数字，不得自行计算原文未明确列出的派生金额；原文给出比例时保留比例、下限和基准额，不作换算。只回答原问题，删除额外年份核验、流程或材料要求。不能用摘录推断完整目录或全文未列某项；不能无依据扩大成全体、所有对象。改用片段可支持的条款，说明完整性尚未核实。资料确实不足可返回 sufficient=false。'}
        if trace: trace('generation',{'draft':draft})
        return {'draft':draft, 'steps':state['steps']+['generate']}

    def validate(state):
        try:
            draft = Draft.model_validate(state['draft'])
            if not draft.sufficient: return insufficient(state, 'model_insufficient')
            if not draft.paragraphs: return insufficient(state, 'invalid_output')
            numeric_issues=numeric_support_issues(draft.paragraphs,evidence_for(state),user_ages=user_ages)
            if numeric_issues:
                result=insufficient(state,'invalid_output')
                logger.warning('Policy numeric validation blocked issues=%s',numeric_issues)
                result['answer_checks']={'status':'blocked','checked_paragraphs':len(draft.paragraphs),'accepted_paragraphs':0,'issues':[f"generation_{item['type']}:paragraph_{item['paragraph']}" for item in numeric_issues]}
                result.update(reason='unsupported_numeric_expansion',answer='草稿新增了引用原文中未直接列出的年龄或金额，修正后仍未通过检查，暂不展示。可查看右侧原文，不应据此认为知识库没有资料。')
                return result
            used = set()
            paragraphs = []
            withheld = False
            for paragraph in draft.paragraphs:
                if not paragraph.text.strip() or re.search(r'【.*?】', paragraph.text): return insufficient(state, 'invalid_citations')
                indices = sorted(set(paragraph.sources))
                if any(i < 1 or i > len(evidence_for(state)) for i in indices): return insufficient(state, 'invalid_citations')
                if unsupported_validity_claim(paragraph.text) or evidence_scope_issues(paragraph.text,[item for item in evidence_for(state) if item['index'] in indices]):
                    withheld = True
                    continue
                used.update(indices)
                paragraphs.append(paragraph.text.strip() + ''.join(f'【{i}】' for i in indices))
            if not paragraphs:
                result = insufficient(state, 'invalid_output')
                result['answer'] = '已取得政策资料，但草稿包含缺乏依据的效力、完整目录或适用对象判断，已拦截。请核对右侧原文，当前不能据片段确认完整文件范围。'
                result['reason'] = 'unsupported_evidence_scope' if any(evidence_scope_issues(p.text,[item for item in evidence_for(state) if item['index'] in p.sources]) for p in draft.paragraphs) else 'unsupported_validity_claim'
                return result
            temporal_note = '\n\n本次仅能说明所引用文件的规定，尚不能确认其截至今日的现行效力或是否为最新政策。' if wants_freshness(state) or withheld else ''
            local_count = len(state['hits'])
            citations = [Citation(index=i, hit=state['hits'][i-1]) if i <= local_count else
                         Citation(index=i, source_type='web', web=state['web_sources'][i-local_count-1]) for i in sorted(used)]
            return {'status':'answered', 'reason':'grounded_answer', 'answer':'\n\n'.join(paragraphs)+temporal_note+'\n\n适用地区、有效状态及个人资格仍需以属地主管部门核实为准。'+('\n\n'+state['web_warning'] if state.get('web_warning') else ''),
                    'citations':citations, 'steps':state['steps']+['validate_citations']}
        except ValidationError:
            return insufficient(state, 'invalid_output')

    def verify_grounding(state):
        # Only paragraphs that survived format/temporal validation are candidates for review.
        draft = Draft.model_validate(state['draft'])
        candidates = [p for p in draft.paragraphs if not unsupported_validity_claim(p.text) and not evidence_scope_issues(p.text,[item for item in evidence_for(state) if item['index'] in p.sources])]
        evidence = evidence_for(state)
        payload = {'question':state['decision'].query, 'user_question':resolved_input, 'user_provided_ages':sorted(user_ages), 'paragraphs':[
            {'paragraph':i,'text':p.text,'sources':p.sources} for i,p in enumerate(candidates,1)],
            'evidence':[item for item in evidence if any(item['index'] in p.sources for p in candidates)]}
        for item in payload['evidence']: item['spans']=evidence_spans(item['text'])
        if trace: trace('review_input',payload)
        try:
            accepted,issues,attempts = review_with_repair(llm,payload,candidates,evidence,trace=trace)
        except GroundingReviewError as error:
            return {'status':'insufficient','reason':'grounding_review_failed',
                    'answer':'已检索到政策资料，但本次答案与原文的一致性检查未能完成，暂不展示草稿。请重试，右侧原文仍可查看。',
                    'citations':[], 'answer_checks':{'status':'error','checked_paragraphs':len(candidates),'accepted_paragraphs':0,'issues':[error.code],'review_attempts':error.attempts},
                    'steps':state['steps']+['verify_grounding']}
        off_topic=[i for i,assessment in accepted.items() if not assessment.addresses_question]
        if off_topic:
            accepted={i:assessment for i,assessment in accepted.items() if i not in off_topic}
            issues=issues+['answer_off_topic']
        checks = {'status':'passed' if not issues else ('partial' if accepted else 'blocked'),
                  'checked_paragraphs':len(candidates),'accepted_paragraphs':len(accepted),'issues':issues,'review_attempts':attempts}
        if not accepted:
            return {'status':'insufficient','reason':'unsupported_policy_claim',
                    'answer':'已检索到资料，但草稿中的政策类别、金额、年龄、地区或适用条件未通过原文一致性检查，已拦截该草稿。请查看右侧原文，或明确要咨询的补贴类别。',
                    'citations':[], 'answer_checks':checks,'steps':state['steps']+['verify_grounding']}
        from app.services.chat.grounding import amounts
        asks_amount=bool(re.search(r'多少钱|金额|补贴标准|津贴标准|标准是多少',request.question+' '+(state['decision'].query or '')))
        if asks_amount and any(amounts(p.text) for p in candidates) and not any(amounts(candidates[i-1].text) for i in accepted):
            checks.update(status='blocked',issues=issues+['core_answer_removed'])
            return {'status':'insufficient','reason':'answer_incomplete','answer':'已找到政策原文，但涉及金额的核心回答未通过一致性检查，暂不能提供可靠金额。右侧原文仍可查看，请重试或核对对应年龄、地区及发放周期。',
                    'citations':[],'answer_checks':checks,'steps':state['steps']+['verify_grounding']}
        rendered=[];used=set();categories=[];last_type=None
        for i,paragraph in enumerate(candidates,1):
            if i not in accepted: continue
            assessment=accepted[i]
            category=assessment.policy_type
            if category!='other' and category!=last_type: rendered.append(LABELS[category]+'：')
            if LABELS[category] not in categories: categories.append(LABELS[category])
            last_type=category
            indices=sorted(set(paragraph.sources));used.update(indices)
            rendered.append(paragraph.text.strip()+''.join(f'【{index}】' for index in indices))
        count=len(state['hits'])
        citations=[Citation(index=i,hit=state['hits'][i-1]) if i<=count else Citation(index=i,source_type='web',web=state['web_sources'][i-count-1]) for i in sorted(used)]
        note = '\n\n部分内容未通过原文一致性检查，已省略；以上仅说明检查保留的政策条款。' if issues else ''
        if wants_freshness(state) or any(unsupported_validity_claim(p.text) for p in draft.paragraphs): note += '\n\n本次仅能说明所引用文件的规定，尚不能确认其截至今日的现行效力或是否为最新政策。'
        note += '\n\n适用地区、有效状态及个人资格仍需以属地主管部门核实为准。'
        if state.get('web_warning'): note += '\n\n'+state['web_warning']
        return {'answer':'\n\n'.join(rendered)+note,'citations':citations,'answer_checks':checks,'policy_categories':categories,
                'steps':state['steps']+['verify_grounding']}

    graph = StateGraph(State)
    for name, node in [('understand',understand), ('clarify',clarify), ('retrieve',retrieve), ('insufficient',insufficient), ('generate',generate), ('validate',validate), ('web_search',web_search), ('web_refine',web_refine), ('verify_grounding',verify_grounding)]:
        def with_progress(state, _name=name, _node=node):
            if progress: progress(_name)
            return _node(state)
        graph.add_node(name, metrics.measure_node(name, with_progress))
    graph.add_edge(START, 'understand')
    graph.add_conditional_edges('understand', route, {'clarify':'clarify', 'retrieve':'retrieve'})
    graph.add_conditional_edges('retrieve', lambda s:'web_search' if wants_freshness(s) or not s['hits'] else 'generate', {'generate':'generate', 'web_search':'web_search'})
    graph.add_conditional_edges('web_search', lambda s:'generate' if s.get('web_sources') or (s.get('hits') and not s.get('draft')) else 'insufficient',
                                {'generate':'generate', 'insufficient':'insufficient'})
    graph.add_edge('generate','validate')
    graph.add_conditional_edges('validate', after_validate,
                                {'verify_grounding':'verify_grounding', 'web_search':'web_search', 'web_refine':'web_refine', END:END})
    graph.add_conditional_edges('web_refine',lambda s:'generate' if s.get('web_refine_found') else 'insufficient',{'generate':'generate','insufficient':'insufficient'})
    graph.add_edge('verify_grounding',END)
    for terminal in ['clarify','insufficient']: graph.add_edge(terminal, END)
    try:
        state = graph.compile().invoke({})
    finally:
        logger.info('Policy execution metrics=%s', metrics.snapshot())
    try: draft_meta=Draft.model_validate(state['draft']) if state.get('draft') else None
    except ValidationError: draft_meta=None
    targets=requested_gaps(state.get('decision').query or resolved_input)
    gaps=[key for key in (draft_meta.missing_topics if draft_meta else []) if key in targets or key=='full_policy_scope']
    partial=state['status']=='answered' and bool(gaps or (draft_meta and draft_meta.coverage=='partial') or (state.get('answer_checks') or {}).get('status')=='partial')
    if partial and not gaps: gaps=targets if draft_meta and draft_meta.coverage=='partial' else ['full_policy_scope']
    if state['status']=='insufficient' and not gaps: gaps=targets
    # Internal validation failures remain visible as failures, not as benign source gaps.
    source_gap=state.get('reason') in {'model_insufficient','no_hits','no_vectors'}
    if partial: state['answer']+='\n\n'+gap_message(gaps,partial=True)
    if state['status']=='insufficient' and source_gap:
        state['answer']=gap_message(gaps)+(('\n\n'+state['web_warning']) if state.get('web_warning') else '')
    general_info=concept_help((state.get('decision').query or resolved_input)) if partial or (state['status']=='insufficient' and source_gap) else []
    return PolicyAnswer(coverage='partial' if partial else 'complete' if state['status']=='answered' else 'none',missing_topics=gaps,general_info=general_info,dialogue_state=dialogue,consultation_context=request.context,metrics=metrics.snapshot(),answer_checks=state.get('answer_checks'),policy_categories=state.get('policy_categories',[]),status=state['status'], answer=state['answer'], citations=state.get('citations',[]),
        web_diagnostics=state.get('web_diagnostics'), web_sources=state.get('web_sources',[]), web_status=state.get('web_status','not_used'), web_warning=state.get('web_warning'),
        retrieved_hits=state.get('hits',[]), vector_count=state.get('vector_count',0), reason=state.get('reason'),
        retrieval_log_id=state.get('log_id'), model=llm.model, knowledge_scope=kb_ids, steps=state['steps'])
