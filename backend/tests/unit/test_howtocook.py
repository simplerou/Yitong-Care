from contextlib import asynccontextmanager
from types import SimpleNamespace as NS
import json
import pytest
from pydantic import SecretStr
from app.core.config import Settings
from app.core.exceptions import BusinessError
from app.services.howtocook import candidates,configuration,CATEGORY_TOOL,DETAIL_TOOL,source_url

def settings(**kwargs):
    return Settings(_env_file=None,howtocook_enabled=True,howtocook_mcp_url=SecretStr('https://example.com/mcp?secret=PRIVATE'),**kwargs)

class Session:
    def __init__(self):self.calls=[]
    async def list_tools(self):return NS(tools=[NS(name=CATEGORY_TOOL,inputSchema={'properties':{'category':{'enum':['早餐','素菜']}}}),NS(name=DETAIL_TOOL)])
    async def call_tool(self,name,args):
        self.calls.append((name,args))
        if name==CATEGORY_TOOL:
            raw=[{'id':args['category']+str(i),'name':'菜品'+str(i)} for i in range(6)]
        else:
            raw={'id':args['query'],'category':'素菜','ingredients':[{'name':'白菜'}],'steps':[{'description':'洗净后蒸熟'}],'source_path':'dishes/vegetable/白菜.md'}
        return NS(isError=False,content=[NS(type='text',text=json.dumps(raw))])

def connector_for(session):
    @asynccontextmanager
    async def connector(_):yield session
    return connector

def test_mcp_discovery_category_detail_and_balanced_bounded_pool():
    session=Session();result=candidates(settings(howtocook_max_recipes=6),connector_for(session))
    assert result['status']=='success' and result['count']==6
    assert result['recipes'][0]['id'].startswith('早餐')
    assert result['recipes'][1]['id'].startswith('素菜')
    assert len(session.calls)==8
    assert all(set(args)==({'category'} if name==CATEGORY_TOOL else {'query'}) for name,args in session.calls)
    assert all('PRIVATE' not in str(r) for r in result['recipes'])

def test_disabled_does_not_connect():
    s=Settings(_env_file=None,howtocook_enabled=False)
    assert candidates(s)['status']=='disabled'
    assert configuration(s)=={'enabled':False,'configured':False,'provider':'HowToCook MCP'}

def test_missing_url_is_explicit():
    with pytest.raises(BusinessError,match='HOWTOCOOK_MCP_URL'):
        candidates(Settings(_env_file=None,howtocook_enabled=True))

def test_remote_error_does_not_expose_url_or_silently_fallback():
    @asynccontextmanager
    async def broken(_):raise RuntimeError('https://example.com/PRIVATE_TOKEN');yield
    with pytest.raises(BusinessError) as error:candidates(settings(),broken)
    assert 'PRIVATE' not in error.value.message
    assert error.value.status_code==502

def test_unsafe_source_paths_are_not_linked():
    assert source_url('https://evil.com') is None
    assert source_url('dishes/../secrets') is None
    assert source_url('dishes/vegetable/白菜.md').startswith('https://github.com/Anduin2017/HowToCook/')
