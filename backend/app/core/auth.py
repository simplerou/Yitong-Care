import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from typing import Annotated
from fastapi import Depends, HTTPException, Request
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

def require_session_account(db: DatabaseSession, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if credentials is None:
        raise HTTPException(401, '请先登录')
    session = db.get(LoginSession, token_hash(credentials.credentials))
    if session is None or session.expires_at <= now():
        raise HTTPException(401, '登录已失效，请重新登录')
    account = db.get(Account, session.account_id)
    if account is None:
        raise HTTPException(401, '登录已失效，请重新登录')
    if account.status in ('disabled','archived'):raise HTTPException(403,'账号已停用，请联系院长管理员')
    db.info['account_id'] = account.id
    db.info['account_role'] = account.role
    return account


def require_account(account=Depends(require_session_account)):
    if account.status != 'active':raise HTTPException(403,'账号尚未通过岗位审核，请查看申请状态')
    return account

def require_admin(account=Depends(require_account)):
    if account.role != 'admin':
        raise HTTPException(403, '此操作仅管理员可用')
    return account


def require_staff(db: DatabaseSession, request: Request, account=Depends(require_account)):
    if getattr(request.app.state,'legacy_compatibility',False) and account.role=='admin':return account
    if account.role=='user':return account
    if account.role in ('nursing','medical'):
        from app.operations.models import Credential
        from app.operations.contracts import current_date
        credential=db.get(Credential,account.id,populate_existing=True)
        if credential and credential.qualification and credential.valid_until>=current_date():return account
    raise HTTPException(403,'此功能仅授权照护岗位可用')


def require_nursing(db: DatabaseSession, request: Request, account=Depends(require_account)):
    if getattr(request.app.state,'legacy_compatibility',False) and account.role=='admin':return account
    if account.role!='nursing':raise HTTPException(403,'此操作仅护理部可用')
    from app.operations.models import Credential
    from app.operations.contracts import current_date
    credential=db.get(Credential,account.id,populate_existing=True)
    if not credential or not credential.qualification or credential.valid_until<current_date():raise HTTPException(403,'护理部任职资质未核实或已过期')
    return account
