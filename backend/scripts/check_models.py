"""测试 .env 中的聊天及 Embedding 模型；不读取知识库，不输出密钥和完整向量。

在 backend 目录、agent_env 环境运行：python -m scripts.check_models
"""
import math
import os
import socket
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
CHAT_INPUT = "这是一次模型连接测试。请只回复 OK。"
EMBEDDING_INPUT = ["社区养老服务连接测试。", "居民可以到社区服务窗口咨询。"]


def config_values() -> dict[str, str]:
    # 与后端配置规则一致：系统环境变量优先于本地 .env。
    return {**{k: v or "" for k, v in dotenv_values(ENV_FILE).items()}, **os.environ}


def redact(message: str, values: dict[str, str]) -> str:
    for key in (values.get("LLM_API_KEY"), values.get("EMBEDDING_API_KEY")):
        if key:
            message = message.replace(key, "[已隐藏密钥]")
    return message[:240]


def connection_reason(error: BaseException) -> str:
    pending = [error]
    seen = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, socket.gaierror):
            return "DNS 无法解析模型服务域名，请检查网络或 DNS。"
        if isinstance(current, PermissionError):
            return "执行环境禁止网络连接，请在本机终端运行。"
        if current.__cause__:
            pending.append(current.__cause__)
        if current.__context__:
            pending.append(current.__context__)
        pending.extend(arg for arg in current.args if isinstance(arg, BaseException))
    return "无法连接服务，请检查网络、代理和 BASE_URL。"


def check_model(prefix: str, values: dict[str, str]) -> tuple[bool, str]:
    title = "聊天模型" if prefix == "LLM" else "向量模型"
    model = values.get(f"{prefix}_MODEL", "").strip()
    base = values.get(f"{prefix}_BASE_URL", "").strip().rstrip("/")
    key = values.get(f"{prefix}_API_KEY", "").strip()
    missing = [name for name, value in (("MODEL", model), ("BASE_URL", base), ("API_KEY", key)) if not value]
    if missing:
        return False, f"{title}：缺少配置 " + ", ".join(f"{prefix}_{name}" for name in missing)
    try:
        url = urlsplit(base)
        if url.scheme not in {"https", "http"} or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError()
        if url.path.endswith(("/chat/completions", "/embeddings")):
            raise ValueError()
        timeout = int(values.get(f"{prefix}_TIMEOUT_SECONDS") or "60")
        if not 1 <= timeout <= 300:
            raise ValueError()
    except ValueError:
        return False, f"{title}：BASE_URL 应填写 API 基础地址，超时应为 1–300 秒的整数。"

    if prefix == "LLM":
        endpoint = "/chat/completions"
        payload = {"model": model, "messages": [{"role": "user", "content": CHAT_INPUT}], "max_tokens": 32, "stream": False}
        if model.startswith("qwen"):
            payload["enable_thinking"] = False
    else:
        endpoint = "/embeddings"
        try:
            dimensions = int(values.get("EMBEDDING_DIMENSIONS", ""))
            if dimensions <= 0:
                raise ValueError()
        except ValueError:
            return False, "向量模型：请填写正整数 EMBEDDING_DIMENSIONS。"
        payload = {"model": model, "input": EMBEDDING_INPUT, "encoding_format": "float", "dimensions": dimensions}

    try:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=min(timeout, 10)), follow_redirects=False) as client:
            response = client.post(base + endpoint, headers={"Authorization": f"Bearer {key}"}, json=payload)
        if response.status_code != 200:
            detail = ""
            try:
                error = response.json().get("error", {})
                if isinstance(error, dict):
                    detail = redact(f"{error.get('code', '')} {error.get('message', '')}", values).strip()
            except (ValueError, AttributeError):
                pass
            return False, f"{title} {model}：HTTP {response.status_code}，{detail or '请检查服务地址、模型名称、区域和账号权限。'}"
        body = response.json()
        if prefix == "LLM":
            reply = body["choices"][0]["message"].get("content")
            if not isinstance(reply, str) or not reply.strip():
                raise ValueError("聊天模型未返回有效文本。")
            return True, f"聊天模型 {model}：连接成功，回复：{redact(reply, values)[:80]}"
        entries = sorted(body["data"], key=lambda item: item["index"])
        if [entry["index"] for entry in entries] != [0, 1]:
            raise ValueError("返回的向量数量或顺序不正确。")
        for entry in entries:
            vector = entry["embedding"]
            if not isinstance(vector, list) or len(vector) != dimensions:
                raise ValueError("实际向量维度与 EMBEDDING_DIMENSIONS 不一致。")
            if not all(type(number) in (int, float) and math.isfinite(number) for number in vector):
                raise ValueError("向量包含非数值或无穷值。")
            norm = sum(number * number for number in vector)
            if not math.isfinite(norm) or norm <= 0:
                raise ValueError("模型返回无效的向量。")
        return True, f"向量模型 {model}：连接成功，返回 {len(entries)} 条 {dimensions} 维向量。"
    except httpx.TimeoutException:
        return False, f"{title} {model}：请求超时，请检查网络及服务状态。"
    except httpx.RequestError as exc:
        return False, f"{title} {model}：{connection_reason(exc)}"
    except ValueError as exc:
        return False, f"{title} {model}：响应校验失败，{redact(str(exc), values)}"
    except (KeyError, IndexError, TypeError):
        return False, f"{title} {model}：返回格式与 OpenAI 兼容接口不一致。"


def main() -> int:
    values = config_values()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda prefix: check_model(prefix, values), ["LLM", "EMBEDDING"]))
    for _ok, message in results:
        print(message)
    return 0 if all(ok for ok, _message in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
