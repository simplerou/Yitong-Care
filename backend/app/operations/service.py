from datetime import datetime,date,timedelta
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select,func
from app.models.auth import Account,LoginSession
from app.models.resident import Resident,ResidentAssignment
from app.operations.models import Draft,Execution,Correction,Shift,ClinicalProfile,Event,Credential
from app.operations.security import identity,gate,resident,event,TASK_TOOL,TASK_TO_ROLE
from app.operations.state import utcnow,digest,resolve_context
from app.operations.workflow import check,normalize,public_validation

APPROVERS={'medication':'admin','menu':'admin','schedule':'admin','payroll':'admin','meal_swap':'kitchen','incident':'nursing'}

def permitted(db,actor,row):
    card=identity(db,actor)
    if card.role in ('medical','nursing') and not card.qualified:return False
    return card.role=='admin' or (row.owner_id==actor.id and card.role==TASK_TO_ROLE[row.kind]) or card.role==APPROVERS[row.kind]

def draft(db,actor,key,lock=False):
    query=select(Draft).where(Draft.id==key)
    if lock:query=query.with_for_update()
    row=db.scalar(query.execution_options(populate_existing=True))
    if not row or not permitted(db,actor,row):
        event(db,actor,'draft_access_denied',key,reason='missing' if not row else 'out_of_scope');db.commit();raise HTTPException(404,'不存在或无权')
    return row

def serialize(db,actor,row):
    if not permitted(db,actor,row):raise HTTPException(404,'不存在或无权')
    role=identity(db,actor).role
    payload=dict(row.current)
    proposed=dict(row.proposed)
    if role=='admin':
        gate(db,actor,'view_validation');gate(db,actor,'view_cost')
        payload={};proposed={}
    if role=='kitchen':
        for obj in (payload,proposed):obj.pop('resident_id',None)
    trace=row.trace if role in ('medical',) or row.kind not in ('medication','meal_swap') else [{'node':step['node']} for step in row.trace]
    if role=='admin':trace=[{'node':step['node']} for step in row.trace]
    from app.models.resident import Resident
    target=db.get(Resident,row.private_context.get('resident_id')) if row.private_context.get('resident_id') and role not in ('kitchen','admin') else None
    derived={key:row.private_context[key] for key in ('month','lines','pending','formula') if key in row.private_context} if row.kind=='payroll' and role in ('finance','admin') else {}
    if role=='admin' and row.kind=='payroll':
        from decimal import Decimal
        derived={'total_amount':str(sum((Decimal(line['amount']) for line in row.private_context.get('lines',[])),Decimal('0'))),'pending_count':len(row.private_context.get('pending',[]))}
    signoff=row.professional_signoff
    public_signoff={'signed':True,'signed_at':signoff['signed_at']} if signoff else None
    return {'professional_signoff':public_signoff,'can_sign':role=='medical' and row.kind=='medication' and row.owner_id==actor.id and row.status=='pending','was_modified':row.proposed!=row.current,'resident_name':target.name if target else None,'calculation':derived,'id':row.id,'kind':row.kind,'status':'expired' if row.status=='pending' and row.expires_at<=utcnow() else row.status,'risk':row.risk,'version':row.version,'proposed':proposed,'current':payload,'validation':public_validation(row.validation,role),'trace':trace,'expires_at':row.expires_at,'created_at':row.created_at,'decision_note':row.decision_note,'can_approve':role==APPROVERS[row.kind] and (row.kind!='medication' or bool(signoff)),'can_edit':row.owner_id==actor.id and row.status=='pending' and (role!='user' or row.kind=='meal_swap'),'owner_id':row.owner_id}

def pending(row,version):
    if row.status!='pending':raise HTTPException(409,'草稿已经处理')
    if row.expires_at<=utcnow():raise HTTPException(409,'草稿已过期，请重新生成')
    if row.version!=version:raise HTTPException(409,'草稿版本已变化，请刷新')

