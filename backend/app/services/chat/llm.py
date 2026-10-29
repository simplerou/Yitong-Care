"""Qwen via an OpenAI-compatible endpoint; errors never expose upstream bodies/keys."""
import json
from urllib.parse import urlsplit
import httpx
from app.core.config import get_settings
from app.core.exceptions import BusinessError


class QwenClient:
    def __init__(self, settings):
        self.settings = settings
        self.model = settings.llm_model

    def ensure_configured(self):
        url = urlsplit(self.settings.llm_base_url)
        if not self.model or not self.settings.llm_api_key.get_secret_value() or not url.hostname:
            raise BusinessError('请先配置 LLM_BASE_URL、LLM_API_KEY 和 LLM_MODEL。', 503)
        if url.scheme not in {'http', 'https'} or url.username or url.password or url.query or url.fragment:
            raise BusinessError('聊天模型基础地址格式不正确。', 503)

    def review_json(self, system: str, payload: dict) -> dict:
        return self.complete_json(system, payload, max_tokens=5000)

    def complete_json(self, system: str, payload: dict, *, max_tokens: int = 1800) -> dict:
        self.ensure_configured()
        try:
            with httpx.Client(timeout=httpx.Timeout(self.settings.llm_timeout_seconds, connect=10), follow_redirects=False) as client:
                response = client.post(self.settings.llm_base_url.rstrip('/') + '/chat/completions',
                    headers={'Authorization': 'Bearer ' + self.settings.llm_api_key.get_secret_value()},
                    json={'model': self.model, 'temperature': 0, 'max_tokens': max_tokens,
                          'response_format': {'type': 'json_object'}, 'messages': [
                              {'role':'system', 'content':system},
                              {'role':'user', 'content':json.dumps(payload, ensure_ascii=False)}]})
                if response.status_code != 200:
                    raise BusinessError(f'聊天模型返回 HTTP {response.status_code}，请检查模型权限、额度和服务地址。', 502)
                data = response.json()
                choice = data['choices'][0]
                if choice.get('finish_reason') != 'stop': raise ValueError('incomplete response')
                result = json.loads(choice['message']['content'])
                if not isinstance(result, dict): raise ValueError('invalid object')
                return result
        except httpx.TimeoutException:
            raise BusinessError('聊天模型请求超时，请重试。', 504) from None
        except httpx.HTTPError:
            raise BusinessError('无法连接聊天模型，请检查服务地址和网络。', 502) from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise BusinessError('聊天模型返回格式异常，请重试。', 502) from None


def get_llm():
    return QwenClient(get_settings())
