from datetime import date,timedelta
from uuid import uuid4
from app.models import KnowledgeDocument,DocumentChunk
from app.operations.models import DrugReference
from app.operations.state import digest
from app.operations.evidence import retrieve

def test_drug_category_date_and_source_hash_filter_before_retrieval(client):
    api,_,factory=client
    with factory() as db:
        content='第一条 服用规则。第二条 禁忌事项。'
        doc=KnowledgeDocument(id='insert-doc',kb_id='medication',name='已核实说明书',type='txt',content=content,status='parsed')
        db.add(doc);db.flush()
        chunk=DocumentChunk(doc_id=doc.id,kb_id='medication',seq=0,content=content,start_offset=0,chars=len(content),vector_status='pending')
        db.add(chunk);db.flush()
        ref=DrugReference(id=str(uuid4()),drug_id='D-1',category='insert',chunk_id=chunk.id,section='第一条',valid_from=date.today()-timedelta(days=1),source_hash=digest({'doc':doc.id,'content':doc.content,'chunk':chunk.content,'start':0}))
        db.add(ref);db.commit()
        hits=retrieve(db,'D-1','服用规则');assert len(hits)==1
        assert hits[0]['section']=='第一条' and hits[0]['start']==0 and hits[0]['quote']==content
        assert retrieve(db,'D-2','服用规则')==[]
        assert retrieve(db,'D-1','服用规则',category='other')==[]
        assert retrieve(db,'D-1','服用规则',on_date=date.today()-timedelta(days=10))==[]
        doc.content='已修改原文';db.commit()
        assert retrieve(db,'D-1','服用规则')==[]