def revision(db,actor,key,data,validator):
    row=draft(db,actor,key,True);pending(row,data.version)
    if row.owner_id!=actor.id:raise HTTPException(404,'不存在或无权')
    if actor.role=='user' and row.kind!='meal_swap':raise HTTPException(403,'上报记录不能编辑，请追加上报')
    gate(db,actor,TASK_TOOL[row.kind])
    payload=normalize(row.kind,data.payload)
    # Corrections cannot redirect a draft to a different resident/cohort.
    for field in ('resident_id','constraint_token'):
        if payload.get(field)!=row.current.get(field):raise HTTPException(422,'修改不能更换草稿目标，请重新生成')
    private,result=check(db,actor,row.kind,payload,validator)
    before=row.current;previous_validation=row.validation;previous_source_hash=row.source_hash;previous_version=row.version
    row.current=payload;row.validation=result;row.risk=result['risk'];row.private_context=private;row.source_hash=digest(private);row.professional_signoff=None;row.version+=1
    row.trace=row.trace+[{'node':'human_revision','version':row.version,'rule_version':result['rule_version'],'risk':result['risk'],'route':data.route,'tag':data.tag}]
    correction_id=str(uuid4())
    db.add(Correction(id=correction_id,draft_id=row.id,actor_id=actor.id,route=data.route,tag=data.tag,reason=data.reason,before=before,after=payload,closed=False))
    event(db,actor,'draft_revised',row.id,route=data.route,tag=data.tag,correction_id=correction_id,previous_version=previous_version,version=row.version,previous_validation=previous_validation,validation=result,previous_source_hash=previous_source_hash,source_hash=row.source_hash)
    db.commit();return row

def lock_sources(db,row,actor):
    account_ids=sorted({actor.id,row.owner_id})
    list(db.scalars(select(Account).where(Account.id.in_(account_ids)).order_by(Account.id).with_for_update()))
    list(db.scalars(select(Credential).where(Credential.account_id.in_(account_ids)).order_by(Credential.account_id).with_for_update()))
    ids=([row.private_context['resident_id']] if 'resident_id' in row.private_context else [r['resident_id'] for r in row.private_context.get('residents',[])])
    if ids:
        list(db.scalars(select(Resident).where(Resident.id.in_(ids)).order_by(Resident.id).with_for_update()))
        list(db.scalars(select(ClinicalProfile).where(ClinicalProfile.resident_id.in_(ids)).order_by(ClinicalProfile.resident_id).with_for_update()))
    if row.kind=='payroll':list(db.scalars(select(Shift).order_by(Shift.id).with_for_update()))

def decision(db,actor,key,data,validator):
    row=draft(db,actor,key,True)
    card=identity(db,actor)
    if card.role!=APPROVERS[row.kind] or (card.role=='nursing' and not card.qualified):raise HTTPException(404,'不存在或无权')
    # Same decision on the same version is idempotent, without new execution rows.
    target='approved' if data.action=='approve' else 'rejected'
    if row.status==target and row.decision_by==actor.id and data.version==row.version-1:return row
    pending(row,data.version)
    lock_sources(db,row,actor)
    card=identity(db,actor)
    if card.role!=APPROVERS[row.kind] or (card.role=='nursing' and not card.qualified):raise HTTPException(404,'不存在或无权')
    if row.risk>=3 and not data.note.strip():raise HTTPException(422,'高风险确认必须填写专业核对意见')
    if row.owner_id==actor.id:raise HTTPException(409,'不得审批自己提交的草稿')
    owner=db.get(Account,row.owner_id,populate_existing=True)
    gate(db,owner,TASK_TOOL[row.kind])
    if data.action=='approve':
        if row.kind=='medication':
            signature=row.professional_signoff
            if not signature or signature['version']!=row.version or signature['payload_hash']!=digest(row.current) or signature['source_hash']!=row.source_hash or signature['rule_version']!=row.validation['rule_version'] or signature['graph_hash']!=row.validation['graph_hash']:raise HTTPException(409,'必须先由医务室医生核对并签字；修改后需要重新签字')
        lock_sources(db,row,actor)
        gate(db,owner,TASK_TOOL[row.kind])
        private,result=check(db,owner,row.kind,row.current,validator)
        if digest(private)!=row.source_hash:raise HTTPException(409,'源资料或业务状态已变化，请退回重新生成')
        if result['rule_version']!=row.validation['rule_version'] or result['graph_hash']!=row.validation['graph_hash']:raise HTTPException(409,'规则或图事实版本已变化，请退回复校')
        row.validation=result
        build_execution(db,row,actor)
        row.trace=row.trace+[{'node':'approval_recheck','passed':True,'rule_version':result['rule_version']},{'node':'execution_created'}]
    row.status=target;row.version+=1;row.decision_by=actor.id;row.decision_note=data.note
    event(db,actor,'draft_'+target,row.id,risk=row.risk,rule_version=row.validation['rule_version'],modified=digest(row.proposed)!=digest(row.current))
    db.commit();return row

