"""Create caregiver accounts and assign unassigned in-care residents atomically.

Preview: python -m scripts.setup_caregivers
Apply:   python -m scripts.setup_caregivers --apply
"""
import argparse
import secrets
from uuid import uuid4
from sqlalchemy import select
from app.core.auth import hash_password
from app.db.session import SessionLocal
from app.models.auth import Account
from app.models.resident import Resident, ResidentAssignment, ResidentChange
from app.services.residents import snapshot

ACCOUNTS = [('13900009001', '陈静'), ('13900009002', '李芳'), ('13900009003', '王敏')]


def provision(db, apply=False):
    admin = db.scalar(select(Account).where(Account.role == 'admin').order_by(Account.id).with_for_update())
    if admin is None:
        raise ValueError('请先创建管理员账号')
    # Lock caregiver accounts before residents, matching assignment validation order.
    staff = list(db.scalars(select(Account).where(Account.role == 'user').order_by(Account.id).with_for_update()))
    new = []
    for phone, name in ACCOUNTS:
        existing = db.scalar(select(Account).where(Account.phone == phone).with_for_update())
        if existing:
            if existing.role != 'user' or existing.name != name:
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='实际创建账号并保存负责关系')
    args = parser.parse_args()
    try:
        with SessionLocal() as db:
            result = provision(db, args.apply)
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
    print('已有负责关系、账号密码和离院档案未更改；重复执行不会重复创建或重新分配。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
