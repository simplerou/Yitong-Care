from datetime import date,timedelta
from typing import Annotated,Literal
from uuid import uuid4
from fastapi import APIRouter,Depends,HTTPException,Query,Response,Request
from sqlalchemy import select,func,delete
from pydantic import Field
from app.core.auth import require_account,require_admin
from app.core.deps import DatabaseSession
from app.models.auth import Account,LoginSession
from app.models.resident import Resident,ResidentAssignment
from app.operations.models import Credential,ClinicalProfile,Draft,Correction,Shift,Event
from app.operations.contracts import RunInput,Decision,Revision,ProfileInput,StaffInput,Strict,current_date
from app.operations.security import identity,gate,event,resident,ROLES,TOOLS
from app.operations.validator import get_validator,ValidationClient
from app.operations.state import issue_constraints,utcnow,payroll
from app.operations import service,workflow
from app.services.chat.llm import QwenClient,get_llm
from app.api.v1.embeddings import Model,Manager

def schema_ready(db:DatabaseSession,response:Response):
    response.headers['Cache-Control']='no-store'
    from sqlalchemy.exc import ProgrammingError,OperationalError
    from app.operations.models import DrugReference
    try:
        for model in (Credential,Draft,DrugReference):db.execute(select(model.id if hasattr(model,'id') else model.account_id).limit(0))
    except (ProgrammingError,OperationalError):
        db.rollback();raise HTTPException(503,'六岗位业务数据层尚未就绪，请检查MySQL并先执行 alembic upgrade head') from None

router=APIRouter(prefix='/operations',tags=['collaborative-operations'],dependencies=[Depends(schema_ready)])
Actor=Annotated[Account,Depends(require_account)]
Admin=Annotated[Account,Depends(require_admin)]
Validator=Annotated[ValidationClient,Depends(get_validator)]

@router.get('/identity')
def card(db:DatabaseSession,actor:Actor):
    value=identity(db,actor)
    return {'account_id':value.account_id,'name':value.name,'role':value.role,'role_name':ROLES[value.role],'qualified':value.qualified,'tools':value.tools,'tasks':[task for task,role in workflow.TASK_TO_ROLE.items() if role==value.role and workflow.TASK_TOOL[task] in value.tools],'roles':ROLES}

@router.get('/staff')
def staff(db:DatabaseSession,actor:Actor):
    card=identity(db,actor)
    if card.role not in ('admin','nursing'):raise HTTPException(404,'不存在或无权')
    if card.role=='nursing':gate(db,actor,'staff_roster')
    result=[]
    staff_query=select(Account).where(Account.role.in_(ROLES),Account.status=='active')
    if card.role=='nursing':staff_query=staff_query.where(Account.role=='user')
    for row in db.scalars(staff_query.order_by(Account.name)):
        credential=db.get(Credential,row.id)
        result.append({'id':row.id,'name':row.name,'phone_hint':row.phone[:3]+'****'+row.phone[-4:],'role':row.role,'qualification':credential.qualification if credential else '', 'valid_until':credential.valid_until if credential else None})
    return {'items':result}

@router.put('/staff')
def set_staff(data:StaffInput,db:DatabaseSession,actor:Admin):
    # Lock all admin records to serialize last-admin protection.
    admins=list(db.scalars(select(Account).where(Account.role=='admin',Account.status=='active').order_by(Account.id).with_for_update()))
    row=db.scalar(select(Account).where(Account.id==data.account_id).with_for_update())
    if not row:raise HTTPException(404,'不存在或无权')
    if row.status!='active':raise HTTPException(409,'未开通账号请先在注册审核中处理')
    if row.role=='admin' and data.role!='admin' and len(admins)<=1:raise HTTPException(409,'必须保留至少一位院长管理员')
    if data.role in ('medical','nursing') and (not data.qualification or not data.valid_until or data.valid_until<current_date()):raise HTTPException(422,'专业岗位必须登记有效资质及有效期')
    before=row.role;row.role=data.role
    existing=db.get(Credential,row.id)
    if existing:db.delete(existing);db.flush()
    if data.qualification and data.valid_until:db.add(Credential(account_id=row.id,qualification=data.qualification,valid_until=data.valid_until))
    db.execute(delete(LoginSession).where(LoginSession.account_id==row.id))
    event(db,actor,'role_changed',row.id,before=before,after=data.role)
    db.commit();return {'id':row.id,'role':row.role,'login_required':True}

