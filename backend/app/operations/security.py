from dataclasses import dataclass
from datetime import date
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.models.auth import Account
from app.models.resident import Resident,ResidentAssignment
from app.operations.models import Credential,Event
from app.operations.contracts import current_date

ROLES={'admin':'院长','medical':'医务室','kitchen':'食堂','nursing':'护理部','finance':'财务部','user':'护工'}
TOOLS={
 'admin':('view_validation','view_cost','approve'),
 'medical':('read_record','drug_evidence','validate_medication','medication_draft','review_draft','receive_incident'),
 'kitchen':('constraints','food_catalog','recipe_search','nutrition_check','menu_draft','review_draft','approve_swap'),
 'nursing':('staff_roster','schedule_check','schedule_draft','care_review','execution_list','constraints'),
 'finance':('read_hours','calculate_payroll','payroll_draft','explain_payroll'),
 'user':('execution_list','record','report_incident','validate_swap','swap_draft'),
}
TASK_TO_ROLE={'medication':'medical','menu':'kitchen','schedule':'nursing','payroll':'finance','meal_swap':'user','incident':'user'}
TASK_TOOL={'medication':'medication_draft','menu':'menu_draft','schedule':'schedule_draft','payroll':'payroll_draft','meal_swap':'swap_draft','incident':'report_incident'}

@dataclass(frozen=True)
class Identity:
    account_id:str
    role:str
    name:str
    tools:tuple[str,...]
    qualified:bool

def event(db,actor,action,object_id='',**data):
    row=Event(id=str(uuid4()),actor_id=actor.id,action=action,object_id=str(object_id)[:64],data=data)
    db.add(row)

def identity(db,actor):
    # Never trust the caller's role snapshot, including at tool/approval boundaries.
    current=db.scalar(select(Account).where(Account.id==actor.id).execution_options(populate_existing=True))
    if not current or current.status!='active' or current.role not in ROLES:raise HTTPException(403,'不存在或无权')
    credential=db.get(Credential,current.id,populate_existing=True)
    qualified=bool(credential and credential.qualification and credential.valid_until>=current_date())
    return Identity(current.id,current.role,current.name,TOOLS[current.role],qualified)

def gate(db,actor,tool):
    if actor is None:raise HTTPException(404,'不存在或无权')
    card=identity(db,actor)
    allowed_tool={'complete_task':'record','clock':'record'}.get(tool,tool) if card.role=='user' else ('approve_swap' if card.role=='kitchen' and tool=='confirm_preparation' else tool)
    if allowed_tool not in card.tools or (card.role in ('medical','nursing') and not card.qualified):
        event(db,actor,'gateway_denied',tool,reason='qualification' if tool in card.tools else 'tool_not_allowed',role=card.role)
        db.commit()
        raise HTTPException(404,'不存在或无权')
    return card

def resident(db,actor,key,lock=False):
    card=identity(db,actor)
    condition=Resident.id==key
    statement=select(Resident).where(condition)
    if card.role=='user':statement=statement.where(Resident.id.in_(select(ResidentAssignment.resident_id).where(ResidentAssignment.account_id==card.account_id)))
    elif card.role not in ('medical','nursing','admin') or (card.role!='admin' and not card.qualified):
        statement=statement.where(False)
    if lock:statement=statement.with_for_update()
    row=db.scalar(statement.execution_options(populate_existing=True))
    if not row:
        exists=db.get(Resident,key) is not None
        event(db,actor,'scope_denied',key,reason='out_of_scope' if exists else 'missing')
        db.commit();raise HTTPException(404,'不存在或无权')
    return row

def read_tool(db,actor,tool,work):
    """Audited read-only invocation. Never wrap business writes or retry them here."""
    from time import perf_counter
    gate(db,actor,tool);started=perf_counter()
    try:result=work()
    except HTTPException as exc:
        event(db,actor,'tool_failed',tool,status=exc.status_code,elapsed_ms=round((perf_counter()-started)*1000))
        db.commit();raise
    event(db,actor,'tool_succeeded',tool,elapsed_ms=round((perf_counter()-started)*1000))
    return result
