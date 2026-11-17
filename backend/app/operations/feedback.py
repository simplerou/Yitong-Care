"""Role-scoped human correction evidence and closure; never changes graph rules."""
from fastapi import HTTPException
from sqlalchemy import select
from app.operations.models import Correction,Event
from app.operations.security import identity,gate,event,TASK_TOOL
from app.operations import service


def records(db,actor,key):
    draft=service.draft(db,actor,key)
    owner=actor.id==draft.owner_id
    rows=list(db.scalars(select(Correction).where(Correction.draft_id==key).order_by(Correction.created_at,Correction.id)))
    closures={}
    if rows:
        for entry in db.scalars(select(Event).where(Event.action=='feedback_resolved',Event.object_id.in_([row.id for row in rows])).order_by(Event.created_at,Event.id)):
            closures[entry.object_id]=entry
    checks={entry.data.get('correction_id'):entry.data for entry in db.scalars(select(Event).where(Event.action=='draft_revised',Event.object_id==key))}
    items=[]
    for row in rows:
        closed=closures.get(row.id)
        check=checks.get(row.id)
        from app.operations.workflow import public_validation
        role=identity(db,actor).role
        snapshot={'previous_version':check.get('previous_version'),'version':check.get('version'),'before':public_validation(check.get('previous_validation',{}),role),'after':public_validation(check.get('validation',{}),role)} if check else None
        items.append({'id':row.id,'route':row.route,'tag':row.tag,'closed':row.closed,'created_at':row.created_at,
                      'reason':row.reason if owner else '专业岗位修正，正文仅原提交岗位可见',
                      'before':row.before if owner else {},'after':row.after if owner else {},
                      'validation_snapshot':snapshot,'resolution_note':closed.data.get('note','') if closed and owner else '',
                      'resolved_at':closed.created_at if closed else None,
                      'can_resolve':owner and row.actor_id==actor.id and not row.closed})
    return {'items':items,'evidence':{'modified':draft.proposed!=draft.current,'status':draft.status,'version':draft.version,'decision_note':draft.decision_note if owner else ''}}


def resolve(db,actor,key,note):
    row=db.scalar(select(Correction).where(Correction.id==key).with_for_update().execution_options(populate_existing=True))
    if row is None:raise HTTPException(404,'不存在或无权')
    draft=service.draft(db,actor,row.draft_id)
    if draft.owner_id!=actor.id or row.actor_id!=actor.id:raise HTTPException(404,'不存在或无权')
    gate(db,actor,TASK_TOOL[draft.kind])
    if not row.closed:
        row.closed=True
        event(db,actor,'feedback_resolved',row.id,route=row.route,tag=row.tag,note=note,draft_id=draft.id)
        db.commit()
    return records(db,actor,draft.id)
