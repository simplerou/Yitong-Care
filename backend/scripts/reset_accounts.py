"""Clear all login accounts while preserving resident/knowledge/business records.

Preview: python -m scripts.reset_accounts
Apply:   python -m scripts.reset_accounts --apply
"""
import argparse,secrets
from uuid import uuid4
from sqlalchemy import select,delete,update,func
from app import models
from app.db.base import Base
from app.db.session import SessionLocal
from app.models.auth import Account,LoginSession
from app.models.resident import Resident,ResidentAssignment,ResidentAccountBinding,ResidentChange
from app.operations.models import Credential,Draft,Execution,Event,Correction
from app.models.meals import MealChange
from app.core.auth import hash_password
from scripts.setup_admin import MODELS


def reset(db,apply=False):
    accounts=list(db.scalars(select(Account).where(Account.status!='archived').order_by(Account.id).with_for_update()))
    ids=[a.id for a in accounts]
    if not ids:return {'accounts':0,'deleted':0,'anonymous':0,'sessions':0,'assignments':0,'bindings':0,'cancelled_drafts':0,'cancelled_executions':0}
    def count(model,*where):return db.scalar(select(func.count()).select_from(model).where(*where)) or 0
    result={'accounts':len(ids),'deleted':0,'anonymous':0,'sessions':count(LoginSession,LoginSession.account_id.in_(ids)),'assignments':count(ResidentAssignment,ResidentAssignment.account_id.in_(ids)),'bindings':count(ResidentAccountBinding,ResidentAccountBinding.account_id.in_(ids)),'cancelled_drafts':0,'cancelled_executions':0}
    resident_ids=set(db.scalars(select(ResidentAssignment.resident_id).where(ResidentAssignment.account_id.in_(ids))))|set(db.scalars(select(ResidentAccountBinding.resident_id).where(ResidentAccountBinding.account_id.in_(ids))))
    for model in [LoginSession,ResidentAssignment,ResidentAccountBinding,Credential]:db.execute(delete(model).where(model.account_id.in_(ids)))
    if resident_ids:db.execute(update(Resident).where(Resident.id.in_(resident_ids)).values(version=Resident.version+1))
    # Explicitly retain old conversations as unclaimed history, not another user's data.
    for model in MODELS:db.execute(update(model).where(model.owner_id.in_(ids)).values(owner_id=None))
    db.execute(update(ResidentChange).where(ResidentChange.actor_id.in_(ids)).values(actor_name='历史操作人（账号已清理）'))
    # Remove registration/authorization records containing account application details.
    db.execute(delete(Event).where(Event.actor_id.in_(ids),(Event.action.like('account_%')|(Event.action=='role_changed'))))
    result['cancelled_drafts']=db.execute(update(Draft).where(Draft.owner_id.in_(ids),Draft.status=='pending').values(status='rejected',decision_by=None,decision_note='账号重置：原操作账号已清理，草稿作废',version=Draft.version+1)).rowcount
    db.execute(update(Execution).where(Execution.assignee_id.in_(ids)).values(assignee_id=None))
    result['cancelled_executions']=db.execute(update(Execution).where(Execution.status=='pending',Execution.draft_id.in_(select(Draft.id).where(Draft.owner_id.in_(ids)))).values(status='cancelled',result={'reason':'原账号已清理，请由新岗位人员重新核实后生成'})).rowcount
    def scrub(value):
        if isinstance(value,list):return [scrub(item) for item in value]
        if not isinstance(value,dict):return value
        result={key:scrub(item) for key,item in value.items()}
        if any(value.get(key) in ids for key in ('id','account_id','actor_id','owner_id','assignee_id') if isinstance(value.get(key),str)):
            for key in ('name','actor_name','owner_name','assignee_name'):
                if key in result:result[key]='历史匿名操作人'
            for key in ('phone','phone_hint'):
                if key in result:result[key]='已清理'
        return result
    # Remove explicit account identity fields in historical bindings/payroll snapshots;
    # never replace arbitrary text or elderly names by string matching.
    for model,fields in [(ResidentChange,['before','after']),(MealChange,['data']),(Draft,['proposed','current','private_context','validation','trace']),(Correction,['before','after']),(Event,['data']),(Execution,['data','result'])]:
        for row in db.scalars(select(model)):
            for field in fields:
                old=getattr(row,field);new=scrub(old)
                if new!=old:setattr(row,field,new)
    db.flush()
    # Detect remaining references rather than turning off foreign-key constraints.
    referenced=set()
    for table in Base.metadata.sorted_tables:
        if table.name=='account':continue
        for fk in table.foreign_keys:
            if fk.column.table.name=='account':
                referenced.update(db.scalars(select(fk.parent).where(fk.parent.in_(ids))))
    used_phones=set(db.scalars(select(Account.phone)))
    for account in accounts:
        if account.id not in referenced:
            db.delete(account);result['deleted']+=1
        else:
            phone='x'+uuid4().hex[:10]
            while phone in used_phones:phone='x'+uuid4().hex[:10]
            used_phones.add(phone)
            account.phone=phone # Not a phone number; rejected by the login input contract.
            account.name='历史匿名操作人'
            account.password_hash=hash_password(secrets.token_urlsafe(48))
            account.role='archive';account.status='archived';account.requested_role=None
            account.application_note='';account.review_note='';account.reviewed_at=None;account.application_version=1
            result['anonymous']+=1
    db.flush()
    if apply:db.commit()
    else:db.rollback()
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true',help='实际清空全部可登录账号；不保留任何现有院长');args=parser.parse_args()
    try:
        with SessionLocal() as db:
            result=reset(db,args.apply)
    except Exception as exc:
        print('清理未完成，本次事务已回滚。错误类型：'+type(exc).__name__)
        print('请检查MySQL连接，并在backend目录先执行 alembic upgrade head。')
        return 1
    print('账号清理已提交。' if args.apply else '仅预览，未写入。添加 --apply 才执行。')
    print(result)
    print('老人档案、知识库、向量及历史业务资料保留。历史引用仅保留匿名不可登录记录。')
    if args.apply:print('请运行 python -m scripts.setup_admin --name 院长 创建新的院长账号；勿使用 --claim-legacy，除非明确要接收历史会话。')
    return 0
if __name__=='__main__':raise SystemExit(main())
