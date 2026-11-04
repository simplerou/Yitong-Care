from uuid import uuid4
from sqlalchemy import select, delete, exists
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app.models.auth import Account, LoginSession
from app.models.resident import Resident, ResidentAccountBinding, ResidentAssignment, ResidentChange
from app.services.residents import snapshot

SELF_FIELDS = ('id','record_no','name','gender','birth_date','admission_date','status','location','care_level','allergies','chronic_conditions','dietary_notes','mobility_notes','communication_notes','care_notes')

def personal_record(db,account):
    if account.role!='resident':raise HTTPException(403,'当前账号不是老人账号')
    row=db.scalar(select(Resident).join(ResidentAccountBinding,ResidentAccountBinding.resident_id==Resident.id).where(ResidentAccountBinding.account_id==account.id))
    return {key:getattr(row,key) for key in SELF_FIELDS} if row else None

def current(db,resident_id):
    row=db.get(ResidentAccountBinding,resident_id)
    account=db.get(Account,row.account_id) if row else None
    return {'id':account.id,'name':account.name,'phone_hint':account.phone[:3]+'****'+account.phone[-4:]} if account else None

def candidates(db,q,page,page_size):
    filters=[Account.role.in_(['user','resident']),~exists(select(ResidentAccountBinding.account_id).where(ResidentAccountBinding.account_id==Account.id)),~exists(select(ResidentAssignment.account_id).where(ResidentAssignment.account_id==Account.id))]
    if q:
        pattern='%'+q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
        filters.append(Account.name.ilike(pattern,escape='\\') | Account.phone.ilike(pattern,escape='\\'))
    rows=db.scalars(select(Account).where(*filters).order_by(Account.name,Account.id).offset((page-1)*page_size).limit(page_size+1)).all()
    return {'items':[{'id':row.id,'name':row.name,'phone_hint':row.phone[:3]+'****'+row.phone[-4:]} for row in rows[:page_size]],'has_more':len(rows)>page_size,'page':page}

def set_binding(db,resident_id,account_id,version,reason,actor):
    row=db.scalar(select(Resident).where(Resident.id==resident_id).with_for_update().execution_options(populate_existing=True))
    if row is None:raise HTTPException(404,'档案不存在')
    if row.version!=version:raise HTTPException(409,'档案已变化，请重新加载核对后绑定')
    binding=db.scalar(select(ResidentAccountBinding).where(ResidentAccountBinding.resident_id==resident_id).with_for_update())
    old_id=binding.account_id if binding else None
    if old_id==account_id:return {'account':current(db,resident_id),'version':row.version}
    target=None
    if account_id:
        target=db.scalar(select(Account).where(Account.id==account_id).with_for_update().execution_options(populate_existing=True))
        if target is None:raise HTTPException(404,'账号不存在')
        if target.role not in ('user','resident'):raise HTTPException(422,'管理员账号不能绑定为老人账号')
        other=db.scalar(select(ResidentAccountBinding).where(ResidentAccountBinding.account_id==account_id).with_for_update())
        if other and other.resident_id!=resident_id:raise HTTPException(409,'该账号已绑定其他老人，请先核实并解绑')
        if db.scalar(select(ResidentAssignment.account_id).where(ResidentAssignment.account_id==account_id).limit(1).with_for_update()):
            raise HTTPException(409,'该账号已有工作人员负责范围，不能直接转换为老人账号')
    before=snapshot(db,row);before['bound_account_id']=old_id;before['bound_account']=current(db,resident_id)
    try:
        if binding:db.delete(binding);db.flush()
        if target:
            target.role='resident'
            db.add(ResidentAccountBinding(resident_id=resident_id,account_id=account_id))
        # Unbinding never restores staff privileges; the previous resident stays resident.
        affected=[key for key in [old_id,account_id] if key]
        if affected:db.execute(delete(LoginSession).where(LoginSession.account_id.in_(affected)))
        row.version+=1;db.flush()
        after=snapshot(db,row);after['bound_account_id']=account_id;after['bound_account']=current(db,resident_id)
        db.add(ResidentChange(id=str(uuid4()),resident_id=resident_id,actor_id=actor.id,actor_name=actor.name,reason=('绑定/更换老人账号：' if account_id else '解除老人账号绑定：')+reason,before=before,after=after))
        db.commit();db.refresh(row)
    except IntegrityError:
        db.rollback();raise HTTPException(409,'绑定关系已变化，请重新加载核对') from None
    return {'account':current(db,resident_id),'version':row.version}
