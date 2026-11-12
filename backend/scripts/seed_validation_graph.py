"""Load fictional demo graph facts; never installs clinical reference data."""
import argparse,json
from validation_service.config import ValidationSettings
from validation_service.graph import Neo4jGraph,DEMO

def seed(graph,data=None):
    data=data or DEMO
    from hashlib import sha256
    from validation_service.manifest import Manifest
    data=Manifest.model_validate(data).model_dump(mode='json')
    version=data['version']
    fingerprint=sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    existing=graph.query('MATCH (v:ValidationVersion {version:$version}) RETURN v.payload_hash AS hash',{'version':version})
    if existing:
        if existing[0]['hash']!=fingerprint:raise ValueError('规则版本不可覆盖，请使用新版本号')
        return
    for kind,items in [('drug',data['drugs']),('food',data['foods'])]:
        for key,data in items.items():
            label='Drug' if kind=='drug' else 'Food'
            graph.query(f'MERGE (n:CatalogEntity:{label} {{id:$id,version:$version}}) SET n.kind=$kind,n.payload=$payload',{'id':key,'version':version,'kind':kind,'payload':json.dumps(data,ensure_ascii=False)})
            for ingredient in data['ingredients']:
                graph.query('MATCH (n:CatalogEntity {id:$id,version:$version}) MERGE (i:Ingredient {id:$ingredient}) MERGE (n)-[:CONTAINS]->(i)',{'id':key,'version':version,'ingredient':ingredient})
            for allergen in data.get('allergens',[]):
                graph.query('MATCH (n:CatalogEntity {id:$id,version:$version}) MERGE (a:Allergen {id:$allergen}) MERGE (n)-[:HAS_ALLERGEN]->(a)',{'id':key,'version':version,'allergen':allergen})
    for c in data['conflicts']:
        graph.query('''MERGE (a:Ingredient {id:$left}) MERGE (b:Ingredient {id:$right})
        MERGE (r:ContraindicationRule {id:$rule,version:$version}) MERGE (e:Evidence {id:$evidence_id,version:$version}) SET e.payload=$payload
        MERGE (a)-[:CONFLICTS_WITH]->(r) MERGE (r)-[:TARGETS]->(b) MERGE (r)-[:EVIDENCED_BY]->(e)''',{'left':c['left'],'right':c['right'],'rule':c['rule'],'version':version,'evidence_id':c['evidence']['id'],'payload':json.dumps(c['evidence'],ensure_ascii=False)})
    for disease in data.get('diseases',[]):
        graph.query('MERGE (d:Disease {id:$id,version:$version})',{'id':disease,'version':version})
    for c in data.get('disease_conflicts',[]):
        graph.query('''MERGE (a:Disease {id:$disease,version:$version}) MERGE (b:Ingredient {id:$ingredient})
        MERGE (r:ContraindicationRule {id:$rule,version:$version}) MERGE (e:Evidence {id:$eid,version:$version}) SET e.payload=$payload
        MERGE (a)-[:CONTRAINDICATES]->(r) MERGE (r)-[:TARGETS]->(b) MERGE (r)-[:EVIDENCED_BY]->(e)''',{'disease':c['disease'],'ingredient':c['ingredient'],'rule':c['rule'],'version':version,'eid':c['evidence']['id'],'payload':json.dumps(c['evidence'],ensure_ascii=False)})
    for role in ('admin','medical','kitchen','nursing','finance','user'):
        graph.query('MERGE (r:Role {id:$role}) MERGE (d:BusinessDomain {id:$role}) MERGE (r)-[:WORKS_IN]->(d)',{'role':role})
    graph.query('MATCH (old:ValidationVersion) SET old.active=false WITH count(old) AS ignored MERGE (v:ValidationVersion {version:$version}) SET v.active=true,v.demo=$demo,v.payload_hash=$hash',{'version':version,'demo':data.get('demo',False),'hash':fingerprint})

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    if not args.apply:print('仅预览：将安装 DEMO-* 虚构图谱。添加 --apply 写入 Neo4j。');return 0
    try:seed(Neo4jGraph(ValidationSettings()))
    except Exception:print('Neo4j 导入失败；请检查服务和配置。');return 1
    print('虚构演示图谱已安装，禁止用于真实诊疗或营养决策。');return 0
if __name__=='__main__':raise SystemExit(main())
