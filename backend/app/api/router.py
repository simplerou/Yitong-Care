from fastapi import APIRouter, Depends
from app.core.auth import require_account, require_admin

from app.api.v1.chat import router as chat_router
from app.api.v1.health_chat import router as health_chat_router
from app.api.v1.medication_chat import router as medication_chat_router
from app.api.v1.diet_chat import router as diet_chat_router
from app.api.v1.safety_chat import router as safety_chat_router
from app.api.v1.mind_chat import router as mind_chat_router
from app.api.v1.health import router as health_router
from app.api.v1.documents import router as documents_router
from app.api.v1.chunks import router as chunks_router

from app.api.v1.embeddings import router as embeddings_router
from app.api.v1.retrieval import router as retrieval_router

from copy import copy
from app.api.v1.residents import router as residents_router
from app.api.v1.meals import router as meals_router
from app.api.v1.speech import router as speech_router
from app.api.v1.operations import router as operations_router


def create_api_router(*, legacy_compatibility: bool = False):
    router = APIRouter(prefix="/api", dependencies=[Depends(require_account)])
    if legacy_compatibility:
        for legacy in (documents_router, chunks_router, embeddings_router, retrieval_router):
            router.include_router(legacy, dependencies=[Depends(require_admin)])
        for legacy in (chat_router, health_chat_router, medication_chat_router,
                       diet_chat_router, safety_chat_router, mind_chat_router):
            router.include_router(legacy)
    for source in (residents_router, meals_router, speech_router, operations_router):
        selected = copy(source)
        selected.routes = list(source.routes)
        if not legacy_compatibility:
            def exposed(route):
                path = getattr(route, 'path', '')
                if path.startswith(('/operations/audit', '/operations/corrections', '/operations/drug-references')):
                    return False
                if path.startswith('/meals/'):
                    return path == '/meals/residents/{key}' and 'GET' in route.methods
                return path not in ('/residents/me', '/residents/bindable-accounts') and not path.endswith('/account-binding')
            selected.routes = [route for route in selected.routes if exposed(route)]
        router.include_router(selected)
    return router


api_router = create_api_router()
