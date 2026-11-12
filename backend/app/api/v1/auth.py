import re
import secrets
from datetime import timedelta
from uuid import uuid4
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from app.core.deps import DatabaseSession
from app.core.auth import require_account, require_session_account, require_admin, require_nursing, hash_password, verify_password, token_hash, now, bearer
from app.models.auth import Account, LoginSession
from fastapi.security import HTTPAuthorizationCredentials

router = APIRouter(prefix='/api/auth', tags=['auth'])
class LoginInput(BaseModel):
    phone: str = Field(pattern=r'^1[3-9]\d{9}$')
    password: str = Field(min_length=1, max_length=128)
class RegisterInput(LoginInput):
    name: str = Field(min_length=1, max_length=30)
    requested_role: Literal['user','medical','kitchen','nursing','finance']='user'
    application_note: str=Field(default='',max_length=500)

def user(account):
    return {'id':account.id,'name':account.name,'role':account.role,'status':account.status,'requested_role':account.requested_role,'application_note':account.application_note,'review_note':account.review_note,'application_version':account.application_version,'reviewed_at':account.reviewed_at}

@router.post('/register', status_code=201)
def register(data: RegisterInput, db: DatabaseSession):
    if not data.name.strip():
        raise HTTPException(422, '请填写您的称呼')
    if len(data.password) < 8 or not re.search(r'[A-Za-z]', data.password) or not re.search(r'\d', data.password):
        raise HTTPException(422, '密码至少 8 位，包含字母和数字')
    account = Account(id=str(uuid4()), phone=data.phone, name=data.name.strip(), password_hash=hash_password(data.password),role='user',status='pending',requested_role=data.requested_role,application_note=data.application_note.strip())
    db.add(account)
    try:
        db.flush()
        from app.operations.security import event
        event(db,account,'account_application_submitted',account.id,requested_role=account.requested_role,application_note=account.application_note,version=1)
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
    if account.status in ('disabled','archived'):raise HTTPException(403,'账号已停用，请联系院长管理员')
    db.execute(delete(LoginSession).where(LoginSession.expires_at <= now()))
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=token_hash(token), account_id=account.id, expires_at=now()+timedelta(hours=8)))
    db.commit()
    return {'token': token, 'user': user(account)}

@router.get('/me')
def me(account=Depends(require_session_account)):
    return user(account)

@router.post('/logout', status_code=204)
def logout(db: DatabaseSession, account=Depends(require_session_account), credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]=None):
    db.execute(delete(LoginSession).where(LoginSession.token_hash == token_hash(credentials.credentials)))
    db.commit()

@router.get('/caregivers')
def caregivers(db:DatabaseSession,account=Depends(require_nursing)):
    from app.models.resident import ResidentAssignment
    from sqlalchemy import func
    rows=db.execute(select(Account.id,Account.name,Account.phone,func.count(ResidentAssignment.resident_id)).outerjoin(ResidentAssignment,ResidentAssignment.account_id==Account.id).where(Account.role=='user',Account.status=='active').group_by(Account.id,Account.name,Account.phone).order_by(Account.name,Account.id)).all()
    return [{'id':key,'name':name,'phone_hint':phone[:3]+'****'+phone[-4:],'resident_count':count} for key,name,phone,count in rows]

class ReapplyInput(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True,extra='forbid')
    version:int=Field(ge=1)
    requested_role:Literal['user','medical','kitchen','nursing','finance']
    application_note:str=Field(default='',max_length=500)

@router.put('/application')
def reapply(data:ReapplyInput,db:DatabaseSession,account=Depends(require_session_account)):
    row=db.scalar(select(Account).where(Account.id==account.id).with_for_update().execution_options(populate_existing=True))
    if row.status!='rejected' or row.application_version!=data.version:raise HTTPException(409,'申请状态已变化，请刷新')
    before={'requested_role':row.requested_role,'review_note':row.review_note,'application_note':row.application_note}
    row.status='pending';row.requested_role=data.requested_role;row.application_note=data.application_note;row.review_note='';row.reviewed_at=None;row.application_version+=1
    from app.operations.security import event
    event(db,row,'account_application_resubmitted',row.id,before=before,requested_role=row.requested_role,application_note=row.application_note,version=row.application_version)
    db.commit();return user(row)
