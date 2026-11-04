"""Local administrator provisioning; never available through public registration."""
import argparse
from getpass import getpass
import re
from uuid import uuid4
from sqlalchemy import select, update
from app.db.session import SessionLocal
from app.models.auth import Account
from app.core.auth import hash_password
from app.models.conversation import PolicyConversation
from app.models.health_conversation import HealthConversation
from app.models.medication_conversation import MedicationConversation
from app.models.diet_conversation import DietConversation
from app.models.safety_conversation import SafetyConversation
from app.models.mind_conversation import MindConversation
MODELS = [PolicyConversation,HealthConversation,MedicationConversation,DietConversation,SafetyConversation,MindConversation]

def provision(db, phone, name, password=None, claim_legacy=False):
    account = db.scalar(select(Account).where(Account.phone==phone))
    if account is None:
        if password is None:
            raise ValueError('新管理员必须设置密码')
        account = Account(id=str(uuid4()),phone=phone,name=name,password_hash=hash_password(password),role='admin')
        db.add(account)
        db.flush()
    else:
        if account.role == 'resident':
            raise ValueError('老人账号不能直接提升为管理员，请使用独立管理账号')
        account.role = 'admin'
    counts = {}
    if claim_legacy:
        for model in MODELS:
            result=db.execute(update(model).where(model.owner_id.is_(None)).values(owner_id=account.id))
            counts[model.__tablename__]=result.rowcount
    db.commit()
    return counts

def main():
    parser=argparse.ArgumentParser(description='创建/提升管理员，将历史无归属测试会话归入该账号')
    parser.add_argument('--phone',help='管理员手机号；省略时交互输入')
    parser.add_argument('--name',default='管理员')
    parser.add_argument('--claim-legacy',action='store_true',help='接收所有尚无归属的历史会话，不改动已属于其他账号的会话')
    args=parser.parse_args()
    phone=args.phone or input('管理员手机号：').strip()
    if not re.fullmatch(r'1[3-9]\d{9}',phone):
        raise SystemExit('手机号格式不正确')
    with SessionLocal() as db:
        exists=db.scalar(select(Account).where(Account.phone==phone))
        password=None
        if exists is None:
            password=getpass('设置管理员密码（至少8位，包含字母和数字）：')
            if len(password)>128 or len(password)<8 or not re.search('[A-Za-z]',password) or not re.search(r'\d',password):
                raise SystemExit('密码格式不符合要求')
            if password != getpass('再次输入密码：'):
                raise SystemExit('两次密码不一致')
        counts=provision(db,phone,args.name,password,args.claim_legacy)
    print('管理员设置完成。现有账号密码保持不变。')
    print('历史会话归档数量：',counts)
    print('知识文档、向量、检索记录保持原位，仅管理员可管理；普通用户通过智能体使用知识。')
if __name__=='__main__':
    main()
