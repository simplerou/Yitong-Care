from datetime import datetime,timedelta,date
from zoneinfo import ZoneInfo
def localnow():return datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
from hashlib import sha256
from decimal import Decimal,ROUND_HALF_UP
import json
from uuid import uuid4
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from app.models.resident import Resident,ResidentAssignment
from app.operations.models import ClinicalProfile,ConstraintToken,Shift
from app.operations.contracts import Patient
from app.operations.security import identity,resident

def utcnow():return datetime.utcnow()
def digest(value):return sha256(json.dumps(jsonable_encoder(value),sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def profile(db,key):
    row=db.get(ClinicalProfile,key,populate_existing=True);r=db.get(Resident,key,populate_existing=True)
    if not r or not row or row.resident_version!=r.version or r.status!='in_care':raise HTTPException(409,'结构化医护资料未核实或档案已变化，请医务室核对')
    return Patient.model_validate(row.data).model_dump(mode='json')
def context(db,key):
    r=db.get(Resident,key,populate_existing=True);p=db.get(ClinicalProfile,key,populate_existing=True)
    if not r:raise HTTPException(404,'不存在或无权')
    return {'resident_id':key,'resident_version':r.version,'profile_version':p.version if p else None,'profile':profile(db,key)}
def cohort(db):
    ids=list(db.scalars(select(Resident.id).where(Resident.status=='in_care').order_by(Resident.id)))
    if not ids:raise HTTPException(409,'暂无在院老人')
    return [context(db,key) for key in ids]
def issue_constraints(db,validator):
    rows=cohort(db)
    # Service, not kitchen Agent, sees the medical records. Conclusions contain no identities.
    check=validator.check({'kind':'medication','patients':[r['profile'] for r in rows],'medicines':[],'foods':[]})
    # A constraint token is not permission to prescribe. Unknown evidence must fail closed.
    if any(i['code'] not in ('medicines_required',) for i in check['issues']):raise HTTPException(409,'基础医护资料存在待核查冲突，不能建立食堂约束')
    public={'population':len(rows),'allergens':sorted({a for r in rows for a in r['profile']['allergens']}),'rule_version':check['rule_version'],'demo':check.get('demo',False)}
    token=ConstraintToken(id=str(uuid4()),private_context={'residents':rows},public_data=public,fingerprint=digest(rows),expires_at=utcnow()+timedelta(minutes=30))
    db.add(token);db.flush();return token

def resolve_context(db,actor,kind,data):
    if kind in ('menu','meal_swap') and date.fromisoformat(data['service_date'])<localnow().date():raise HTTPException(409,'餐食服务日期已过，请重新提交')
    if kind in ('medication','meal_swap','incident'):
        resident(db,actor,data['resident_id'])
        if kind=='incident':
            r=db.get(Resident,data['resident_id']);return {'resident_id':r.id,'resident_version':r.version}
        return context(db,data['resident_id'])
    if kind=='menu':
        token=db.get(ConstraintToken,data['constraint_token'],populate_existing=True)
        if not token or token.expires_at<=utcnow():raise HTTPException(409,'约束凭证已过期，请重新获取')
        current=cohort(db)
        if digest(current)!=token.fingerprint:raise HTTPException(409,'照护资料已变化，请重新获取脱敏约束')
        return {'residents':current,'token':token.id}
    if kind=='schedule':return schedule_state(db,data)
    if kind=='payroll':return payroll(db,data['month'])
    raise HTTPException(422,'未知业务类型')

def schedule_state(db,data):
    from app.models.auth import Account
    existing=list(db.scalars(select(Shift)))
    incoming=data['shifts'];result=[]
    for item in incoming:
        user=db.get(Account,item['account_id'],populate_existing=True)
        if not user or user.role!='user':raise HTTPException(422,'排班对象必须是护工')
        start=datetime.fromisoformat(item['start_at']);end=datetime.fromisoformat(item['end_at'])
        if start<localnow():raise HTTPException(409,'不能为已过去的时间建立新排班')
        for row in existing:
            if row.account_id==user.id and row.start_at<end and row.end_at>start:raise HTTPException(409,'排班时间重叠')
        for row in result:
            if row['account_id']==user.id and datetime.fromisoformat(row['start_at'])<end and datetime.fromisoformat(row['end_at'])>start:raise HTTPException(409,'草稿中的班次重叠')
        result.append(item)
    return {'shifts':result,'existing':sorted([{'id':r.id,'account_id':r.account_id,'start':r.start_at.isoformat(),'end':r.end_at.isoformat()} for r in existing],key=lambda r:r['id'])}

def payroll(db,month):
    year,m=map(int,month.split('-'));start=datetime(year,m,1);end=datetime(year+int(m==12),m%12+1,1)
    rows=db.scalars(select(Shift).where(Shift.start_at>=start,Shift.start_at<end).order_by(Shift.id)).all()
    from app.models.auth import Account
    totals={};sources=[];pending=[]
    for row in rows:
        sources.append({'id':row.id,'rate':row.hourly_rate,'in':row.checked_in,'out':row.checked_out})
        if not row.checked_in or not row.checked_out:pending.append(row.id);continue
        seconds=max(0,(min(row.checked_out,row.end_at)-max(row.checked_in,row.start_at)).total_seconds())
        amount=(Decimal(str(seconds))/3600*Decimal(row.hourly_rate)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
        item=totals.setdefault(row.account_id,{'account_id':row.account_id,'name':db.get(Account,row.account_id).name,'seconds':0,'amount':Decimal('0')})
        item['seconds']+=int(seconds);item['amount']+=amount
    for item in totals.values():item['amount']=str(item['amount'])
    return jsonable_encoder({'month':month,'lines':list(totals.values()),'pending':pending,'sources':sources,'formula':'有效打卡与排班交集秒数 / 3600 × 班次小时费率；逐班四舍五入到分；缺失打卡不按0处理'})