def build_execution(db,row,actor):
    resident_id=row.private_context.get('resident_id')
    if row.kind=='schedule':
        # Serialize shifts per account to prevent concurrent overlapping schedule approvals.
        ids=sorted({item['account_id'] for item in row.current['shifts']})
        list(db.scalars(select(Account).where(Account.id.in_(ids)).order_by(Account.id).with_for_update()))
        from app.operations.state import schedule_state
        schedule_state(db,row.current)
        for shift in row.current['shifts']:
            db.add(Shift(id=str(uuid4()),draft_id=row.id,account_id=shift['account_id'],start_at=datetime.fromisoformat(shift['start_at']),end_at=datetime.fromisoformat(shift['end_at']),hourly_rate=shift['hourly_rate']))
    if row.kind=='medication':
        # Approved orders become part of the profile before menus can be validated.
        p=db.get(ClinicalProfile,resident_id)
        medicines={m['drug_id']:m for m in p.data['medicines']};medicines.update({m['drug_id']:m for m in row.current['medicines']})
        from app.services.residents import snapshot
        from app.models.resident import ResidentChange
        target=db.get(Resident,resident_id);before=snapshot(db,target);clinical_before=p.data
        target.version+=1
        p.data={**p.data,'medicines':list(medicines.values())};p.version+=1;p.resident_version=target.version;db.flush()
        db.add(ResidentChange(id=str(uuid4()),resident_id=resident_id,actor_id=actor.id,actor_name=actor.name,reason='院长批准医务室用药草稿',before=before,after=snapshot(db,target)))
        event(db,actor,'clinical_orders_applied',resident_id,before=clinical_before,after=p.data,draft_id=row.id,ordered_by=row.owner_id)
        from app.operations.state import context
        row.private_context=context(db,resident_id);row.source_hash=digest(row.private_context)
    if row.kind in ('medication','meal_swap'):
        tasks=[(resident_id,None,{'kind':row.kind,**{k:v for k,v in row.current.items() if k!='resident_id'}})]
    elif row.kind=='menu':tasks=[(None,None,{'kind':'menu','title':row.current['title'],'foods':row.current['foods'],'service_date':row.current['service_date']})]
    else:tasks=[]
    if row.kind=='meal_swap':tasks.append((None,None,{'kind':'meal_swap_prepare','foods':row.current['foods'],'servings':1,'service_date':row.current['service_date']}))
    for n,(key,assignee,data) in enumerate(tasks):
        db.add(Execution(id=str(uuid4()),draft_id=row.id,resident_id=key,assignee_id=assignee,sequence=n,status='pending',data=data,result={}))

def executions(db,actor):
    card=identity(db,actor)
    query=select(Execution).order_by(Execution.created_at.desc())
    if card.role=='user':query=query.where(Execution.resident_id.in_(select(ResidentAssignment.resident_id).where(ResidentAssignment.account_id==actor.id)))
    elif card.role=='kitchen':query=query.where(Execution.resident_id.is_(None))
    elif card.role not in ('nursing','medical'):raise HTTPException(404,'不存在或无权')
    if card.role in ('medical','nursing') and not card.qualified:raise HTTPException(404,'不存在或无权')
    return list(db.scalars(query.limit(200)))

