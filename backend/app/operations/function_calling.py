"""Native Qwen/OpenAI-compatible tool calling; no simulated JSON tool selector."""
import httpx
from fastapi import HTTPException
from app.core.exceptions import BusinessError
from app.operations.budget import remaining

def function_call(client,messages,tools):
    client.ensure_configured()
    try:
        with httpx.Client(timeout=remaining(min(60,client.settings.llm_timeout_seconds)),follow_redirects=False) as transport:
            response=transport.post(client.settings.llm_base_url.rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+client.settings.llm_api_key.get_secret_value()},json={'model':client.model,'temperature':0,'max_tokens':1800,'messages':messages,'tools':tools,'tool_choice':'auto','parallel_tool_calls':False})
            if response.status_code!=200:raise HTTPException(502,'模型Function Calling请求失败，请检查模型服务配置')
            data=response.json()
        from app.services.chat.metrics import record_usage
        record_usage(data.get('usage'))
        choice=data['choices'][0]
        if choice['finish_reason'] not in ('stop','tool_calls'):raise ValueError()
        message=choice['message']
        if not isinstance(message,dict) or not isinstance(message.get('tool_calls',[]),list):raise ValueError()
        return message
    except (httpx.HTTPError,KeyError,TypeError,ValueError):raise HTTPException(502,'模型工具调用返回异常，未生成草稿') from None
