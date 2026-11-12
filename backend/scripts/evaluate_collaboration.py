"""Evaluate a fixed fictional set; reports rule correctness, not clinical accuracy."""
import argparse,json
from uuid import uuid4
from datetime import datetime,timezone
from pathlib import Path
from app.operations.contracts import CheckRequest
from app.operations.validator import ValidationClient
from validation_service.rules import evaluate
from validation_service.graph import DEMO
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fixture',action='store_true');p.add_argument('--split',choices=['all','calibration','holdout'],default='all');args=p.parse_args()
    cases=[json.loads(line) for line in (ROOT/'evaluations/collaboration/cases.jsonl').read_text().splitlines() if line]
    results=[]
    for case in cases:
        if args.split!='all' and case['split']!=args.split:continue
        try:
            request=CheckRequest.model_validate(case['request'])
            result=evaluate(request,DEMO) if args.fixture else ValidationClient().check(request.model_dump(mode='json'))
            codes={i['code'] for i in result['issues']}
            matched=result['passed']==case['expected_passed'] and set(case['expected_codes'])<=codes
            results.append({'id':case['id'],'status':'pass' if matched else 'fail','codes':sorted(codes),'rule_version':result['rule_version']})
        except Exception:results.append({'id':case['id'],'status':'blocked'})
    report={'time':datetime.now(timezone.utc).isoformat(),'mode':'fixture' if args.fixture else 'independent_service','split':args.split,'cases':results,'passed':sum(r['status']=='pass' for r in results),'failed':sum(r['status']=='fail' for r in results),'blocked':sum(r['status']=='blocked' for r in results),'limitations':'虚构规则固定集；holdout不在运行前展示期望标签。不是临床盲试、生产工具成功率、RAG召回率或人工节时研究。'}
    out=ROOT/'var/evaluations';out.mkdir(parents=True,exist_ok=True);path=out/('collaboration-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]+'.json');path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(f"通过 {report['passed']}；失败 {report['failed']}；阻塞 {report['blocked']}。报告：{path}")
    return int(bool(report['failed'] or report['blocked']))
if __name__=='__main__':raise SystemExit(main())
