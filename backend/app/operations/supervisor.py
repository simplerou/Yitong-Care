"""Identity-only front desk. It never interprets the user's clinical question."""
from typing import TypedDict,Any
from fastapi import HTTPException
from langgraph.graph import StateGraph,START,END
from app.operations.security import identity,ROLES
class DispatchState(TypedDict,total=False):
    role:str
    result:Any

def dispatch(db,actor,handlers):
    def authenticate(state):return {'role':identity(db,actor).role}
    def reject(state):raise HTTPException(404,'该身份没有此工作台入口')
    graph=StateGraph(DispatchState);graph.add_node('identity_card',authenticate);graph.add_node('reject',reject);graph.add_edge(START,'identity_card')
    targets={}
    for role in ROLES:
        name=role+'_agent'
        if role in handlers:
            def node(state,handler=handlers[role]):return {'result':handler()}
            graph.add_node(name,node);graph.add_edge(name,END);targets[role]=name
        else:targets[role]='reject'
    graph.add_conditional_edges('identity_card',lambda state:state['role'],targets)
    return graph.compile().invoke({}, {'recursion_limit':6})['result']
