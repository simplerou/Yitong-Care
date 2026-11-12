"""Validate/import a reviewed JSON graph manifest. Read-only unless --apply."""
import argparse,json
from pathlib import Path
from validation_service.manifest import Manifest
from validation_service.graph import Neo4jGraph
from validation_service.config import ValidationSettings
from scripts.seed_validation_graph import seed

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('manifest',type=Path);parser.add_argument('--apply',action='store_true');parser.add_argument('--reviewer',default='');args=parser.parse_args()
    data=Manifest.model_validate_json(args.manifest.read_text()).model_dump(mode='json')
    print(f"事实版本 {data['version']}：{len(data['drugs'])} 个药品、{len(data['foods'])} 个食物，demo={data['demo']}")
    if not args.apply:print('结构检查通过，未写入 Neo4j。');return 0
    if not args.reviewer.strip():parser.error('正式导入需 --reviewer 登记专业核实责任人')
    graph=Neo4jGraph(ValidationSettings())
    seed(graph,data)
    graph.query('MATCH (v:ValidationVersion {version:$version}) SET v.reviewer=$reviewer,v.reviewed_at=datetime()',{'version':data['version'],'reviewer':args.reviewer})
    print('已导入并切换规则版本；旧版本草稿需重新核对。');return 0
if __name__=='__main__':raise SystemExit(main())
