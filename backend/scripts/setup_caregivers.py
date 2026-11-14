"""Create caregiver accounts and assign unassigned in-care residents atomically.

Preview: python -m scripts.setup_caregivers
Apply:   python -m scripts.setup_caregivers --apply
"""
import argparse
import secrets
from uuid import uuid4,uuid5
from sqlalchemy import select,delete
from app.core.auth import hash_password,verify_password
from app.db.session import SessionLocal
from app.models.auth import Account,LoginSession
from app.models.resident import Resident, ResidentAssignment, ResidentChange
from app.services.residents import snapshot

ACCOUNTS = [('13900009001', '陈静'), ('13900009002', '李芳'), ('13900009003', '王敏')]


def provision(db, apply=False):
    admin = db.scalar(select(Account).where(Account.role == 'admin').order_by(Account.id).with_for_update())
    if admin is None:
        raise ValueError('请先创建管理员账号')
    # Lock caregiver accounts before residents, matching assignment validation order.
    staff = list(db.scalars(select(Account).where(Account.role == 'user',Account.status=='active').order_by(Account.id).with_for_update()))
    new = []
    for phone, name in ACCOUNTS:
        existing = db.scalar(select(Account).where(Account.phone == phone).with_for_update())
        if existing:
            if existing.role != 'user' or existing.name != name or existing.status!='active':
                raise ValueError(f'预设手机号 {phone} 已被其他账号占用，未修改任何数据')
            continue
        password = 'Care9' + secrets.token_hex(6)
        row = Account(id=str(uuid4()), phone=phone, name=name, role='user', password_hash=hash_password(password))
        db.add(row)
        staff.append(row)
        new.append({'phone':phone, 'name':name, 'password':password})
    db.flush()
    residents = list(db.scalars(select(Resident).where(Resident.status == 'in_care').order_by(Resident.location, Resident.record_no).with_for_update()))
    assignments = list(db.scalars(select(ResidentAssignment)))
    active_ids = {row.id for row in residents}
    assigned = {row.resident_id for row in assignments}
    loads = {row.id:0 for row in staff}
    for row in assignments:
        if row.resident_id in active_ids and row.account_id in loads:
            loads[row.account_id] += 1
    added = 0
    for row in residents:
        if row.id in assigned:
            continue
        caregiver = min(staff, key=lambda person:(loads[person.id], person.phone))
        before = snapshot(db, row)
        db.add(ResidentAssignment(resident_id=row.id, account_id=caregiver.id))
        row.version += 1
        db.flush()
        db.add(ResidentChange(id=str(uuid4()), resident_id=row.id, actor_id=admin.id,
            actor_name=admin.name, reason='初始化护工负责关系：均衡分配未分配的在院老人',
            before=before, after=snapshot(db, row)))
        loads[caregiver.id] += 1
        added += 1
    result = {'created':new, 'assigned':added, 'counts':[
        {'name':row.name, 'phone':row.phone, 'count':loads[row.id]} for row in sorted(staff,key=lambda person:person.phone)]}
    if apply:
        db.commit()
    else:
        db.rollback()
    return result


FIVE_ACCOUNTS=ACCOUNTS+[('13900009004','张丽'),('13900009005','刘芳')]
FIVE_INITIAL_PASSWORD='hg123456'


def provision_five_by_four(db,apply=False,admin_phone=None):
    """Use only the original 20 fictional residents; exact and repeatable assignment."""
    from scripts.seed_residents import NAMESPACE,SOURCE,LEGACY_SOURCE
    from app.core.auth import now
    from app.operations.security import event
    try:
        admins=list(db.scalars(select(Account).where(Account.role=='admin',Account.status=='active').order_by(Account.id).with_for_update()))
        if admin_phone:admins=[person for person in admins if person.phone==admin_phone]
        if len(admins)!=1:raise ValueError('请先创建唯一有效院长；多位院长时用 --admin-phone 指定操作人')
        actor=admins[0]
        existing={row.phone:row for row in db.scalars(select(Account).where(Account.phone.in_([phone for phone,_ in FIVE_ACCOUNTS])).order_by(Account.id).with_for_update())}
        for phone,name in FIVE_ACCOUNTS:
            person=existing.get(phone)
            if person and (person.name!=name or person.role!='user' or person.status!='active'):
                raise ValueError(f'预设手机号 {phone} 已被其他姓名、岗位或未开通账号占用，未修改账号')
        numbers=[f'DEMO202611-{i:03d}' for i in range(1,21)]
        keys=[str(uuid5(NAMESPACE,number)) for number in numbers]
        residents=list(db.scalars(select(Resident).where(Resident.id.in_(keys)).order_by(Resident.record_no).with_for_update()))
        if len(residents)!=20 or any(row.record_no!=number or row.source not in (SOURCE,LEGACY_SOURCE) or row.status!='in_care' for row,number in zip(residents,numbers)):
            raise ValueError('需要原样例001至020共20位在院老人；请先执行 python -m scripts.seed_residents --resize-to-20')
        excess=[str(uuid5(NAMESPACE,f'DEMO202611-{i:03d}')) for i in range(21,101)]
        if db.scalar(select(Resident.id).where(Resident.id.in_(excess)).limit(1)):
            raise ValueError('旧100人样例尚未缩减，请先执行 python -m scripts.seed_residents --resize-to-20')
        existing_ids=[person.id for person in existing.values()]
        if db.scalar(select(ResidentAssignment.resident_id).where(ResidentAssignment.account_id.in_(existing_ids),ResidentAssignment.resident_id.not_in(keys)).limit(1)):
            raise ValueError('预设护工还负责本批次以外的老人，未修改原分配，请先由护理部核对')
        staff=[];created=[]
        for phone,name in FIVE_ACCOUNTS:
            person=existing.get(phone)
            if person is None:
                password=FIVE_INITIAL_PASSWORD
                person=Account(id=str(uuid4()),phone=phone,name=name,role='user',status='active',requested_role='user',reviewed_at=now(),review_note='本地初始化：五名护工各负责四位虚构老人',application_version=2,password_hash=hash_password(password))
                db.add(person)
                event(db,actor,'account_application_approve',person.id,applicant_name=name,phone_hint=phone[:3]+'****'+phone[-4:],reviewer_name=actor.name,application_version=1,requested_role='user',granted_role='user',status='active',note=person.review_note)
                created.append({'phone':phone,'name':name,'password':password})
            staff.append(person)
        db.flush()
        changed=0;counts=[]
        for index,person in enumerate(staff):
            group=residents[index*4:(index+1)*4]
            for row in group:
                old=set(db.scalars(select(ResidentAssignment.account_id).where(ResidentAssignment.resident_id==row.id)))
                if old=={person.id}:continue
                before=snapshot(db,row)
                db.execute(delete(ResidentAssignment).where(ResidentAssignment.resident_id==row.id))
                db.add(ResidentAssignment(resident_id=row.id,account_id=person.id))
                row.version+=1;db.flush()
                db.add(ResidentChange(id=str(uuid4()),resident_id=row.id,actor_id=actor.id,actor_name=actor.name,reason='本地初始化：五名护工各负责四位虚构老人',before=before,after=snapshot(db,row)))
                changed+=1
            counts.append({'name':person.name,'phone':person.phone,'count':len(group),'records':[row.record_no for row in group]})
        result={'created':created,'assigned':changed,'counts':counts}
        if apply:db.commit()
        else:db.rollback()
        return result
    except Exception:
        db.rollback();raise


