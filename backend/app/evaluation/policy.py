import json
import re
from hashlib import sha256
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.chat import PolicyAnswer
from app.services.chat.grounding import normalized
from app.services.chat.policy_checks import unsupported_validity_claim
from app.services.chat.evidence_limits import evidence_scope_issues

DATASET_PATH = Path(__file__).resolve().parents[2] / 'evaluations/policy/cases.json'


class Case(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    topic: str
    mode: str
    turns: list[str] = Field(min_length=1)
    expected_statuses: list[str]
    answer_groups: list[list[str]]
    evidence_groups: list[list[str]]
    reference_pages: list[int]
    reference_quotes: list[str]
    manual_checks: list[str] = Field(min_length=1)
    preconditions: str


def load_dataset(path=DATASET_PATH):
    data=json.loads(Path(path).read_text())
    reference=data['reference']
    reference_path=(Path(path).parent/reference['reference_file']).resolve()
    if reference_path.parent!=Path(path).parent.resolve(): raise ValueError('reference outside dataset folder')
    text=reference_path.read_text()
    if sha256(text.encode()).hexdigest()!=reference['text_sha256']: raise ValueError('reference hash mismatch')
    cases=[Case.model_validate(row) for row in data['cases']]
    if len({c.id for c in cases})!=len(cases): raise ValueError('duplicate case IDs')
    for case in cases:
        if case.mode not in {'local','web'}: raise ValueError(f'{case.id}: invalid mode')
        if any(not turn.strip() or len(turn)>1000 for turn in case.turns): raise ValueError(f'{case.id}: invalid question')
        if not case.expected_statuses or any(status not in {'answered','clarification','insufficient'} for status in case.expected_statuses): raise ValueError(f'{case.id}: invalid expected status')
        for group in case.answer_groups+case.evidence_groups:
            if not group: raise ValueError('empty assertion group')
            for pattern in group: re.compile(pattern)
        for quote in case.reference_quotes:
            if normalized(quote) not in normalized(text): raise ValueError(f'{case.id}: reference quote not found')
    return data,cases


def check_answer(case: Case, answer: PolicyAnswer):
    """Mechanical diagnostics only; never label these results factual accuracy."""
    checks=[]
    def add(name,passed,detail=''):
        checks.append({'name':name,'passed':bool(passed),'detail':detail})
    add('expected_status',answer.status in case.expected_statuses,answer.status)
    for i,group in enumerate(case.answer_groups,1):
        add(f'answer_anchor_{i}',any(re.search(p,answer.answer) for p in group),' / '.join(group))
    evidence='\n'.join([hit.text for hit in answer.retrieved_hits]+[source.content for source in answer.web_sources])
    for i,group in enumerate(case.evidence_groups,1):
        add(f'retrieved_anchor_{i}',any(re.search(p,normalized(evidence)) for p in group),' / '.join(group))
    indices=[c.index for c in answer.citations]
    markers={int(i) for i in re.findall(r'【(\d+)】',answer.answer)}
    add('unique_citation_indices',len(indices)==len(set(indices)))
    add('citation_markers_match',markers==set(indices))
    for citation in answer.citations:
        if citation.source_type=='local':
            valid=0<citation.index<=len(answer.retrieved_hits) and citation.hit is not None and answer.retrieved_hits[citation.index-1].chunk_id==citation.hit.chunk_id and answer.retrieved_hits[citation.index-1].text==citation.hit.text
        else:
            offset=citation.index-len(answer.retrieved_hits)-1
            valid=0<=offset<len(answer.web_sources) and citation.web is not None and answer.web_sources[offset].url==citation.web.url and answer.web_sources[offset].content==citation.web.content
        add(f'citation_source_{citation.index}',valid)
    if answer.status=='answered':
        add('has_citations',bool(answer.citations))
        support=[{'text':c.hit.text if c.source_type=='local' and c.hit else c.web.content if c.web else ''} for c in answer.citations]
        add('no_unsupported_scope_claim',not evidence_scope_issues(answer.answer,support))
        add('grounding_check_completed',answer.answer_checks is not None and answer.answer_checks.status in {'passed','partial'})
    if case.mode=='web':
        add('web_attempted','web_search' in answer.steps)
        add('no_unverified_validity_claim',not unsupported_validity_claim(answer.answer))
    return checks


def write_report(report, output_root):
    from datetime import datetime, UTC
    from uuid import uuid4
    directory=Path(output_root)/(datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8])
    directory.mkdir(parents=True,exist_ok=False)
    (directory/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    def cell(value): return str(value).replace('|','／').replace('\n',' ')
    lines=['# 政策顾问评测报告','',f"运行状态：{report['status']}。",'',
           '**机械检查通过不等于政策事实正确；人工核对尚未完成。**','',
           f"数据集：{report['dataset_version']}；模式：{report['mode']}。",'']
    if report.get('blocking_reason'): lines+=['中断原因：'+report['blocking_reason'],'']
    lines+=['| 用例 | 主题 | 自动结果 | 人工结论 |','|---|---|---|---|']
    for row in report['results']: lines.append(f"| {cell(row['id'])} | {cell(row['topic'])} | {row['automatic_status']} | {row['manual_status']} |")
    for row in report['results']:
        lines+=['',f"## {row['id']} {row['topic']}",'']
        if row.get('error'): lines+=['执行错误：'+row['error'],'']
        for turn in row.get('turns',[]):
            lines+=['问题：'+turn['question'],'','回答：',turn['response']['answer'],'']
        failed=[item for item in row.get('checks',[]) if not item['passed']]
        if failed: lines+=['未通过的机械检查：'+', '.join(item['name'] for item in failed),'']
        lines+=['人工核对清单：']+['- '+note for note in row['manual_checks']]
        lines+=['','人工结论：待填写（通过／失败／无法判断）；请说明证据与失败原因。']
    (directory/'report.md').write_text('\n'.join(lines)+'\n')
    return directory
