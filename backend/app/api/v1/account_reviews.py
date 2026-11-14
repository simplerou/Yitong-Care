"""Administrator-reviewed public applications; no self-authorized business access."""
from datetime import date
from typing import Annotated,Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select,func,delete
from sqlalchemy.orm import aliased
from app.core.auth import require_admin,now
from app.core.deps import DatabaseSession
from app.models.auth import Account,LoginSession
from app.operations.models import Credential,Event
from app.operations.contracts import current_date
from app.operations.security import event
from app.api.v1.auth import user
router=APIRouter(prefix='/api/account-reviews',tags=['account-reviews'],dependencies=[Depends(require_admin)])
Admin=Annotated[Account,Depends(require_admin)]

@router.get('')
def listing(db:DatabaseSession,actor:Admin,status:Literal['pending','rejected','active','disabled']='pending',page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100)):
    total=db.scalar(select(func.count()).select_from(Account).where(Account.status==status)) or 0
    rows=db.scalars(select(Account).where(Account.status==status).order_by(Account.name,Account.id).offset((page-1)*page_size).limit(page_size)).all()
    return {'items':[{**user(row),'phone_hint':row.phone[:3]+'****'+row.phone[-4:]} for row in rows],'total':total,'page':page,'page_size':page_size}

@router.get('/history')
def history(db:DatabaseSession,actor:Admin,result:Literal['all','approve','reject']='all',page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100)):
    actions=['account_application_'+value for value in (['approve','reject'] if result=='all' else [result])]
    condition=Event.action.in_(actions)
    total=db.scalar(select(func.count()).select_from(Event).where(condition)) or 0
    applicant=aliased(Account)
    reviewer=aliased(Account)
    records=db.execute(select(Event,applicant,reviewer).outerjoin(applicant,applicant.id==Event.object_id).outerjoin(reviewer,reviewer.id==Event.actor_id).where(condition).order_by(Event.created_at.desc(),Event.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    items=[]
    for record,person,operator in records:
        data=record.data or {}
        items.append({
            'id':record.id,'account_id':record.object_id,
            'applicant_name':data.get('applicant_name') or (person.name if person else '历史账号'),
            'phone_hint':data.get('phone_hint') or (person.phone[:3]+'****'+person.phone[-4:] if person else '未记录'),
            'reviewer_name':data.get('reviewer_name') or (operator.name if operator else '历史审核人'),
            'result':record.action.removeprefix('account_application_'),
            'requested_role':data.get('requested_role'),
            'granted_role':data.get('granted_role') if record.action.endswith('_approve') else None,
            'note':data.get('note',''),'qualification':data.get('qualification',''),
            'valid_until':data.get('valid_until'),'application_note':data.get('application_note'),
            'application_version':data.get('application_version'),'reviewed_at':record.created_at,
        })
    return {'items':items,'total':total,'page':page,'page_size':page_size}


class Review(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True,extra='forbid')
    version:int=Field(ge=1)
    action:Literal['approve','reject']
    role:Literal['user','medical','kitchen','nursing','finance']='user'
    note:str=Field(default='',max_length=1000)
    qualification:str=Field(default='',max_length=80)
    valid_until:date|None=None

@router.post('/{key}/decision')
def decide(key:str,data:Review,db:DatabaseSession,actor:Admin):
    row=db.scalar(select(Account).where(Account.id==key).with_for_update().execution_options(populate_existing=True))
    if not row:raise HTTPException(404,'账号不存在或无权')
    target='active' if data.action=='approve' else 'rejected'
    if row.status==target and row.application_version==data.version+1 and row.reviewed_at and row.review_note==data.note and (data.action=='reject' or row.role==data.role):return user(row)
    if row.status!='pending' or row.application_version!=data.version:raise HTTPException(409,'申请已经处理或发生变化，请刷新')
    if data.action=='reject' and not data.note:raise HTTPException(422,'请填写未通过原因，方便申请人补充资料')
    if data.action=='approve':
        if data.role in ('medical','nursing') and (not data.qualification or not data.valid_until or data.valid_until<current_date()):raise HTTPException(422,'专业岗位须登记有效资质和有效期')
        row.role=data.role
        credential=db.get(Credential,row.id)
        if credential:db.delete(credential);db.flush()
        if data.qualification and data.valid_until:db.add(Credential(account_id=row.id,qualification=data.qualification,valid_until=data.valid_until))
    row.status=target;row.review_note=data.note;row.reviewed_at=now();row.application_version+=1
    # The pending/rejected token must never silently become a privileged business token.
    db.execute(delete(LoginSession).where(LoginSession.account_id==row.id))
    event(db,actor,'account_application_'+data.action,key,applicant_name=row.name,phone_hint=row.phone[:3]+'****'+row.phone[-4:],reviewer_name=actor.name,application_note=row.application_note,application_version=data.version,requested_role=row.requested_role,granted_role=row.role,status=row.status,note=data.note,qualification=data.qualification,valid_until=data.valid_until.isoformat() if data.valid_until else None)
    db.commit();return user(row)

class StatusInput(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True,extra='forbid')
    version:int=Field(ge=1)
    status:Literal['active','disabled']
    note:str=Field(min_length=1,max_length=1000)

@router.put('/{key}/status')
def change_status(key:str,data:StatusInput,db:DatabaseSession,actor:Admin):
    admins=list(db.scalars(select(Account).where(Account.role=='admin',Account.status=='active').order_by(Account.id).with_for_update()))
    row=db.scalar(select(Account).where(Account.id==key).with_for_update().execution_options(populate_existing=True))
    if not row:raise HTTPException(404,'账号不存在或无权')
    if row.status not in ('active','disabled') or row.application_version!=data.version:raise HTTPException(409,'账号状态已变化，请刷新；新申请应先审核')
    if row.role=='admin' and row.status=='active' and data.status=='disabled' and len(admins)<=1:raise HTTPException(409,'不能停用最后一位有效院长账号')
    before=row.status;row.status=data.status;row.application_version+=1
    db.execute(delete(LoginSession).where(LoginSession.account_id==row.id))
    event(db,actor,'account_status_changed',row.id,before=before,after=row.status,note=data.note)
    db.commit();return user(row)
