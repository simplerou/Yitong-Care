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

api_router = APIRouter(prefix="/api", dependencies=[Depends(require_account)])

api_router.include_router(documents_router, dependencies=[Depends(require_admin)])
api_router.include_router(chunks_router, dependencies=[Depends(require_admin)])

api_router.include_router(embeddings_router, dependencies=[Depends(require_admin)])
api_router.include_router(retrieval_router, dependencies=[Depends(require_admin)])

api_router.include_router(chat_router)
api_router.include_router(health_chat_router)
api_router.include_router(medication_chat_router)
api_router.include_router(diet_chat_router)
api_router.include_router(safety_chat_router)
api_router.include_router(mind_chat_router)

from app.api.v1.residents import router as residents_router
api_router.include_router(residents_router)

from app.api.v1.meals import router as meals_router
api_router.include_router(meals_router)

from app.api.v1.speech import router as speech_router
api_router.include_router(speech_router)
