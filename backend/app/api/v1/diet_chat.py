"""Dietitian HTTP surface: stateless chat plus persisted conversations."""
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.agents.diet_orchestrator import run_diet
from app.api.v1.embeddings import Manager, Model
from app.core.config import get_settings
from app.core.deps import DatabaseSession
from app.core.exceptions import BusinessError
from app.schemas.diet import DietAnswer, DietQuestion
from app.schemas.diet_conversation import (
    DietConversationQuestion, DietConversationRecord, DietProfileUpdate, DietStoredTurn,
)
from app.services import diet_conversations as conversations
from app.services.chat.llm import QwenClient, get_llm
from app.services.conversations import get_conversation_lock_dir
from app.services.diet.checks import DISCLAIMER
from app.services.diet.foods import TABLE_VERSION
from app.services.web.tavily import TavilySearch, get_web_search

router = APIRouter(prefix='/agents/diet', tags=['diet-agent'])
LockDirectory = Annotated[Path, Depends(get_conversation_lock_dir)]


@router.get('/config')
def config():
    settings = get_settings()
    return {'model': settings.llm_model,
            'configured': bool(settings.llm_model and settings.llm_base_url and settings.llm_api_key.get_secret_value()),
            'knowledge_scope': settings.diet_kb_ids,
            'web_configured': bool(settings.tavily_api_key.get_secret_value().strip()),
            'workflow': 'langgraph', 'streaming': False, 'enabled': settings.diet_enabled,
            'table_version': TABLE_VERSION, 'disclaimer': DISCLAIMER,
            'intents': ['meal_plan', 'protein', 'salt_control', 'fruit_staple', 'texture', 'food_safety',
                        'condition_diet', 'food_drug', 'education']}


def _run(request, db, embedder, manager, llm, web, progress=None):
    return run_diet(request, db, embedder, manager, llm, get_settings().diet_kb_ids,
                    web=web, progress=progress)


@router.post('/chat', response_model=DietAnswer)
def chat(request: DietQuestion, db: DatabaseSession, embedder: Model, manager: Manager,
         llm: Annotated[QwenClient, Depends(get_llm)], web: Annotated[TavilySearch, Depends(get_web_search)]):
    if not get_settings().diet_enabled: raise BusinessError('膳食营养师当前未启用。', 503)
    return _run(request, db, embedder, manager, llm, web)


@router.get('/conversations')
def conversation_list(db: DatabaseSession, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50)):
    return conversations.listing(db, page, page_size)


@router.post('/conversations', response_model=DietConversationRecord, status_code=201)
def conversation_create(db: DatabaseSession):
    return conversations.create(db)


@router.get('/conversations/{conversation_id}')
def conversation_detail(conversation_id: UUID, db: DatabaseSession, root: LockDirectory,
                        before_seq: int | None = Query(None, ge=1), page_size: int = Query(20, ge=1, le=50)):
    return conversations.detail(db, str(conversation_id), root, before_seq, page_size)


@router.delete('/conversations/{conversation_id}', status_code=204)
def conversation_delete(conversation_id: UUID, db: DatabaseSession, root: LockDirectory):
    conversations.delete(db, str(conversation_id), root)
    return Response(status_code=204)


@router.post('/conversations/{conversation_id}/turns', response_model=DietStoredTurn)
def conversation_ask(conversation_id: UUID, request: DietConversationQuestion, db: DatabaseSession,
                     root: LockDirectory, embedder: Model, manager: Manager,
                     llm: Annotated[QwenClient, Depends(get_llm)],
                     web: Annotated[TavilySearch, Depends(get_web_search)]):
    if not get_settings().diet_enabled: raise BusinessError('膳食营养师当前未启用。', 503)
    return conversations.ask(db, str(conversation_id), request, root,
                             lambda question: _run(question, db, embedder, manager, llm, web,
                                                   progress=lambda stage: conversations.record_stage(
                                                       db, str(conversation_id), str(request.request_id), stage)))


@router.put('/conversations/{conversation_id}/profile', response_model=DietConversationRecord)
def conversation_profile(conversation_id: UUID, request: DietProfileUpdate, db: DatabaseSession, root: LockDirectory):
    return conversations.update_profile(db, str(conversation_id), root, request.profile, request.dialogue_state)


@router.get('/conversations/{conversation_id}/turns/{request_id}/progress')
def conversation_progress(conversation_id: UUID, request_id: UUID, db: DatabaseSession):
    return conversations.progress(db, str(conversation_id), str(request_id))
