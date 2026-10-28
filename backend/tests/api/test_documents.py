from io import BytesIO
from zipfile import ZipFile

def upload(client, content='第一段是社区服务介绍。第二段说明如何登记。', name='社区说明.txt'):
    response = client.post('/api/documents', files={'file': (name, content.encode('utf-8'), 'text/plain')}, data={'kb_id': 'general', 'source': '社区窗口'})
    assert response.status_code == 202, response.text
    return response.json()['id']


def test_upload_parse_preview_save_detail_delete(client):
    api, storage, _factory = client
    text = ('服务窗口提供咨询。工作人员核对资料。居民可以预约服务。\n' * 6).strip()
    doc_id = upload(api, text)
    page = api.get('/api/documents').json()
    assert page['total'] == 1
    assert page['items'][0]['status'] == 'parsed'
    detail = api.get(f'/api/documents/{doc_id}').json()
    assert detail['content'] == text
    assert detail['source'] == '社区窗口'
    assert detail['created_at'].endswith('+00:00')
    parameters = {'size': 100, 'overlap': 30}
    preview = api.post(f'/api/documents/{doc_id}/chunks:preview', json=parameters)
    assert preview.status_code == 200
    assert preview.json()['count'] > 1
    assert api.get(f'/api/documents/{doc_id}').json()['chunk_count'] == 0
    saved = api.post(f'/api/documents/{doc_id}/chunks', json=parameters)
    assert saved.status_code == 200, saved.text
    for chunk in saved.json()['chunks']:
        assert chunk['id'] is not None
        assert text[chunk['start_offset']:chunk['start_offset'] + chunk['chars']] == chunk['content']
        assert chunk['chars'] <= 100
        assert api.get(f"/api/chunks/{chunk['id']}").status_code == 200
    assert api.get(f'/api/documents/{doc_id}').json()['status'] == 'chunked'
    assert api.get('/api/documents').json()['stats']['chunks'] == saved.json()['count']
    first_chunk_id = saved.json()['chunks'][0]['id']
    assert len(list(storage.root.glob('*.txt'))) == 1
    assert api.delete(f'/api/documents/{doc_id}').status_code == 204
    assert api.get(f'/api/documents/{doc_id}').status_code == 404
    assert api.get(f'/api/chunks/{first_chunk_id}').status_code == 404
    assert api.get('/api/documents').json()['stats'] == {'documents': 0, 'chunks': 0, 'vectors': 0, 'pending': 0}
    assert not list(storage.root.iterdir())


def test_rechunk_invalidates_vectors_and_index(client):
    api, _storage, factory = client
    text = '社区窗口提供咨询，居民可以预约服务。' * 12
    doc_id = upload(api, text)
    api.post(f'/api/documents/{doc_id}/chunks', json={'size': 150, 'overlap': 30})
    from app.models import DocumentChunk, KnowledgeDocument, VectorIndex
    from sqlalchemy import select
    with factory() as db:
        chunks = db.scalars(select(DocumentChunk).where(DocumentChunk.doc_id == doc_id)).all()
        old_ids = {c.id for c in chunks}
        for c in chunks:
            c.embedding = b'fake-vector'; c.vector_status = 'ready'
        db.get(KnowledgeDocument, doc_id).status = 'vectorized'
        db.add(VectorIndex(kb_id='general', model='test', dim=3, vector_count=len(chunks), version=1, path='test.faiss', status='ready'))
        db.commit()
    response = api.post(f'/api/documents/{doc_id}/chunks', json={'size': 100, 'overlap': 0})
    assert response.status_code == 200
    assert all(c['id'] not in old_ids and c['vector_status'] == 'pending' for c in response.json()['chunks'])
    assert api.get(f'/api/documents/{doc_id}').json()['vector_count'] == 0
    with factory() as db:
        assert db.scalar(select(VectorIndex)).status == 'stale'