def complete(db,actor,key,note,validator):
    card=identity(db,actor)
    gate(db,actor,'confirm_preparation' if card.role=='kitchen' else 'complete_task')
    row=db.scalar(select(Execution).where(Execution.id==key).with_for_update().execution_options(populate_existing=True))
    if not row:raise HTTPException(404,'不存在或无权')
    if card.role=='kitchen':
        if row.resident_id is not None:raise HTTPException(404,'不存在或无权')
    elif row.resident_id:resident(db,actor,row.resident_id,True)
    else:raise HTTPException(404,'不存在或无权')
    if row.status=='completed':return row
    if row.status!='pending':raise HTTPException(409,'执行单已撤销或不可执行')
    source=db.get(Draft,row.draft_id,populate_existing=True)
    if source.status!='approved':raise HTTPException(409,'执行单没有有效审批')
    if source.kind=='medication' and (not source.professional_signoff or source.professional_signoff['payload_hash']!=digest(source.current)):raise HTTPException(409,'用药执行单缺少有效医生签字')
    if source.kind=='meal_swap' and card.role=='user':
        preparation=db.scalar(select(Execution).where(Execution.draft_id==source.id,Execution.resident_id.is_(None)))
        if not preparation or preparation.status!='completed':raise HTTPException(409,'请等待食堂确认备餐完成')
    lock_sources(db,source,actor)
    owner=db.get(Account,source.owner_id,populate_existing=True)
    gate(db,owner,TASK_TOOL[source.kind])
    private,result=check(db,owner,source.kind,source.current,validator)
    if digest(private)!=source.source_hash or result['rule_version']!=source.validation['rule_version'] or result['graph_hash']!=source.validation['graph_hash']:raise HTTPException(409,'执行依据已变化，请重新核对，不得继续执行')
    row.status='completed';row.result={'actor_id':actor.id,'note':note,'completed_at':utcnow().isoformat()}
    event(db,actor,'execution_completed',row.id)
    db.commit();return row

def clock(db,actor,key,action):
    gate(db,actor,'clock')
    row=db.scalar(select(Shift).where(Shift.id==key,Shift.account_id==actor.id).with_for_update().execution_options(populate_existing=True))
    if not row:raise HTTPException(404,'不存在或无权')
    from app.operations.state import localnow
    now=localnow()
    if action=='in':
        if row.checked_in:return row
        if now<row.start_at-timedelta(minutes=30) or now>row.end_at:raise HTTPException(409,'不在签到窗口内')
        row.checked_in=now
    else:
        if row.checked_out:return row
        if not row.checked_in or now<row.checked_in:raise HTTPException(409,'请先签到')
        if now>row.end_at+timedelta(hours=24):raise HTTPException(409,'签退已超时，请护理部核对异常')
        row.checked_out=now
    event(db,actor,'clock_'+action,row.id);db.commit();return row

def sign_medication(db,actor,key,version,note,validator):
    gate(db,actor,'review_draft')
    row=draft(db,actor,key,True)
    if row.kind!='medication' or row.owner_id!=actor.id:raise HTTPException(404,'不存在或无权')
    pending(row,version);lock_sources(db,row,actor);gate(db,actor,'review_draft')
    private,result=check(db,actor,row.kind,row.current,validator)
    if digest(private)!=row.source_hash or result['rule_version']!=row.validation['rule_version'] or result['graph_hash']!=row.validation['graph_hash']:raise HTTPException(409,'资料或规则变化，必须重新核对后签字')
    row.professional_signoff={'actor_id':actor.id,'version':row.version,'payload_hash':digest(row.current),'source_hash':row.source_hash,'rule_version':result['rule_version'],'graph_hash':result['graph_hash'],'signed_at':utcnow().isoformat(),'note':note}
    event(db,actor,'medical_draft_signed',row.id,version=row.version)
    db.commit();return row
