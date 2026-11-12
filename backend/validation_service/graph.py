"""Only the rule service can query graph facts. All Cypher is fixed/parameterized."""
import httpx

# A deliberately fictional fixture; never represents drug or nutrition advice.
DEMO={
 'version':'demo-2026-11-v1','demo':True,
 'drugs':{
  'DEMO-A':{'id':'DEMO-A','name':'虚构药品A','ingredients':['demo-active-a'],'max_single_mg':'10','max_daily_mg':'20','evidence':{'id':'demo-insert-a','section':'1.1','location':'演示说明书第1段','quote':'仅自动化演示：单次不超过10单位、每日不超过20单位。','valid_from':'2026-01-01','valid_to':None}},
  'DEMO-B':{'id':'DEMO-B','name':'虚构药品B','ingredients':['demo-active-b'],'max_single_mg':'5','max_daily_mg':'10','evidence':{'id':'demo-insert-b','section':'1.2','location':'演示说明书第2段','quote':'虚构测试规则，禁止用于医疗。','valid_from':'2026-01-01','valid_to':None}}},
 'foods':{
  'DEMO-RICE':{'id':'DEMO-RICE','name':'演示米饭','ingredients':['demo-rice'],'allergens':[],'energy':'100','protein':'3','sodium':'5'},
  'DEMO-FISH':{'id':'DEMO-FISH','name':'演示鱼餐','ingredients':['demo-fish'],'allergens':['demo-fish-allergen'],'energy':'150','protein':'20','sodium':'100'},
  'DEMO-GRAPE':{'id':'DEMO-GRAPE','name':'演示冲突水果','ingredients':['demo-grape'],'allergens':[],'energy':'50','protein':'1','sodium':'0'}},
 'conflicts':[
  {'left':'demo-active-a','right':'demo-grape','rule':'demo-food-drug','evidence':{'id':'demo-rule-1','section':'R1','location':'演示规则第1条','quote':'仅测试：虚构药品A与演示冲突水果禁配。','valid_from':'2026-01-01','valid_to':None}},
  {'left':'demo-active-a','right':'demo-active-b','rule':'demo-polypharmacy','evidence':{'id':'demo-rule-2','section':'R2','location':'演示规则第2条','quote':'仅测试：两种虚构活性成分禁配。','valid_from':'2026-01-01','valid_to':None}}],
 'diseases':[],'disease_conflicts':[]}

class GraphUnavailable(Exception):pass

class DemoGraph:
    def facts(self):return DEMO

class Neo4jGraph:
    def __init__(self,settings):self.settings=settings
    def query(self,statement,parameters=None):
        cfg=self.settings
        if not cfg.neo4j_password.get_secret_value():raise GraphUnavailable()
        try:
            with httpx.Client(timeout=10,follow_redirects=False) as client:
                response=client.post(cfg.neo4j_http_url.rstrip('/')+f'/db/{cfg.neo4j_database}/tx/commit',auth=(cfg.neo4j_user,cfg.neo4j_password.get_secret_value()),json={'statements':[{'statement':statement,'parameters':parameters or {}}]})
                response.raise_for_status();data=response.json()
            if data.get('errors'):raise GraphUnavailable()
            result=data['results'][0]
            return [dict(zip(result['columns'],item['row'])) for item in result['data']]
        except (httpx.HTTPError,KeyError,TypeError,ValueError):raise GraphUnavailable() from None
    def facts(self):
        versions=self.query('MATCH (v:ValidationVersion {active:true}) RETURN v.version AS version, v.demo AS demo')
        if len(versions)!=1:raise GraphUnavailable()
        version=versions[0]['version']
        rows=self.query('MATCH (n:CatalogEntity {version:$version}) RETURN n.kind AS kind, n.id AS id, n.payload AS payload',{'version':version})
        import json
        facts={**versions[0],'drugs':{},'foods':{},'conflicts':[],'disease_conflicts':[]}
        for row in rows:
            value=json.loads(row['payload'])
            if row['kind'] in ('drug','food'):facts['drugs' if row['kind']=='drug' else 'foods'][row['id']]=value
        # Materialize ingredient-level multihop paths, with evidence attached to rule nodes.
        paths=self.query('''MATCH (a:Ingredient)-[:CONFLICTS_WITH]->(r:ContraindicationRule {version:$version})-[:TARGETS]->(b:Ingredient)
        MATCH (r)-[:EVIDENCED_BY]->(e:Evidence)
        RETURN a.id AS left,b.id AS right,r.id AS rule,e.payload AS evidence''',{'version':version})
        full_paths=self.query('''MATCH (d:Drug:CatalogEntity {version:$version})-[:CONTAINS]->(a:Ingredient)-[:CONFLICTS_WITH]->(r:ContraindicationRule {version:$version})-[:TARGETS]->(b:Ingredient)<-[:CONTAINS]-(target:CatalogEntity {version:$version})
        MATCH (r)-[:EVIDENCED_BY]->(e:Evidence) RETURN d.id AS drug_id, a.id AS active_ingredient, r.id AS rule, b.id AS conflict_ingredient, target.id AS target_id, e.id AS evidence_id''',{'version':version})
        facts['graph_paths']=full_paths
        facts['diseases']=[row['id'] for row in self.query('MATCH (d:Disease {version:$version}) RETURN d.id AS id',{'version':version})]
        for row in paths:
            row['evidence']=json.loads(row['evidence']);facts['conflicts'].append(row)
        rows=self.query('''MATCH (a:Disease)-[:CONTRAINDICATES]->(r:ContraindicationRule {version:$version})-[:TARGETS]->(b:Ingredient)
        MATCH (r)-[:EVIDENCED_BY]->(e:Evidence)
        RETURN a.id AS disease,b.id AS ingredient,r.id AS rule,e.payload AS evidence''',{'version':version})
        for row in rows:row['evidence']=json.loads(row['evidence']);facts['disease_conflicts'].append(row)
        return facts

def get_graph(settings):
    if settings.validation_graph_mode=='fixture' and settings.validation_allow_demo:return DemoGraph()
    if settings.validation_graph_mode!='neo4j':raise GraphUnavailable()
    return Neo4jGraph(settings)
