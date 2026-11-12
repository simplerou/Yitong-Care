"""Drug metadata filtering occurs before hybrid retrieval; references are mandatory."""
from datetime import date
from fastapi import HTTPException
from sqlalchemy import select,or_
from app.operations.models import DrugReference
from app.models import DocumentChunk,KnowledgeDocument
from app.operations.state import digest
from app.operations.contracts import current_date
from app.services.retrieval.bm25 import bm25


def eligible(db,drug_id,category,on_date):
    statement=select(DrugReference,DocumentChunk,KnowledgeDocument).join(DocumentChunk,DocumentChunk.id==DrugReference.chunk_id).join(KnowledgeDocument,KnowledgeDocument.id==DocumentChunk.doc_id).where(DrugReference.drug_id==drug_id,DrugReference.category==category,DrugReference.valid_from<=on_date,or_(DrugReference.valid_until.is_(None),DrugReference.valid_until>=on_date))
    result=[]
    for ref,chunk,doc in db.execute(statement):
        if not ref.section or ref.source_hash!=digest({'doc':doc.id,'content':doc.content,'chunk':chunk.content,'start':chunk.start_offset}):continue
        if not doc.content or doc.content[chunk.start_offset:chunk.start_offset+chunk.chars]!=chunk.content:continue
        result.append((ref,chunk,doc))
    return result

def retrieve(db,drug_id,query,category='insert',on_date=None,embedder=None,manager=None):
    on_date=on_date or current_date();rows=eligible(db,drug_id,category,on_date)
    if not rows:return []
    pool={chunk.id:(ref,chunk,doc) for ref,chunk,doc in rows}
    lexical=bm25(query,[(key,chunk.content) for key,(_,chunk,_) in pool.items()],limit=10)
    ranked=list(lexical) or list(pool)
    if embedder and manager:
        from app.schemas.retrieval import SearchRequest
        from app.services.retrieval.hybrid import search
        result=search(db,SearchRequest(query=query,scope='all',top_k=10,threshold=.02),embedder,manager,allowed_kb_ids=['medication'],allowed_chunk_ids=set(pool))
        ranked=[hit.chunk_id for hit in result.hits] or ranked
    return [{'drug_id':drug_id,'category':category,'section':pool[key][0].section,'location':f"{pool[key][2].name} · 字符 {pool[key][1].start_offset}—{pool[key][1].start_offset+pool[key][1].chars}",'doc_id':pool[key][2].id,'chunk_id':key,'start':pool[key][1].start_offset,'end':pool[key][1].start_offset+pool[key][1].chars,'quote':pool[key][1].content,'valid_from':pool[key][0].valid_from,'valid_until':pool[key][0].valid_until} for key in ranked[:10] if key in pool]
