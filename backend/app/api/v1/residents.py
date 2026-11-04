from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from app.core.auth import require_account, require_admin, require_staff
from app.core.deps import DatabaseSession
from app.models.auth import Account
from app.models.resident import ResidentChange
from app.schemas.resident import ResidentInput, ResidentUpdate
from app.services import residents, resident_binding
from pydantic import BaseModel, Field, ConfigDict
router=APIRouter(prefix='/residents',tags=['residents'])
Principal=Annotated[Account,Depends(require_account)]
Staff=Annotated[Account,Depends(require_staff)]
Admin=Annotated[Account,Depends(require_admin)]

@router.get('')
def listing(db:DatabaseSession,account:Staff,q:str=Query('',max_length=100),status:Literal['in_care','discharged']|None=None,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100)):
    return residents.listing(db,account,q.strip(),status,page,page_size)

@router.get('/assignees')
def assignees(db:DatabaseSession,account:Admin):
    return [{'id':row.id,'name':row.name,'phone_hint':row.phone[:3]+'****'+row.phone[-4:]} for row in db.scalars(select(Account).where(Account.role=='user').order_by(Account.name,Account.id))]

@router.post('',status_code=201)
def create(data:ResidentInput,db:DatabaseSession,account:Admin):
    return residents.create(db,data,account)

class BindingInput(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True,extra='forbid')
    account_id:UUID|None
    version:int=Field(ge=1)
    reason:str=Field(min_length=1,max_length=200)

@router.get('/me')
def personal_record(db:DatabaseSession,account:Principal):
    return {'resident':resident_binding.personal_record(db,account)}

@router.get('/bindable-accounts')
def bindable_accounts(db:DatabaseSession,account:Admin,q:str=Query('',max_length=100),page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=50)):
    return resident_binding.candidates(db,q.strip(),page,page_size)

@router.get('/{key}/account-binding')
def binding_detail(key:UUID,db:DatabaseSession,account:Admin):
    row=residents.require(db,str(key),account)
    return {'account':resident_binding.current(db,str(key)),'version':row.version}

@router.put('/{key}/account-binding')
def binding_update(key:UUID,data:BindingInput,db:DatabaseSession,account:Admin):
    return resident_binding.set_binding(db,str(key),str(data.account_id) if data.account_id else None,data.version,data.reason,account)

@router.get('/{key}')
def detail(key:UUID,db:DatabaseSession,account:Staff):
    return residents.detail(db,residents.require(db,str(key),account))

@router.put('/{key}')
def edit(key:UUID,data:ResidentUpdate,db:DatabaseSession,account:Admin):
    return residents.edit(db,str(key),data,account)

@router.get('/{key}/changes')
def changes(key:UUID,db:DatabaseSession,account:Admin,page:int=Query(1,ge=1),page_size:int=Query(10,ge=1,le=50)):
    residents.require(db,str(key),account)
    rows=db.scalars(select(ResidentChange).where(ResidentChange.resident_id==str(key)).order_by(ResidentChange.created_at.desc(),ResidentChange.id).offset((page-1)*page_size).limit(page_size)).all()
    return {'items':rows,'page':page,'page_size':page_size}