@router.get('/residents')
def records(db:DatabaseSession,actor:Actor):
    card=identity(db,actor)
    if card.role not in ('medical','nursing','user'):raise HTTPException(404,'不存在或无权')
    if card.role=='medical':gate(db,actor,'read_record')
    if card.role=='nursing':gate(db,actor,'care_review')
    query=select(Resident).where(Resident.status=='in_care')
    if card.role=='user':query=query.where(Resident.id.in_(select(ResidentAssignment.resident_id).where(ResidentAssignment.account_id==actor.id)))
    return {'items':[{'id':r.id,'name':r.name,'location':r.location,'version':r.version} for r in db.scalars(query.order_by(Resident.name))]}

@router.get('/profiles/{key}')
def read_profile(key:str,db:DatabaseSession,actor:Actor):
    gate(db,actor,'read_record');r=resident(db,actor,key)
    row=db.get(ClinicalProfile,key)
    return {'resident_version':r.version,'version':row.version if row else 0,'profile':row.data if row else None,'record_excerpt':{'allergies':r.allergies,'chronic_conditions':r.chronic_conditions,'dietary_notes':r.dietary_notes}}

@router.put('/profiles/{key}')
def save_profile(key:str,data:ProfileInput,db:DatabaseSession,actor:Actor,validator:Validator):
    gate(db,actor,'read_record');r=resident(db,actor,key,True)
    row=db.get(ClinicalProfile,key)
    if data.resident_version!=r.version or data.version!=(row.version if row else 0):raise HTTPException(409,'资料版本已变化，请刷新')
    payload=data.model_dump(mode='json',exclude={'version','resident_version'})
    result=validator.check({'kind':'medication','patients':[payload],'medicines':[],'foods':[]})
    if any(item['code']!='medicines_required' for item in result['issues']):raise HTTPException(409,{'message':'现有用药存在待核对事项','validation':result})
    from app.services.residents import snapshot
    from app.models.resident import ResidentChange
    before=snapshot(db,r);clinical_before=row.data if row else None
    r.version+=1
    if row:row.data=payload;row.version+=1;row.resident_version=r.version
    else:row=ClinicalProfile(resident_id=key,version=1,resident_version=r.version,data=payload);db.add(row)
    db.add(ResidentChange(id=str(uuid4()),resident_id=key,actor_id=actor.id,actor_name=actor.name,reason='医务室核实结构化医护资料',before=before,after=snapshot(db,r)))
    event(db,actor,'clinical_profile_reviewed',key,version=row.version,before=clinical_before,after=payload)
    db.commit();return {'version':row.version,'resident_version':r.version,'profile':row.data}

@router.post('/constraints')
def constraints(db:DatabaseSession,actor:Actor,validator:Validator):
    gate(db,actor,'constraints');row=issue_constraints(db,validator);event(db,actor,'constraints_issued',row.id);db.commit()
    return {'constraint_token':row.id,'expires_at':row.expires_at,**row.public_data}

@router.get('/catalog')
def catalog(db:DatabaseSession,actor:Actor,validator:Validator):
    card=identity(db,actor)
    if card.role=='medical':gate(db,actor,'drug_evidence')
    elif card.role=='kitchen':gate(db,actor,'food_catalog')
    elif card.role=='user':gate(db,actor,'validate_swap')
    else:raise HTTPException(404,'不存在或无权')
    data=validator.catalog()
    if card.role!='medical':
        data.pop('drugs',None);data.pop('diseases',None);data.pop('allergens',None)
    if card.role=='medical':data.pop('foods',None)
    return data

@router.get('/drug-evidence/{drug_id}')
def evidence(drug_id:str,db:DatabaseSession,actor:Actor,validator:Validator):
    gate(db,actor,'drug_evidence');return validator.evidence(drug_id)

@router.get('/recipes')
def recipes(db:DatabaseSession,actor:Actor):
    gate(db,actor,'recipe_search')
    from app.services.howtocook import candidates
    return candidates(seed=actor.id)

@router.post('/run',status_code=201)
def run(data:RunInput,db:DatabaseSession,actor:Actor,validator:Validator,llm:Annotated[QwenClient,Depends(get_llm)],embedder:Model,manager:Manager):
    row=workflow.run(db,actor,data,validator,llm,embedder,manager);return service.serialize(db,actor,row)

