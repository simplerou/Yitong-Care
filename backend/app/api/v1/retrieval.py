from fastapi import APIRouter, Query, Response
from app.core.deps import DatabaseSession
from app.schemas.retrieval import SearchRequest, SearchResult
from app.api.v1.embeddings import Model, Manager
from app.services.retrieval import hybrid

router = APIRouter(prefix='/retrieval',tags=['retrieval'])


@router.post('/search',response_model=SearchResult)
def search(request: SearchRequest,db: DatabaseSession,embedder: Model,manager: Manager):
    embedder.ensure_configured()
    return hybrid.search(db,request,embedder,manager)


@router.get('/logs')
def logs(db: DatabaseSession,page: int=Query(default=1,ge=1),page_size: int=Query(default=20,ge=1,le=100)):
    return hybrid.logs(db,page,page_size)


@router.get('/logs/{log_id}',response_model=SearchResult)
def replay(log_id: str,db: DatabaseSession):
    return hybrid.replay(db,log_id)


@router.delete('/logs/{log_id}',status_code=204)
def remove(log_id: str,db: DatabaseSession):
    hybrid.remove_log(db,log_id);return Response(status_code=204)


@router.delete('/logs',status_code=204)
def clear(db: DatabaseSession):
    hybrid.remove_log(db);return Response(status_code=204)
