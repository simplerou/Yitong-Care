"""Score independently labeled chunk rankings without model calls or database writes."""
import argparse,json
from pathlib import Path
from datetime import datetime,timezone
from uuid import uuid4


def read_jsonl(path):
    rows=[json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
    if not rows or any(not isinstance(r,dict) or not isinstance(r.get('id'),str) or not r['id'].strip() for r in rows):raise ValueError('每行须包含非空字符串id')
    if len({r['id'] for r in rows})!=len(rows):raise ValueError('id不得重复')
    return rows


def identifiers(value):
    if not isinstance(value,list) or any(type(v) not in (str,int) or not str(v).strip() for v in value):raise ValueError('块标识须为字符串或整数数组')
    values=[str(v) for v in value]
    if len(set(values))!=len(values):raise ValueError('块标识不得重复')
    return values


def score(labels,rankings,k=10,split='holdout'):
    if not 1<=k<=100 or split not in ('all','calibration','holdout'):raise ValueError('k或数据集划分错误')
    if len({r['id'] for r in labels})!=len(labels) or len({r['id'] for r in rankings})!=len(rankings):raise ValueError('id不得重复')
    if {r['id'] for r in rankings}-{r['id'] for r in labels}:raise ValueError('结果包含标注集以外的id')
    predictions={r['id']:identifiers(r['retrieved_chunk_ids']) for r in rankings};results=[]
    for row in labels:
        if row.get('split') not in ('calibration','holdout'):raise ValueError('标注须明确calibration或holdout')
        gold=set(identifiers(row['relevant_chunk_ids']))
        if not gold:raise ValueError('相关块集合为空，请先独立标注；无答案问题须单独评测')
        if split!='all' and row['split']!=split:continue
        if row['id'] not in predictions:
            results.append({'id':row['id'],'status':'blocked','reason':'missing_ranking'});continue
        top=predictions[row['id']][:k];hits=sum(v in gold for v in top)
        first=next((rank for rank,v in enumerate(top,1) if v in gold),None)
        results.append({'id':row['id'],'status':'scored','relevant_count':len(gold),'hits':hits,'recall':hits/len(gold),'reciprocal_rank':1/first if first else 0})
    measured=[r for r in results if r['status']=='scored'];n=len(measured)
    return {'k':k,'split':split,'cases':results,'scored':n,'blocked':len(results)-n,'complete':bool(results) and n==len(results),
            'recall_at_k':sum(r['recall'] for r in measured)/n if n else None,
            'micro_recall_at_k':sum(r['hits'] for r in measured)/sum(r['relevant_count'] for r in measured) if n else None,
            'mrr_at_k':sum(r['reciprocal_rank'] for r in measured)/n if n else None,
            'hit_rate_at_k':sum(r['hits']>0 for r in measured)/n if n else None}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--labels',required=True,type=Path);p.add_argument('--rankings',required=True,type=Path)
    p.add_argument('--split',choices=['all','calibration','holdout'],default='holdout');p.add_argument('--k',type=int,default=10)
    p.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parents[1]/'var/evaluations');args=p.parse_args()
    try:
        report=score(read_jsonl(args.labels),read_jsonl(args.rankings),args.k,args.split)
        report.update({'time':datetime.now(timezone.utc).isoformat(),'mode':'offline_rankings','limitations':'只评测提供的块级排序；标注须独立于待测结果。不等于已运行线上检索，也不证明临床事实或历史指标。缺失结果单列阻塞，完整性及分母单列。'})
        args.output_dir.mkdir(parents=True,exist_ok=True);path=args.output_dir/f'retrieval-{uuid4().hex[:12]}.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f"Recall@{args.k}：{report['recall_at_k']}；计分 {report['scored']}；阻塞 {report['blocked']}；完整：{report['complete']}。报告：{path}")
        return 0 if report['complete'] else 1
    except (OSError,ValueError,KeyError,TypeError):print('评测未完成：请检查文件、唯一id、数据集划分及块级标注格式。');return 1
if __name__=='__main__':raise SystemExit(main())
