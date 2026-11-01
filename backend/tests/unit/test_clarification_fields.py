from app.schemas.chat import PolicyQuestion,ChatTurn
from app.services.chat.clarification import explicitly_provided_fields,remaining_clarification
from test_policy_graph import Model,run,setup_retrieval

ASK='请问您的具体年龄（如22岁）、户籍类型（如温州市户籍）以及想了解的养老补贴类型（如高龄津贴、养老服务补贴、长期护理保险等）是？'


def test_t08_asks_only_benefit_after_user_supplies_age_and_domicile():
 history=[ChatTurn(role='user',content='我能申请养老补贴吗？'),ChatTurn(role='assistant',content='请问年龄、户籍及补贴类别？')]
 model=Model({'supported':True,'needs_clarification':True,'clarification':ASK,'query':None})
 result=run(model,PolicyQuestion(question='22岁温州市户籍',history=history))
 assert result.status=='clarification'
 assert '类别' in result.answer and '具体年龄' not in result.answer and '户籍类型' not in result.answer
 assert model.calls[0]['provided_fields']==['age','household_region']
 assert len(model.calls)==1


def test_structured_missing_fields_cannot_hide_repeated_fields_in_question():
 result=remaining_clarification(ASK,{'age','household_region'},['benefit'])
 assert '类别' in result and '年龄' not in result and '户籍' not in result


def test_age_only_keeps_region_and_benefit_questions():
 result=remaining_clarification(ASK,{'age'})
 assert '户籍地区' in result and '类别' in result and '年龄' not in result


def test_assistant_examples_are_not_user_facts():
 assert explicitly_provided_fields('我能申请吗？',[ChatTurn(role='assistant',content=ASK)])==set()


def test_uncertainty_and_new_person_do_not_reuse_old_fields():
 history=[ChatTurn(role='user',content='22岁温州市户籍')]
 assert 'household_region' not in explicitly_provided_fields('户籍不清楚',history)
 assert explicitly_provided_fields('我父亲70岁',history)=={'age'}
 assert explicitly_provided_fields('可能22岁，户籍不确定',[])==set()


def test_residence_is_not_treated_as_already_known_domicile():
 assert explicitly_provided_fields('22岁，目前住在温州市',[])=={'age'}
 refined=remaining_clarification('请问年龄和现居住地？',{'age','household_region'},['age','residence'])
 assert '现居住地' in refined and '年龄' not in refined


def test_all_requested_fields_known_then_retrieve_without_asserting_eligibility(monkeypatch):
 calls=setup_retrieval(monkeypatch,[])
 model=Model({'supported':True,'needs_clarification':True,'clarification':'请问年龄、户籍地区？','query':None,'missing_fields':['age','household_region']})
 result=run(model,PolicyQuestion(question='22岁温州市户籍，想了解长期护理保险'))
 assert 'retrieve' in result.steps and result.status=='insufficient' and calls
 assert not result.citations


def test_city_and_district_are_distinct_and_short_district_reply_is_retained():
 known=explicitly_provided_fields('22岁温州市户籍',[])
 assert 'household_region' in known and 'district' not in known
 question=remaining_clarification('请问户籍地区及具体在哪个区？',known,['household_region','district'])
 assert '区或县' in question
 assert explicitly_provided_fields('龙湾区的',[ChatTurn(role='user',content='22岁温州市户籍')])=={'age','household_region','district'}
