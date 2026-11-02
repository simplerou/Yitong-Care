from uuid import uuid4
from sqlalchemy import select, func, exists, or_, update, delete
from fastapi import HTTPException
from app.models.resident import Resident, ResidentAssignment, ResidentChange
from app.models.auth import Account
from app.schemas.resident import ResidentInput

FIELDS = tuple(key for key in ResidentInput.model_fields if key != 'assigned_account_ids')

def scope(account):
    if account.role == 'admin': return True
    return exists(select(ResidentAssignment.resident_id).where(ResidentAssignment.resident_id==Resident.id,ResidentAssignment.account_id==account.id))

def require(db, key, account):
    row = db.scalar(select(Resident).where(Resident.id==key,scope(account)))
    if row is None: raise HTTPException(404,'档案不存在或无权访问')
    return row

def detail(db,row):
    data={key:getattr(row,key) for key in FIELDS}
    data.update(id=row.id,record_no=row.record_no,version=row.version,created_at=row.created_at,updated_at=row.updated_at)
    # JSON snapshots are stable and do not rely on live ORM objects.
    data['assigned_account_ids']=list(db.scalars(select(ResidentAssignment.account_id).where(ResidentAssignment.resident_id==row.id).order_by(ResidentAssignment.account_id)))
    return data

def snapshot(db,row):
    from fastapi.encoders import jsonable_encoder
    return jsonable_encoder(detail(db,row))

def validate_assignees(db, ids):
    if ids:
        found=set(db.scalars(select(Account.id).where(Account.id.in_(ids),Account.role=='user')))
        if found != set(ids): raise HTTPException(422,'负责人员必须是现有普通工作人员账号，请刷新人员列表')

def assign(db,key,ids):
    db.execute(delete(ResidentAssignment).where(ResidentAssignment.resident_id==key))
    db.add_all([ResidentAssignment(resident_id=key,account_id=account_id) for account_id in ids])
    db.flush()

def listing(db,account,q,status,page,page_size):
    filters=[scope(account)]
    if q:
        # Escape wildcards: searching a literal percent must not return all records.
        term='%'+q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
        filters.append(or_(*(field.ilike(term,escape='\\') for field in [Resident.name,Resident.record_no,Resident.location])))
    if status: filters.append(Resident.status==status)
    total=db.scalar(select(func.count()).select_from(Resident).where(*filters)) or 0
    rows=db.scalars(select(Resident).where(*filters).order_by(Resident.updated_at.desc(),Resident.id).offset((page-1)*page_size).limit(page_size)).all()
    return {'items':[{key:getattr(row,key) for key in ['id','record_no','name','gender','birth_date','location','care_level','status','updated_at']} for row in rows], 'total':total,'page':page,'page_size':page_size}

def create(db,data,account):
    validate_assignees(db,data.assigned_account_ids)
    row=Resident(id=str(uuid4()),record_no='R'+uuid4().hex[:12].upper(),version=1,**data.model_dump(exclude={'assigned_account_ids'}))
    db.add(row);db.flush();assign(db,row.id,data.assigned_account_ids)
    db.add(ResidentChange(id=str(uuid4()),resident_id=row.id,actor_id=account.id,actor_name=account.name,reason='新建档案',before=None,after=snapshot(db,row)))
    db.commit();db.refresh(row)
    return detail(db,row)

def edit(db,key,data,account):
    row=require(db,key,account)
    validate_assignees(db,data.assigned_account_ids)
    before=snapshot(db,row)
    values=data.model_dump(exclude={'assigned_account_ids','version','change_reason'})
    result=db.execute(update(Resident).where(Resident.id==key,Resident.version==data.version).values(**values,version=data.version+1).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback();raise HTTPException(409,'档案已被其他人更新，请重新加载后核对修改')
    assign(db,key,data.assigned_account_ids)
    db.refresh(row)
    db.add(ResidentChange(id=str(uuid4()),resident_id=key,actor_id=account.id,actor_name=account.name,reason=data.change_reason,before=before,after=snapshot(db,row)))
    db.commit();db.refresh(row)
    return detail(db,row)
