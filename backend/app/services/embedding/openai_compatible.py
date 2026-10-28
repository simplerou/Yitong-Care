from typing import Sequence
from urllib.parse import urlsplit

import httpx
import numpy as np

from app.core.config import Settings, get_settings
from app.core.exceptions import BusinessError


class OpenAICompatibleEmbedder:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.key = settings.embedding_key
        self.model = settings.embedding_model
        self.dimensions = settings.embedding_dimensions

    def ensure_configured(self):
        url = urlsplit(self.settings.embedding_base_url)
        if not self.model or not self.settings.embedding_api_key.get_secret_value() or not url.hostname:
            raise BusinessError("请先在 backend/.env 配置 Embedding 地址、模型和 API Key。", 503)
        if url.scheme not in {"http", "https"} or url.username or url.password or url.query or url.fragment:
            raise BusinessError("Embedding 服务基础地址格式不正确。", 503)

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        self.ensure_configured()
        if not texts:
            return np.empty((0, self.dimensions), dtype=np.float32)
        vectors = []
        # qwen3.7 每次支持 20 行；对兼容服务统一以 10 行拆请求，兼容 v3/v4。
        try:
            with httpx.Client(timeout=httpx.Timeout(self.settings.embedding_timeout_seconds, connect=10), follow_redirects=False) as client:
                for start in range(0, len(texts), 10):
                    batch = list(texts[start:start + 10])
                    response = client.post(
                        self.settings.embedding_base_url.rstrip("/") + "/embeddings",
                        headers={"Authorization": "Bearer " + self.settings.embedding_api_key.get_secret_value()},
                        json={"model": self.model, "input": batch, "dimensions": self.dimensions, "encoding_format": "float"},
                    )
                    if response.status_code != 200:
                        raise BusinessError(f"Embedding 服务返回 HTTP {response.status_code}，请检查模型权限、额度和服务地址。", 502)
                    data = sorted(response.json()["data"], key=lambda item: item["index"])
                    if [item["index"] for item in data] != list(range(len(batch))):
                        raise ValueError("wrong batch indices")
                    array = np.asarray([item["embedding"] for item in data], dtype=np.float32)
                    if array.shape != (len(batch), self.dimensions) or not np.isfinite(array).all():
                        raise ValueError("invalid dimensions or values")
                    norms = np.linalg.norm(array, axis=1, keepdims=True)
                    if not np.isfinite(norms).all() or (norms <= 0).any():
                        raise ValueError("zero vector")
                    vectors.append(np.asarray(array / norms, dtype=np.float32))
        except httpx.RequestError as exc:
            raise BusinessError("无法连接 Embedding 服务，请检查网络后重试。", 502) from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise BusinessError("Embedding 返回格式或维度不正确，请检查模型配置。", 502) from exc
        return np.vstack(vectors)


def get_embedder() -> OpenAICompatibleEmbedder:
    return OpenAICompatibleEmbedder(get_settings())
