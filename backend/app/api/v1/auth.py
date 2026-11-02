import re
import secrets
from datetime import timedelta
from uuid import uuid4
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from app.core.deps import DatabaseSession
from app.core.auth import require_account, hash_password, verify_password, token_hash, now, bearer
from app.models.auth import Account, LoginSession
from fastapi.security import HTTPAuthorizationCredentials

router = APIRouter(prefix='/api/auth', tags=['auth'])
class LoginInput(BaseModel):
    phone: str = Field(pattern=r'^1[3-9]\d{9}$')
    password: str = Field(min_length=1, max_length=128)
class RegisterInput(LoginInput):
    name: str = Field(min_length=1, max_length=30)

def user(account):
    return {'id': account.id, 'name': account.name, 'role': account.role}

@router.post('/register', status_code=201)
def register(data: RegisterInput, db: DatabaseSession):
    if not data.name.strip():
        raise HTTPException(422, '请填写您的称呼')
    if len(data.password) < 8 or not re.search(r'[A-Za-z]', data.password) or not re.search(r'\d', data.password):
        raise HTTPException(422, '密码至少 8 位，包含字母和数字')
    account = Account(id=str(uuid4()), phone=data.phone, name=data.name.strip(), password_hash=hash_password(data.password))
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, '该手机号已注册，请登录')
    return user(account)

@router.post('/login')
def login(data: LoginInput, db: DatabaseSession):
    account = db.scalar(select(Account).where(Account.phone == data.phone))
    # Equal work for an unknown account avoids a cheap timing signal.
    dummy = '00' * 16 + ':' + '00' * 64
    valid = verify_password(data.password, account.password_hash if account else dummy)
    if account is None or not valid:
        raise HTTPException(401, '手机号或密码错误')
    db.execute(delete(LoginSession).where(LoginSession.expires_at <= now()))
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=token_hash(token), account_id=account.id, expires_at=now()+timedelta(hours=8)))
    db.commit()
    return {'token': token, 'user': user(account)}

@router.get('/me')
def me(account=Depends(require_account)):
    return user(account)

@router.post('/logout', status_code=204)
def logout(db: DatabaseSession, account=Depends(require_account), credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]=None):
    db.execute(delete(LoginSession).where(LoginSession.token_hash == token_hash(credentials.credentials)))
    db.commit()