@router.get('/drafts')
def drafts(db:DatabaseSession,actor:Actor):
    card=identity(db,actor)
    query=select(Draft).order_by(Draft.created_at.desc())
    if card.role!='admin':query=query.where((Draft.owner_id==actor.id)|(Draft.kind.in_([kind for kind,role in service.APPROVERS.items() if role==card.role])))
    return {'items':[service.serialize(db,actor,row) for row in db.scalars(query.limit(100)) if service.permitted(db,actor,row)]}

@router.get('/drafts/{key}')
def get_draft(key:str,db:DatabaseSession,actor:Actor):return service.serialize(db,actor,service.draft(db,actor,key))
@router.put('/drafts/{key}')
def revise(key:str,data:Revision,db:DatabaseSession,actor:Actor,validator:Validator):return service.serialize(db,actor,service.revision(db,actor,key,data,validator))
@router.post('/drafts/{key}/decision')
def decide(key:str,data:Decision,db:DatabaseSession,actor:Actor,validator:Validator):return service.serialize(db,actor,service.decision(db,actor,key,data,validator))

@router.get('/executions')
def executions(db:DatabaseSession,actor:Actor):
    role=identity(db,actor).role
    items=[]
    for row in service.executions(db,actor):
        target=db.get(Resident,row.resident_id) if row.resident_id and role!='kitchen' else None
        items.append({'id':row.id,'draft_id':row.draft_id,'status':row.status,'data':row.data,'result':row.result,'resident_name':target.name if target else None,'created_at':row.created_at})
    return {'items':items}
class Completion(Strict):
    note:str=Field(min_length=1,max_length=1000)
@router.post('/executions/{key}/complete')
def complete(key:str,data:Completion,db:DatabaseSession,actor:Actor,validator:Validator):return service.complete(db,actor,key,data.note,validator)

@router.get('/shifts')
def shifts(db:DatabaseSession,actor:Actor,request:Request):
    card=identity(db,actor)
    if card.role=='admin' and not getattr(request.app.state,'legacy_compatibility',False):raise HTTPException(404,'不存在或无权')
    if card.role not in ('admin','nursing','finance','user'):raise HTTPException(404,'不存在或无权')
    if card.role=='nursing':gate(db,actor,'staff_roster')
    query=select(Shift).order_by(Shift.start_at.desc())
    if card.role=='user':query=query.where(Shift.account_id==actor.id)
    return {'items':list(db.scalars(query.limit(200)))}
class ClockInput(Strict):action:Literal['in','out']
@router.post('/shifts/{key}/clock')
def clock(key:str,data:ClockInput,db:DatabaseSession,actor:Actor):return service.clock(db,actor,key,data.action)
@router.get('/payroll')
def payroll_report(month:str,db:DatabaseSession,actor:Actor):
    gate(db,actor,'calculate_payroll')
    from app.operations.contracts import PayrollInput
    from pydantic import ValidationError
    try:data=PayrollInput(month=month)
    except ValidationError:raise HTTPException(422,'核薪月份格式不正确') from None
    return payroll(db,data.month)

@router.get('/corrections')
def corrections(db:DatabaseSession,actor:Actor):
    card=identity(db,actor)
    if card.role not in ('admin','nursing'):raise HTTPException(404,'不存在或无权')
    query=select(Correction).order_by(Correction.created_at.desc())
    if card.role=='nursing':
        gate(db,actor,'care_review');query=query.join(Draft).where(Draft.kind.in_(['schedule','incident']))
    rows=list(db.scalars(query.limit(200)))
    if card.role=='admin':return {'items':[{'id':r.id,'draft_id':r.draft_id,'route':r.route,'tag':r.tag,'reason':'专业修正，详情限原专业岗位','before':{},'after':{},'closed':r.closed,'created_at':r.created_at} for r in rows]}
    return {'items':rows}
class CloseInput(Strict):note:str=Field(min_length=1,max_length=1000)
@router.post('/corrections/{key}/close')
def close_correction(key:str,data:CloseInput,db:DatabaseSession,actor:Admin):
    row=db.get(Correction,key)
    if not row:raise HTTPException(404,'不存在或无权')
    row.closed=True;event(db,actor,'correction_closed',key,note=data.note);db.commit();return {'closed':True}

