from functools import lru_cache
from pathlib import Path
from hashlib import sha256

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    mysql_host: str = "127.0.0.1"
    mysql_port: int = Field(default=3306, ge=1, le=65535)
    mysql_database: str = Field(default="yitong_care", pattern=r"^[a-zA-Z0-9_]+$")
    mysql_user: str = "yitong"
    mysql_password: SecretStr = SecretStr("")
    mysql_unix_socket: str = ""
    mysql_pool_size: int = Field(default=5, ge=1, le=100)
    mysql_max_overflow: int = Field(default=10, ge=0, le=100)
    mysql_connect_timeout: int = Field(default=5, ge=1, le=60)
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]
    upload_dir: Path = BACKEND_DIR / "var" / "uploads"
    max_upload_bytes: int = Field(default=50 * 1024 * 1024, ge=1, le=50 * 1024 * 1024)
    embedding_base_url: str = ""
    embedding_api_key: SecretStr = SecretStr("")
    embedding_model: str = Field(default="", max_length=80)
    embedding_dimensions: int = Field(default=1024, ge=1, le=16384)
    embedding_timeout_seconds: int = Field(default=60, ge=1, le=300)
    embedding_revision: str = Field(default="1", max_length=32)
    faiss_index_dir: Path = BACKEND_DIR / "var" / "faiss"

    @property
    def embedding_key(self) -> str:
        identity = f"{self.embedding_base_url.rstrip('/')}|{self.embedding_model}|{self.embedding_dimensions}|{self.embedding_revision}"
        return f"{self.embedding_model}@{self.embedding_dimensions}:{sha256(identity.encode()).hexdigest()[:12]}"

    def database_url(self, *, include_database: bool = True) -> URL:
        query = {"charset": "utf8mb4"}
        if self.mysql_unix_socket:
            query["unix_socket"] = self.mysql_unix_socket
        # URL.create 正确处理密码中的 @、:、/、% 等字符，避免手工拼接 DSN。
        return URL.create(
            "mysql+pymysql",
            username=self.mysql_user,
            password=self.mysql_password.get_secret_value(),
            host=self.mysql_host,
            port=self.mysql_port,
            database=self.mysql_database if include_database else None,
            query=query,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
