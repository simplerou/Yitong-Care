import json
from unittest.mock import patch
import httpx
import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.dialects.mysql import dialect,match

from app.core.config import Settings
from app.core.exceptions import BusinessError
from app.models import DocumentChunk
from app.services.embedding.openai_compatible import OpenAICompatibleEmbedder


def config():
    return Settings(_env_file=None,embedding_model='test-model',embedding_base_url='https://example.test/v1',embedding_dimensions=3,embedding_api_key='private-test-key')


def test_batch_split_response_order_normalization_and_mysql_match():
    requests=[];client=httpx.Client
    def respond(request):
        body=json.loads(request.content);requests.append(body)
        return httpx.Response(200,json={'data':[{'index':i,'embedding':[3.,4.,0.]} for i in reversed(range(len(body['input'])))]})
    with patch('app.services.embedding.openai_compatible.httpx.Client',lambda **kwargs:client(transport=httpx.MockTransport(respond),**kwargs)):
        result=OpenAICompatibleEmbedder(config()).embed(['test']*12)
    assert [len(r['input']) for r in requests]==[10,2]
    assert result.shape==(12,3) and result.dtype==np.float32
    assert np.allclose(np.linalg.norm(result,axis=1),1)
    compiled=str(select(DocumentChunk.id).where(match(DocumentChunk.content,against='助餐',in_natural_language_mode=True)>0).compile(dialect=dialect()))
    assert 'MATCH' in compiled and 'IN NATURAL LANGUAGE MODE' in compiled


def test_invalid_vectors_and_api_errors_are_not_persisted_or_leaked():
    client=httpx.Client
    for response in [httpx.Response(401,json={'error':{'message':'private-test-key'}}),httpx.Response(200,json={'data':[{'index':0,'embedding':[0.,0.,0.]}]}),httpx.Response(200,json={'data':[{'index':0,'embedding':[1.,2.]}]})]:
        with patch('app.services.embedding.openai_compatible.httpx.Client',lambda **kwargs:client(transport=httpx.MockTransport(lambda request:response),**kwargs)):
            with pytest.raises(BusinessError) as exc:
                OpenAICompatibleEmbedder(config()).embed(['test'])
            assert 'private-test-key' not in str(exc.value.message)