def reset_five_passwords(db,apply=False,admin_phone=None):
    """Explicit password reset for these five accounts, with no assignment writes."""
    from app.operations.security import event
    try:
        admins=list(db.scalars(select(Account).where(Account.role=='admin',Account.status=='active').order_by(Account.id).with_for_update()))
        if admin_phone:admins=[actor for actor in admins if actor.phone==admin_phone]
        if len(admins)!=1:raise ValueError('请先创建唯一有效院长；多位院长时用 --admin-phone 指定操作人')
        people={person.phone:person for person in db.scalars(select(Account).where(Account.phone.in_([phone for phone,_ in FIVE_ACCOUNTS])).order_by(Account.id).with_for_update())}
        for phone,name in FIVE_ACCOUNTS:
            person=people.get(phone)
            if person is None:raise ValueError('五名护工尚未全部创建，请先执行 --five-by-four --apply')
            if person.name!=name or person.role!='user' or person.status!='active':raise ValueError('预设账号身份或状态不符，未重置任何密码')
        changed=0
        for phone,_ in FIVE_ACCOUNTS:
            person=people[phone]
            if verify_password(FIVE_INITIAL_PASSWORD,person.password_hash):continue
            person.password_hash=hash_password(FIVE_INITIAL_PASSWORD)
            db.execute(delete(LoginSession).where(LoginSession.account_id==person.id))
            event(db,admins[0],'account_password_reset',person.id,reason='本地统一五名护工登录密码')
            changed+=1
        if apply:db.commit()
        else:db.rollback()
        return changed
    except Exception:
        db.rollback();raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='实际创建账号并保存负责关系')
    parser.add_argument('--five-by-four',action='store_true',help='将20位原样例老人分给5个指定护工，每人4位；替换该批次原分配并留痕')
    parser.add_argument('--admin-phone',help='五人模式下指定已有院长作为本地初始化操作人')
    parser.add_argument('--reset-five-passwords',action='store_true',help='仅将五个指定护工账号密码统一为 hg123456，不修改老人分配')
    args = parser.parse_args()
    if args.five_by_four and args.reset_five_passwords:parser.error('两个模式请分别执行')
    try:
        with SessionLocal() as db:
            if args.reset_five_passwords:
                changed=reset_five_passwords(db,args.apply,args.admin_phone)
                print(f'五个指定护工密码已统一为 hg123456，更新 {changed} 个；原会话失效，请重新登录。' if args.apply else f'仅预览：将更新 {changed} 个护工密码；添加 --apply 才保存。')
                return 0
            result = provision_five_by_four(db,args.apply,args.admin_phone) if args.five_by_four else provision(db,args.apply)
    except ValueError as exc:
        print(str(exc)); return 1
    except Exception:
        print('操作失败，未提交本次修改。请确认本地 MySQL 已启动、backend/.env 连接配置正确且迁移已完成。')
        return 1
    print('已保存。' if args.apply else '仅预览，未写入。添加 --apply 后执行保存。')
    print(f"新增护工 {len(result['created'])} 位；分配未分配在院老人 {result['assigned']} 位。")
    if args.apply:
        for row in result['created']:
            print(f"新账号：{row['name']} | {row['phone']} | 初始密码：{row['password']}")
    for row in result['counts']:
        print(f"{row['name']} | {row['phone']} | 负责在院老人：{row['count']} 位")
    if args.five_by_four:print('20位样例按编号每4位分给一个护工；已有账号密码及其他老人未改动。重复执行不重复创建或重分配。')
    else:print('已有负责关系、账号密码和离院档案未更改；重复执行不会重复创建或重新分配。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
