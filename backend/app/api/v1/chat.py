from typing import Annotated
from fastapi import APIRouter, Depends, Query, Response
from uuid import UUID
from pathlib import Path
from app.core.config import get_settings
from app.core.deps import DatabaseSession
from app.api.v1.embeddings import Model, Manager
from app.schemas.chat import PolicyQuestion, PolicyAnswer
from app.services.chat.llm import get_llm, QwenClient
from app.agents.orchestrator import run_policy
from app.services.web.tavily import get_web_search, TavilySearch

router = APIRouter(prefix='/agents/policy', tags=['policy-agent'])


@router.get('/config')
def config():
    settings = get_settings()
    return {'model':settings.llm_model, 'configured':bool(settings.llm_model and settings.llm_base_url and settings.llm_api_key.get_secret_value()),
            'knowledge_scope':settings.policy_kb_ids, 'web_configured':bool(settings.tavily_api_key.get_secret_value().strip()), 'workflow':'langgraph', 'streaming':False}


@router.post('/chat', response_model=PolicyAnswer)
def chat(request: PolicyQuestion, db: DatabaseSession, embedder: Model, manager: Manager,
         llm: Annotated[QwenClient, Depends(get_llm)], web: Annotated[TavilySearch, Depends(get_web_search)]):
    return run_policy(request, db, embedder, manager, llm, get_settings().policy_kb_ids, web=web)


from app.services import conversations
from app.schemas.conversation import ConversationQuestion, StoredTurn, ConversationRecord
LockDirectory=Annotated[Path,Depends(conversations.get_conversation_lock_dir)]


@router.get('/conversations')
def conversation_list(db: DatabaseSession,page: int=Query(1,ge=1),page_size: int=Query(20,ge=1,le=50)):
    return conversations.listing(db,page,page_size)


@router.post('/conversations',response_model=ConversationRecord,status_code=201)
def conversation_create(db: DatabaseSession):
    return conversations.create(db)


@router.get('/conversations/{conversation_id}')
def conversation_detail(conversation_id: UUID,db: DatabaseSession,root: LockDirectory,
                        before_seq: int | None=Query(None,ge=1),page_size: int=Query(20,ge=1,le=50)):
    return conversations.detail(db,str(conversation_id),root,before_seq,page_size)


@router.delete('/conversations/{conversation_id}',status_code=204)
def conversation_delete(conversation_id: UUID,db: DatabaseSession,root: LockDirectory):
    conversations.delete(db,str(conversation_id),root)
    return Response(status_code=204)


@router.post('/conversations/{conversation_id}/turns',response_model=StoredTurn)
def conversation_ask(conversation_id: UUID,request: ConversationQuestion,db: DatabaseSession,root: LockDirectory,
                     embedder: Model,manager: Manager,llm: Annotated[QwenClient,Depends(get_llm)],
                     web: Annotated[TavilySearch,Depends(get_web_search)]):
    return conversations.ask(db,str(conversation_id),request,root,
        lambda question:run_policy(question,db,embedder,manager,llm,get_settings().policy_kb_ids,web=web))