@router.get('/dashboard')
def dashboard(db:DatabaseSession,actor:Actor):
    gate(db,actor,'view_validation')
    rows=list(db.scalars(select(Draft)))
    approved=[r for r in rows if r.status=='approved']
    adopted=sum(r.current==r.proposed for r in approved)
    now=utcnow();events=list(db.scalars(select(Event).where(Event.created_at>=now-timedelta(days=30))))
    stats={}
    for period,days in [('week',7),('month',30)]:
        recent=[r for r in approved if r.created_at>=now-timedelta(days=days)]
        stats[period]={'approved':len(recent),'unchanged':sum(r.proposed==r.current for r in recent)}
    tool_ok=sum(e.action=='tool_succeeded' for e in events);tool_bad=sum(e.action=='tool_failed' for e in events)
    return {'tool_success_rate':round(tool_ok/(tool_ok+tool_bad),4) if tool_ok+tool_bad else None,'tool_successes':tool_ok,'tool_failures':tool_bad,'drafts':len(rows),'pending':sum(r.status=='pending' and r.expires_at>now for r in rows),'approved':len(approved),'unchanged_adoption':round(adopted/len(approved),4) if approved else None,'closed_corrections':db.scalar(select(func.count()).select_from(Correction).where(Correction.closed.is_(True))),'open_corrections':db.scalar(select(func.count()).select_from(Correction).where(Correction.closed.is_(False))),'periods':stats,'gateway_denials':sum(e.action.endswith('denied') for e in events),'validation_blocks':sum(e.action=='validation_blocked' for e in events),'notice':'采纳率仅按已批准草稿统计；无样本时未知。没有把演示数据当作生产效果指标。'}

@router.get('/audit')
def audit(db:DatabaseSession,actor:Admin):
    rows=db.scalars(select(Event).order_by(Event.created_at.desc()).limit(200)).all()
    return {'items':[{'id':r.id,'action':r.action,'created_at':r.created_at,'object_id':'' if r.action in ('clinical_profile_reviewed','clinical_orders_applied') else r.object_id,'data':{'redacted':True} if r.action in ('clinical_profile_reviewed','clinical_orders_applied') else r.data} for r in rows]}

class ReferenceInput(Strict):
    drug_id:str=Field(min_length=1,max_length=80)
    category:Literal['insert']='insert'
    chunk_id:int=Field(gt=0,le=9223372036854775807)
    section:str=Field(min_length=1,max_length=100)
    valid_from:date
    valid_until:date|None=None

@router.post('/drug-references')
def bind_reference(data:ReferenceInput,db:DatabaseSession,actor:Admin):
    from app.models import DocumentChunk,KnowledgeDocument
    from app.operations.models import DrugReference
    from app.operations.state import digest
    chunk=db.get(DocumentChunk,data.chunk_id)
    doc=db.get(KnowledgeDocument,chunk.doc_id) if chunk else None
    if not chunk or not doc or doc.kb_id!='medication':raise HTTPException(404,'不存在或无权')
    if not doc.content or doc.content[chunk.start_offset:chunk.start_offset+chunk.chars]!=chunk.content:raise HTTPException(409,'原文与切块不一致，请重新解析')
    if data.valid_until and data.valid_until<data.valid_from:raise HTTPException(422,'有效期范围错误')
    row=DrugReference(id=str(uuid4()),**data.model_dump(),source_hash=digest({'doc':doc.id,'content':doc.content,'chunk':chunk.content,'start':chunk.start_offset}))
    db.add(row);event(db,actor,'drug_reference_bound',row.id,drug_id=data.drug_id);db.commit();return {'id':row.id}

from app.api.v1.embeddings import Model,Manager
@router.get('/drug-retrieval/{drug_id}')
def retrieve_drug(drug_id:str,query:Annotated[str,Query(min_length=1,max_length=1000)],db:DatabaseSession,actor:Actor,embedder:Model,manager:Manager,category:Literal['insert']='insert',on_date:date|None=None,hybrid:bool=True):
    gate(db,actor,'drug_evidence')
    from app.operations.evidence import retrieve
    rows=retrieve(db,drug_id,query,category,on_date,embedder if hybrid else None,manager if hybrid else None)
    return {'hits':rows,'drug_id':drug_id,'category':category,'on_date':on_date or current_date(),'strategy':'embedding_bm25_rrf' if hybrid else 'bm25'}

