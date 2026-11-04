"""Bounded read-only HowToCook MCP adapter. Never sends resident records."""
import asyncio
import json
import random
from contextlib import asynccontextmanager
from datetime import timedelta
from urllib.parse import urlsplit, quote
import anyio
from app.core.config import get_settings
from app.core.exceptions import BusinessError

CATEGORY_TOOL='mcp_howtocook_getRecipesByCategory'
DETAIL_TOOL='mcp_howtocook_getRecipeById'


def configuration(settings=None):
    s=settings or get_settings()
    return {'enabled':s.howtocook_enabled,'configured':bool(s.howtocook_mcp_url.get_secret_value().strip()),'provider':'HowToCook MCP'}

@asynccontextmanager
async def connect(settings):
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError:
        raise BusinessError('请在后端虚拟环境安装项目依赖：python -m pip install -e ".[dev]"，缺少 MCP SDK。',503) from None
    url=settings.howtocook_mcp_url.get_secret_value().strip()
    parsed=urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise BusinessError('HowToCook 连接地址须为有效的 HTTPS Streamable HTTP 地址。',503)
    headers={}
    token=settings.howtocook_api_token.get_secret_value()
    if token:headers['Authorization']='Bearer '+token
    async with streamablehttp_client(url,headers=headers,timeout=timedelta(seconds=20),sse_read_timeout=timedelta(seconds=30)) as (read,write,_):
        async with ClientSession(read,write) as session:
            await session.initialize()
            yield session


def decode(result):
    if getattr(result,'isError',False):raise ValueError('tool error')
    texts=[c.text for c in result.content if getattr(c,'type',None)=='text']
    text=''.join(texts)
    if len(text)>1_000_000:raise ValueError('oversized tool output')
    return json.loads(text)


def source_url(path):
    if not isinstance(path,str) or not path.startswith('dishes/') or '..' in path.split('/'):
        return None
    return 'https://github.com/Anduin2017/HowToCook/blob/master/'+quote(path,safe='/')


async def fetch(settings, connector=connect, seed=""):
    async with connector(settings) as session:
        listed=await session.list_tools()
        tools={t.name:t for t in listed.tools}
        if not {CATEGORY_TOOL,DETAIL_TOOL}<=tools.keys():raise ValueError('missing tools')
        schema=tools[CATEGORY_TOOL].inputSchema
        available=schema.get('properties',{}).get('category',{}).get('enum',[])
        categories=[c for c in settings.howtocook_categories if c in available]
        if not categories:raise ValueError('no supported categories')
        pools=[]
        for category in categories:
            rows=decode(await session.call_tool(CATEGORY_TOOL,{'category':category}))
            if not isinstance(rows,list):raise ValueError('invalid category response')
            pools.append([r for r in rows if isinstance(r,dict) and isinstance(r.get('id'),str) and isinstance(r.get('name'),str)])
        # Interleave categories, avoiding a candidate pool composed entirely of one category.
        rng=random.Random(seed)
        for pool in pools:rng.shuffle(pool)
        selected=[];seen=set()
        for index in range(max((len(p) for p in pools),default=0)):
            for pool in pools:
                if index<len(pool) and pool[index]['id'] not in seen:
                    seen.add(pool[index]['id']);selected.append(pool[index])
                    if len(selected)>=settings.howtocook_max_recipes:break
            if len(selected)>=settings.howtocook_max_recipes:break
        recipes=[]
        for row in selected:
            raw=decode(await session.call_tool(DETAIL_TOOL,{'query':row['id']}))
            if not isinstance(raw,dict) or raw.get('id')!=row['id']:continue
            ingredients=raw.get('ingredients');steps=raw.get('steps')
            if not isinstance(ingredients,list) or not isinstance(steps,list):continue
            names=[v['name'].strip() for v in ingredients if isinstance(v,dict) and isinstance(v.get('name'),str) and v['name'].strip()]
            instructions=[v['description'].strip() for v in steps if isinstance(v,dict) and isinstance(v.get('description'),str) and v['description'].strip()]
            if not names or not instructions:continue
            recipes.append({'id':row['id'][:160],'name':row['name'][:80],'category':str(raw.get('category',''))[:40],
                            'ingredients':list(dict.fromkeys(names))[:60],
                            'steps':[v[:400] for v in instructions[:8]],'source_url':source_url(raw.get('source_path'))})
        if not recipes:raise ValueError('no usable recipes')
        return {'status':'success','provider':'HowToCook MCP','recipes':recipes,'count':len(recipes)}


def candidates(settings=None,connector=connect,*,seed=""):
    s=settings or get_settings()
    if not s.howtocook_enabled:return {'status':'disabled','provider':'HowToCook MCP','recipes':[],'count':0}
    if not s.howtocook_mcp_url.get_secret_value().strip():
        raise BusinessError('已启用 HowToCook，请先在 backend/.env 填写 HOWTOCOOK_MCP_URL。',503)
    async def bounded():
        with anyio.fail_after(s.howtocook_timeout_seconds):return await fetch(s,connector,seed)
    try:return asyncio.run(bounded())
    except BusinessError:raise
    except Exception:
        # SDK errors can embed credential-bearing remote URLs: never expose or log their bodies.
        raise BusinessError('HowToCook 菜谱查询失败或超时，请检查连接有效期、传输类型及服务状态；当前菜单未被替换。',502) from None
