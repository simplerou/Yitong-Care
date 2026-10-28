import re
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from app.core.config import get_settings
from app.core.exceptions import BusinessError


class LocalFileStorage:
    """本地原文件适配器；业务层只保存 object_key，后续可替换为 MinIO。"""

    def __init__(self, root: Path, max_bytes: int):
        self.root = root.resolve()
        self.max_bytes = max_bytes

    def path(self, key: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}\.(pdf|docx|txt|md|markdown)", key):
            raise BusinessError("原文件标识无效。", 400)
        return self.root / key

    def save(self, stream: BinaryIO, suffix: str) -> tuple[str, int]:
        key = f"{uuid4().hex}.{suffix}"
        target = self.path(key)
        temp = target.with_suffix(target.suffix + ".part")
        size = 0
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            with temp.open("xb") as output:
                while data := stream.read(1024 * 1024):
                    size += len(data)
                    if size > self.max_bytes:
                        raise BusinessError("单个文件不能超过 50MB。", 413)
                    output.write(data)
            if not size:
                raise BusinessError("文件为空，请选择包含正文的文档。", 422)
            temp.replace(target)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
        return key, size

    def remove(self, key: str):
        self.path(key).unlink(missing_ok=True)


def get_storage() -> LocalFileStorage:
    settings = get_settings()
    return LocalFileStorage(settings.upload_dir, settings.max_upload_bytes)
