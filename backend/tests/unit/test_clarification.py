from types import SimpleNamespace
from app.schemas.chat import PolicyQuestion,ChatTurn
from app.agents.orchestrator import run_policy
from app.services.chat.clarification import confirmed_question,explicit_standard_question
from test_policy_graph import Model,setup_retrieval

T02='只根据杭民发〔2024〕142号，上城区户籍85岁老人的高龄老年人养老服务补贴标准是多少？'
ASK='请确认老人户籍是否为杭州市上城区？'


def clarification(text=ASK):
    return dict(supported=True,needs_clarification=True,clarification=text,query=None)


def test_t02_goes_to_retrieval_instead_of_reconfirming_domicile(monkeypatch):
    calls=setup_retrieval(monkeypatch,[])
    answer=run_policy(PolicyQuestion(question=T02),None,SimpleNamespace(ensure_configured=lambda:None),None,Model(clarification()),['general'])
    assert answer.status=='insufficient' and 'retrieve' in answer.steps
    assert calls[0][0].query==T02
    assert not explicit_standard_question('我能申请养老补贴吗？')
    assert not explicit_standard_question('根据杭民发〔2024〕142号，我能否申请？')


def test_yes_after_binary_condition_confirmation_cannot_repeat_same_question(monkeypatch):
    calls=setup_retrieval(monkeypatch,[])
    request=PolicyQuestion(question='是的',history=[ChatTurn(role='user',content=T02),ChatTurn(role='assistant',content=ASK)])
    model=Model(clarification())
    answer=run_policy(request,None,SimpleNamespace(ensure_configured=lambda:None),None,model,['general'])
    assert 'retrieve' in answer.steps and answer.status!='clarification'
    assert T02 in calls[0][0].query and '肯定确认' in calls[0][0].query
    assert model.calls[0]['user_reply']=='是的' and ASK in model.calls[0]['question']


def test_missing_core_conditions_are_still_asked(monkeypatch):
    calls=setup_retrieval(monkeypatch,[])
    request=PolicyQuestion(question='是的',history=[ChatTurn(role='user',content='我能申请养老补贴吗'),ChatTurn(role='assistant',content=ASK)])
    answer=run_policy(request,None,None,None,Model(clarification('请问老人年龄是多少？')),['general'])
    assert answer.status=='clarification' and '类别' in answer.answer and not calls


def test_negative_ambiguous_or_policy_confirmation_is_not_promoted_to_personal_fact():
    for question,previous in [('不是',ASK),('是的','老人户籍在哪里？'),('是的','老人是否有户籍？年龄是多少？'),('是的','老人是否不属于上城区户籍？'),('是的','老人是否符合领取资格？')]:
        history=[ChatTurn(role='user',content=T02),ChatTurn(role='assistant',content=previous)]
        assert confirmed_question(question,history) is None


def test_t03_replaces_age_but_keeps_user_region_and_scheme(monkeypatch):
    from app.services.chat.clarification import age_followup_question
    calls=setup_retrieval(monkeypatch,[])
    history=[ChatTurn(role='user',content=T02),ChatTurn(role='assistant',content='上城区每人每月40元。')]
    resolved=age_followup_question('那90岁呢？',history)
    assert '90岁' in resolved and '85岁' not in resolved and '上城区户籍' in resolved
    model=Model(clarification('请问你咨询的是什么地方的？'))
    answer=run_policy(PolicyQuestion(question='那90岁呢？',history=history),None,SimpleNamespace(ensure_configured=lambda:None),None,model,['general'])
    assert 'retrieve' in answer.steps and calls[0][0].query==resolved
    assert model.calls[0]['question']==resolved and model.calls[0]['user_reply']=='那90岁呢？'


def test_age_followup_never_borrows_assistant_region_or_crosses_topic():
    from app.services.chat.clarification import age_followup_question
    assert age_followup_question('那90岁呢？',[]) is None
    assert age_followup_question('那90岁呢？',[ChatTurn(role='assistant',content=T02)]) is None
    history=[ChatTurn(role='user',content=T02),ChatTurn(role='user',content='我想咨询宁波的助餐服务')]
    assert age_followup_question('那90岁呢？',history) is None
    assert age_followup_question('那宁波90岁呢？',[ChatTurn(role='user',content=T02)]) is None


def test_subsequent_age_correction_uses_latest_age_only():
    from app.services.chat.clarification import age_followup_question
    history=[ChatTurn(role='user',content=T02),ChatTurn(role='user',content='那90岁呢？')]
    resolved=age_followup_question('我刚才说错了，是85岁',history)
    assert resolved==T02


def test_t06_amount_verification_retrieves_without_asking_user_to_read_policy(monkeypatch):
    calls=setup_retrieval(monkeypatch,[])
    question='上城区户籍90岁老人的高龄老年人养老服务补贴，是不是按杭民发〔2024〕142号每月领取9999元？'
    assert explicit_standard_question(question)
    answer=run_policy(PolicyQuestion(question=question),None,SimpleNamespace(ensure_configured=lambda:None),None,Model(clarification('请问老人户籍是否为杭州市上城区？文件是否明确适用90周岁及以上老人？')),['general'])
    assert 'retrieve' in answer.steps and calls[0][0].query==question
    assert not explicit_standard_question('按杭民发〔2024〕142号，我能不能领9999元？')
    assert not explicit_standard_question('是不是每月能领9999元？')


def test_t07_applicability_question_retrieves_without_intent_choice(monkeypatch):
    from app.services.chat.clarification import explicit_applicability_question
    calls=setup_retrieval(monkeypatch,[])
    question='宁波市户籍的老人，可以直接按杭民发〔2024〕142号中上城区的标准领取吗？'
    assert explicit_applicability_question(question)
    model=Model(clarification('请问您想了解宁波本地参照政策，还是异地申领杭州补贴？'))
    answer=run_policy(PolicyQuestion(question=question),None,SimpleNamespace(ensure_configured=lambda:None),None,model,['general'])
    assert 'retrieve' in answer.steps and calls[0][0].query==question
    assert answer.status=='insufficient'  # No source: do not invent a cross-region conclusion.
    assert not explicit_applicability_question('我能申请养老补贴吗？')
    assert not explicit_applicability_question('杭民发〔2024〕142号是什么？')