class SignatureInput(Strict):
    version:int=Field(ge=1)
    note:str=Field(min_length=1,max_length=1000)
@router.post('/drafts/{key}/sign')
def sign_medication(key:str,data:SignatureInput,db:DatabaseSession,actor:Actor,validator:Validator):
    return service.serialize(db,actor,service.sign_medication(db,actor,key,data.version,data.note,validator))

class MedicalAssistantInput(Strict):
    resident_id:str=Field(min_length=1,max_length=36)
    text:str=Field(min_length=1,max_length=2000)
class KitchenAssistantInput(Strict):
    text:str=Field(min_length=1,max_length=2000)

def assistant(db,actor,kind,text,validator,llm,embedder,manager,resident_id=None):
    from app.operations.react import run_react
    from app.operations.budget import start,reset,remaining
    token=start()
    try:
        role=identity(db,actor).role
        if role!=('medical' if kind=='medication' else 'kitchen'):raise HTTPException(404,'不存在或无权')
        from app.operations.supervisor import dispatch
        payload,summary,trace=dispatch(db,actor,{role:lambda:run_react(db,actor,kind,text,validator,llm,resident_id=resident_id)})
        remaining()
        if payload is None:
            from fastapi.responses import JSONResponse
            db.commit();return JSONResponse(status_code=200,content={'response_type':'answer','answer':summary,'trace':trace,'draft_created':False})
        row=workflow.run(db,actor,RunInput(task=kind,payload=payload,use_model=False),validator,llm,embedder,manager)
        row.trace=[{'node':'identity_supervisor','agent':role}]+trace+[{'node':'react_summary','summary':summary}]+row.trace
        event(db,actor,'react_draft_prepared',row.id,role=role,tool_calls=len(trace))
        db.commit();return service.serialize(db,actor,row)
    finally:reset(token)

@router.post('/assistant/medical',status_code=201)
def medical_assistant(data:MedicalAssistantInput,db:DatabaseSession,actor:Actor,validator:Validator,llm:Annotated[QwenClient,Depends(get_llm)],embedder:Model,manager:Manager):
    return assistant(db,actor,'medication',data.text,validator,llm,embedder,manager,data.resident_id)
@router.post('/assistant/kitchen',status_code=201)
def kitchen_assistant(data:KitchenAssistantInput,db:DatabaseSession,actor:Actor,validator:Validator,llm:Annotated[QwenClient,Depends(get_llm)],embedder:Model,manager:Manager):
    return assistant(db,actor,'menu',data.text,validator,llm,embedder,manager)

@router.get('/medical-inbox')
def medical_inbox(db:DatabaseSession,actor:Actor):
    gate(db,actor,'receive_incident')
    from app.operations.models import MedicalInbox
    rows=db.scalars(select(MedicalInbox).order_by(MedicalInbox.created_at.desc()).limit(200)).all()
    return {'items':[{'id':row.id,'draft_id':row.draft_id,'resident_id':row.resident_id,'resident_name':db.get(Resident,row.resident_id).name,'severity':row.severity,'observation':row.observation,'status':row.status,'handling_note':row.handling_note,'created_at':row.created_at} for row in rows]}
@router.post('/medical-inbox/{key}/ack')
def acknowledge_incident(key:str,data:Completion,db:DatabaseSession,actor:Actor):
    gate(db,actor,'receive_incident')
    from app.operations.models import MedicalInbox
    row=db.scalar(select(MedicalInbox).where(MedicalInbox.id==key).with_for_update())
    if not row:raise HTTPException(404,'不存在或无权')
    row.status='handled';row.handled_by=actor.id;row.handling_note=data.note
    source=db.get(Draft,row.draft_id)
    # Clinical acknowledgement is distinct from the nursing care-review decision.
    event(db,actor,'medical_incident_acknowledged',row.id);db.commit();return {'status':row.status}

@router.get('/drafts/{key}/cost')
def draft_cost(key:str,db:DatabaseSession,actor:Actor):
    gate(db,actor,'view_cost')
    row=service.draft(db,actor,key)
    result=service.serialize(db,actor,row)
    return {'draft_id':row.id,'cost':result['validation'].get('cost',{}),'calculation':result['calculation']}
