"""A request-scoped LangGraph; durable conversations are deliberately not implied."""
import re
import logging
from datetime import date
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from app.schemas.chat import PolicyAnswer, PolicyQuestion, Citation
from app.schemas.retrieval import SearchRequest
from app.services.chat.prompt_builder import UNDERSTAND, GENERATE
from app.services.chat.citation import Draft
from app.services.chat.evidence_limits import evidence_scope_issues
from app.services.chat.grounding import LABELS, review_with_repair, GroundingReviewError, evidence_spans, numeric_support_issues, remove_extra_calculation
from app.services.chat.policy_checks import unsupported_validity_claim
from app.services.retrieval import hybrid
from app.core.exceptions import BusinessError

logger = logging.getLogger(__name__)

INSUFFICIENT = '当前知识库资料不足以支持可靠回答。请补充相关地区的政策文件或咨询属地医保、民政部门；暂不能据此判断个人资格、补贴金额或政策是否仍有效。'


class Understanding(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
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
    web_attempted: bool
    vector_count: int
    reason: str
    log_id: str | None
    steps: list[str]


def run_policy(request: PolicyQuestion, db, embedder, manager, llm, kb_ids: list[str], web=None, trace=None) -> PolicyAnswer:
    llm.ensure_configured()
    history = [turn.model_dump() for turn in request.history]

    def understand(state):
        payload = {'question':request.question, 'history':history, 'today':date.today().isoformat()}
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
        if decision.supported and not decision.needs_clarification and not request.history:
            proposed=decision.query
            decision.query=request.question
            decision.needs_freshness=bool(re.search(r'最新|现行|有效|废止|后续调整|目前|现在|今天|刚发布|新出台',request.question)) or any(int(year)>=date.today().year for year in re.findall(r'20\d{2}',request.question))
            if trace: trace('query_scope',{'proposed':proposed,'effective':decision.query,'strategy':'standalone_original'})
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
            'model_insufficient':'已检索到相关片段，但模型判断这些片段不足以支持所问结论。右侧仍可查看检索结果；可明确具体补贴类别，或核对片段是否包含所需条件和标准。',
            'invalid_output':'已检索到资料，但模型回答格式未通过校验，暂未展示草稿。请重试；这不代表知识库没有资料。',
            'invalid_citations':'已检索到资料，但模型的引用编号或引用格式未通过校验，暂未展示草稿。请重试；这不代表检索没有结果。',
        }
        return {'status':'insufficient', 'reason':reason, 'answer':messages[reason] + ('\n\n'+state['web_warning'] if state.get('web_warning') else ''), 'citations':[], 'steps':state['steps']+['insufficient']}

    def wants_freshness(state):
        text = request.question + ' ' + (state['decision'].query or '')
        return state['decision'].needs_freshness or bool(re.search(r'最新|现行|仍.{0,2}有效|还.{0,2}有效|是否有效|有没有更新|有无调整|废止|现在.*政策', text))

    def web_search(state):
        from app.services.web.tavily import WebSearchError
        update = {'web_attempted':True, 'steps':state['steps']+['web_search']}
        if web is None or not web.configured:
            return {**update, 'web_status':'not_configured', 'web_sources':[], 'web_warning':'联网搜索尚未配置 TAVILY_API_KEY，本次未完成网络核验。'}
        try:
            diagnostic = None
            if hasattr(web, 'search_with_diagnostics'):
                report = web.search_with_diagnostics(state['decision'].query)
                sources, diagnostic = report.sources, report.diagnostics
            else:
                sources = web.search(state['decision'].query)
            return {**update, 'web_diagnostics':diagnostic, 'web_sources':sources, 'web_status':'success' if sources else 'no_results',
                    'web_warning':None if sources else '联网搜索未取得可用的官方网页正文，本次未完成网络核验。'}
        except WebSearchError as error:
            return {**update, 'web_sources':[], 'web_status':'error', 'web_diagnostics':error.diagnostics, 'web_warning':str(error)}

    def evidence_for(state):
        local = [{'index':i, 'kind':'local', 'document':hit.doc_name, 'source':hit.source, 'text':hit.text, 'coverage':'chunk', 'completeness_verified':False} for i, hit in enumerate(state.get('hits',[]), 1)]
        remote = [{'index':len(local)+i, 'kind':'web', 'document':item.title, 'url':item.url,
                   'published_date':item.published_date, 'retrieved_at':item.retrieved_at, 'text':item.content,
                   'coverage':item.coverage, 'is_truncated':item.is_truncated, 'original_content_chars':item.original_content_chars,
                   'excerpt_start':item.excerpt_start, 'completeness_verified':False}
                  for i, item in enumerate(state.get('web_sources',[]),1)]
        return local + remote

    def generate(state):
        evidence = evidence_for(state)
        payload = {'question':state['decision'].query, 'user_question':request.question, 'evidence':evidence, 'today':date.today().isoformat(),
                   'freshness_requested':wants_freshness(state), 'web_status':state.get('web_status','not_used'),
                   'web_warning':state.get('web_warning')}
        for attempt in range(2):
            draft = llm.complete_json(GENERATE, payload)
            try:
                parsed = Draft.model_validate(draft)
                if parsed.sufficient:
                    cleaned=[remove_extra_calculation(p,evidence) for p in parsed.paragraphs]
                    if cleaned!=parsed.paragraphs:
                        if trace: trace('calculation_removed',{'before':parsed.model_dump(),'after':[p.model_dump() for p in cleaned]})
                        parsed=parsed.model_copy(update={'paragraphs':cleaned})
                        draft=parsed.model_dump()
                    if not parsed.paragraphs: raise ValueError('empty_paragraphs')
                    numeric_issues=numeric_support_issues(parsed.paragraphs,evidence)
                    if numeric_issues:
                        if trace: trace('generation_numeric_rejection',{'attempt':attempt+1,'issues':numeric_issues,'draft':draft})
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
            if numeric_support_issues(draft.paragraphs,evidence_for(state)):
                result=insufficient(state,'invalid_output')
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
        payload = {'question':state['decision'].query, 'user_question':request.question, 'paragraphs':[
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
    for name, node in [('understand',understand), ('clarify',clarify), ('retrieve',retrieve), ('insufficient',insufficient), ('generate',generate), ('validate',validate), ('web_search',web_search), ('verify_grounding',verify_grounding)]:
        graph.add_node(name, node)
    graph.add_edge(START, 'understand')
    graph.add_conditional_edges('understand', route, {'clarify':'clarify', 'retrieve':'retrieve'})
    graph.add_conditional_edges('retrieve', lambda s:'web_search' if wants_freshness(s) or not s['hits'] else 'generate', {'generate':'generate', 'web_search':'web_search'})
    graph.add_conditional_edges('web_search', lambda s:'generate' if s.get('web_sources') or (s.get('hits') and not s.get('draft')) else 'insufficient',
                                {'generate':'generate', 'insufficient':'insufficient'})
    graph.add_edge('generate','validate')
    graph.add_conditional_edges('validate', lambda s:'verify_grounding' if s.get('status')=='answered' else ('web_search' if s.get('reason')=='model_insufficient' and not s.get('web_attempted') else END),
                                {'verify_grounding':'verify_grounding', 'web_search':'web_search', END:END})
    graph.add_edge('verify_grounding',END)
    for terminal in ['clarify','insufficient']: graph.add_edge(terminal, END)
    state = graph.compile().invoke({})
    return PolicyAnswer(answer_checks=state.get('answer_checks'),policy_categories=state.get('policy_categories',[]),status=state['status'], answer=state['answer'], citations=state.get('citations',[]),
        web_diagnostics=state.get('web_diagnostics'), web_sources=state.get('web_sources',[]), web_status=state.get('web_status','not_used'), web_warning=state.get('web_warning'),
        retrieved_hits=state.get('hits',[]), vector_count=state.get('vector_count',0), reason=state.get('reason'),
        retrieval_log_id=state.get('log_id'), model=llm.model, knowledge_scope=kb_ids, steps=state['steps'])
