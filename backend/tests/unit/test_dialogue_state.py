from types import SimpleNamespace
from app.services.chat.dialogue_state import build_dialogue,context_query
from app.schemas.chat import PolicyQuestion,ChatTurn
from app.agents.orchestrator import run_policy
from test_policy_graph import Model,hit,setup_retrieval

MESSAGES=['我能申请补贴吗','22岁温州市','温州市户籍，龙湾区，高龄补贴','养老长期护理保险','待遇标准','服务项目']


def test_six_real_user_turns_stop_menu_clarification_after_region_and_benefit(monkeypatch):
 calls=setup_retrieval(monkeypatch,[])
 history=[];state=None
 for index,message in enumerate(MESSAGES):
  state=build_dialogue([message],state)
  model=Model({'supported':True,'needs_clarification':True,'clarification':'请先选择补贴类别、待遇范围或具体服务形式。','query':None})
  answer=run_policy(PolicyQuestion(question=message,history=history[-6:],dialogue_state=state),None,SimpleNamespace(ensure_configured=lambda:None),None,model,['general'])
  if index<2: assert answer.status=='clarification'
  else:
   assert answer.status!='clarification' and 'retrieve' in answer.steps
   assert '温州市龙湾区' in calls[-1][0].query
   assert ('高龄津贴' if index==2 else '长期护理保险') in calls[-1][0].query
  history.extend([ChatTurn(role='user',content=message),ChatTurn(role='assistant',content=answer.answer)])
 assert len(calls)==4 and state.age==22 and state.household=='温州市户籍'
 assert state.benefit=='长期护理保险' and state.aspect=='服务项目'
 assert '服务项目' in calls[-1][0].query and '待遇标准' not in calls[-1][0].query


def test_retained_age_is_available_after_leaving_recent_three_pairs(monkeypatch):
 state=build_dialogue(MESSAGES)
 recent=[ChatTurn(role='user',content=message) for message in MESSAGES[-3:]]
 source='温州市长期护理保险资料：服务项目包括生活照护和医疗护理，待遇需核对参保状态与失能评估条件。'
 setup_retrieval(monkeypatch,[hit().model_copy(update={'text':source})])
 model=Model({'supported':True,'needs_clarification':True,'clarification':'请先选择居家或机构服务？','query':None},{'sufficient':True,'paragraphs':[{'text':'您提供的年龄为22岁。所引温州市长期护理保险资料列出生活照护和医疗护理服务，能否享受仍需核对参保状态与失能评估条件。','sources':[1]}]})
 answer=run_policy(PolicyQuestion(question='服务项目',history=recent,dialogue_state=state),None,SimpleNamespace(ensure_configured=lambda:None),None,model,['general'])
 assert answer.status=='answered' and answer.citations and 22 in model.review_calls[0]['user_provided_ages']


def test_state_never_rewrites_new_topics_and_resets_for_new_person_or_city():
 state=build_dialogue(MESSAGES)
 assert context_query(state,'今天的天气怎么样')=='今天的天气怎么样'
 assert context_query(state,'明天旅游')=='明天旅游'
 assert build_dialogue(['我母亲70岁'],state).region==''
 changed=build_dialogue(['宁波市户籍'],state)
 assert changed.region=='宁波市' and changed.district=='' and changed.household=='宁波市户籍'
 assert build_dialogue([]).age is None
 assert build_dialogue(['我今年23岁'],state).age==23
 assert build_dialogue(['不是22岁，是23岁'],state).age==23
 assert build_dialogue(['年龄不清楚'],state).age is None
 assert build_dialogue(['户籍是宁波市'],state).region=='宁波市'
 assert build_dialogue(['户籍是宁波市'],state).household=='宁波市户籍'


def test_high_age_alias_and_scheme_changes_do_not_mix_programs():
 state=build_dialogue(MESSAGES[:3])
 assert state.benefit=='高龄津贴'
 state=build_dialogue(['养老长期护理保险'],state)
 assert state.benefit=='长期护理保险'
 assert '高龄津贴' not in context_query(state,'待遇标准')
