from contextlib import contextmanager
from pathlib import Path
import fcntl

from app.core.config import get_settings
from app.core.exceptions import BusinessError


@contextmanager
def index_write_lock(root: Path | None = None, *, blocking: bool = False):
    """单机跨进程写锁；读取已发布的不可变索引不需要此锁。"""
    directory = root or get_settings().faiss_index_dir
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".writer.lock").open("a+b") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError as exc:
            raise BusinessError("向量索引正在更新，请等待当前任务完成后重试。", 409) from exc
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
