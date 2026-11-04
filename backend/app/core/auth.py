import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from typing import Annotated
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.deps import DatabaseSession
from app.models.auth import Account, LoginSession

bearer = HTTPBearer(auto_error=False)

def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + ':' + digest

def verify_password(password: str, stored: str) -> bool:
    return hmac.compare_digest(hash_password(password, stored.split(':')[0]), stored)

def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def require_account(db: DatabaseSession, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if credentials is None:
        raise HTTPException(401, '请先登录')
    session = db.get(LoginSession, token_hash(credentials.credentials))
    if session is None or session.expires_at <= now():
        raise HTTPException(401, '登录已失效，请重新登录')
    account = db.get(Account, session.account_id)
    if account is None:
        raise HTTPException(401, '登录已失效，请重新登录')
    db.info['account_id'] = account.id
    db.info['account_role'] = account.role
    return account


def require_admin(account=Depends(require_account)):
    if account.role != 'admin':
        raise HTTPException(403, '此操作仅管理员可用')
    return account


def require_staff(account=Depends(require_account)):
    if account.role not in ('admin', 'user'):
        raise HTTPException(403, '此页面仅供院内工作人员使用，请前往我的档案')
    return account