def test_file_limits_and_type_checks_leave_no_orphans(client):
    api, storage, _factory = client
    assert api.post('/api/documents', files={'file': ('bad.exe', b'123')}).status_code == 415
    assert api.post('/api/documents', files={'file': ('old.doc', b'123')}).status_code == 415
    assert api.post('/api/documents', files={'file': ('empty.txt', b'')}).status_code == 422
    assert api.post('/api/documents', files={'file': ('large.txt', b'a' * 1025)}).status_code == 413
    assert api.post('/api/documents', files={'file': ('ok.txt', b'123')}, data={'kb_id': 'missing'}).status_code == 422
    assert api.get('/api/documents').json()['total'] == 0
    assert not storage.root.exists() or not list(storage.root.iterdir())


def test_real_docx_and_invalid_pdf_failure_retry(client):
    api, _storage, _factory = client
    data = BytesIO()
    with ZipFile(data, 'w') as z:
        z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>真实 Word 正文</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>表格内容</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
    response = api.post('/api/documents', files={'file': ('说明.docx', data.getvalue())})
    assert response.status_code == 202
    detail = api.get('/api/documents/' + response.json()['id']).json()
    assert detail['content'] == '真实 Word 正文\n表格内容'
    response = api.post('/api/documents', files={'file': ('bad.pdf', b'not a pdf')})
    doc_id = response.json()['id']
    detail = api.get(f'/api/documents/{doc_id}').json()
    assert detail['status'] == 'failed'
    assert '有效的 PDF' in detail['error_message']
    assert detail['content'] is None
    assert api.post(f'/api/documents/{doc_id}/chunks', json={'size': 100, 'overlap': 0}).status_code == 409
    assert api.post(f'/api/documents/{doc_id}/parse:retry').status_code == 202
    assert api.get(f'/api/documents/{doc_id}').json()['status'] == 'failed'


def test_search_pagination_and_parameter_validation(client):
    api, _storage, _factory = client
    upload(api, name='社区%说明.txt')
    upload(api, name='其他说明.txt')
    page = api.get('/api/documents?q=%25&page_size=1').json()
    assert page['total'] == 1
    assert page['items'][0]['name'] == '社区%说明.txt'
    assert api.get('/api/documents?page_size=1&page=2').json()['items']
    assert api.get('/api/documents?page=0').status_code == 422
    doc_id = page['items'][0]['id']
    assert api.post(f'/api/documents/{doc_id}/chunks:preview', json={'size': 100, 'overlap': 100}).status_code == 422
    assert api.delete('/api/documents/missing').status_code == 404


def test_interrupted_parsing_can_be_retried_after_timeout(client):
    from datetime import UTC, datetime, timedelta
    from app.models import KnowledgeDocument
    api, _storage, factory = client
    doc_id = upload(api)
    with factory() as db:
        doc = db.get(KnowledgeDocument, doc_id)
        doc.status = 'parsing'
        doc.updated_at = datetime.now(UTC).replace(tzinfo=None)
        db.commit()
    assert api.post(f'/api/documents/{doc_id}/parse:retry').status_code == 409
    with factory() as db:
        db.get(KnowledgeDocument, doc_id).updated_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=11)
        db.commit()
    assert api.post(f'/api/documents/{doc_id}/parse:retry').status_code == 202
    assert api.get(f'/api/documents/{doc_id}').json()['status'] == 'parsed'


def test_database_failure_cleans_upload_and_restores_deleted_file(client, monkeypatch):
    from sqlalchemy.exc import OperationalError
    api, storage, factory = client
    original_commit = factory.class_.commit

    def failed_commit(_session):
        raise OperationalError('COMMIT', {}, Exception('simulated failure'))

    monkeypatch.setattr(factory.class_, 'commit', failed_commit)
    response = api.post('/api/documents', files={'file': ('new.txt', b'new content')})
    assert response.status_code == 503
    assert not list(storage.root.iterdir())
    assert api.get('/api/documents').json()['total'] == 0
    monkeypatch.setattr(factory.class_, 'commit', original_commit)
    doc_id = upload(api)
    monkeypatch.setattr(factory.class_, 'commit', failed_commit)
    assert api.delete(f'/api/documents/{doc_id}').status_code == 503
    assert api.get(f'/api/documents/{doc_id}').status_code == 200
    assert len(list(storage.root.glob('*.txt'))) == 1
    assert not list(storage.root.glob('*.deleting'))
