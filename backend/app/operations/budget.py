"""Request-local wall-clock budget shared by read-only tool calls."""
from contextvars import ContextVar
from time import monotonic
from fastapi import HTTPException
_deadline=ContextVar('ops_deadline',default=None)
def start(seconds=180):return _deadline.set(min(_deadline.get() or float('inf'),monotonic()+seconds))
def reset(token):_deadline.reset(token)
def remaining(cap=20):
    deadline=_deadline.get()
    seconds=cap if deadline is None else min(cap,deadline-monotonic())
    if seconds<=0:raise HTTPException(504,'协作任务超出执行预算，未继续生成草稿')
    return seconds
