"""100 fictional resident samples; atomic import, stable IDs and no real phone numbers."""
import argparse
from datetime import date, timedelta
import json
from pathlib import Path
from uuid import UUID, uuid5, uuid4
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from app.db.session import SessionLocal
from app.models.auth import Account
from app.models.resident import Resident, ResidentChange
from app.schemas.resident import ResidentInput
from app.services.residents import snapshot

SEED='yitong-demo-residents-20261102-v1'
NAMESPACE=UUID('24f0a752-e783-41b5-825e-1d635d0d805f')
SOURCE='虚构测试资料｜100人演示批次20261102-v1｜非真实入住或医疗记录'
DATA=Path(__file__).resolve().parents[1]/'fixtures/residents_demo_100.json'

def generate():
    surnames=list('赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦许何')
    male_names=['建国','德明','志远','文博','文清']
    female_names=['秀英','淑珍','秀兰','玉华','文静']
    profiles=[
        ('自理','','','可自主进食，饮食喜好待进一步核对。','独立步行，活动情况待核对。'),
        ('部分协助','高血压病史（虚构设定）','','饮食安排与禁忌待工作人员核对。','使用手杖，关注通道安全。'),
        ('部分协助','糖尿病病史（虚构设定）','青霉素过敏史（虚构设定，待核实）','用餐安排待核对，不作为治疗食谱。','长距离活动使用助行器，起身需协助。'),
        ('全面协助','脑卒中既往史（虚构设定）','','进食需协助，质地与吞咽情况待专业核对。','使用轮椅，移位需协助。'),
        ('专人照护','认知功能变化观察（虚构，不代表诊断）','','进食需陪同观察，具体安排待评估。','活动需陪同，关注环境安全。'),
        ('未评估','','','',''),
    ]
    rows=[]
    for i in range(1,101):
        level,chronic,allergy,diet,mobility=profiles[(i-1)%6]
        rows.append({'sample_no':i,'record_no':f'DEMO202611-{i:03d}','data':{
            'name':f'{surnames[(i-1)%20]}{(male_names if i%2 else female_names)[(i-1)//20]}','gender':'male' if i%2 else 'female',
            'birth_date':date(2026-60-(i-1)%40,(i-1)%10+1,(i-1)%28+1).isoformat(),
            'admission_date':(date(2026,10,25)-timedelta(days=i*13%650)).isoformat(),
            'status':'in_care' if i<=90 else 'discharged',
            'location':f'{"ABCD"[(i-1)//25]}楼 / {(i-1)//30+1}层 / {(i-1)//30+1}{(i-1)%30//2+1:02d}室 / {(i-1)%2+1:02d}床' if i<=90 else '',
            'care_level':level,'contact_name':f'演示家属{i:03d}（虚构）',
            'contact_relation':['女儿','儿子','配偶','其他亲属'][(i-1)%4],'contact_phone':'',
            'allergies':allergy,'chronic_conditions':chronic,'dietary_notes':diet,'mobility_notes':mobility,
            'communication_notes':['普通话沟通，偏好放慢语速。','听力待核实，沟通时确认理解。','偏好安静环境，情绪观察待记录。',''][(i-1)%4],
            'care_notes':f'【纯虚构测试档案 {i:03d}/100】用于列表、筛选、分页、权限与变更记录测试；不得作为实际照护、诊断或医嘱依据。',
            'source':SOURCE,'assigned_account_ids':[]}})
    return {'seed':SEED,'as_of':'2026-11-02','description':'全部为虚构测试资料，不包含真实联系电话。','residents':rows}

def read_dataset():
    body=json.loads(DATA.read_text(encoding='utf-8'))
    if body.get('seed')!=SEED or len(body.get('residents',[]))!=100:raise ValueError('数据集标识或数量错误')
    rows=[]
    for i,item in enumerate(body['residents'],1):
        if item['sample_no']!=i or item['record_no']!=f'DEMO202611-{i:03d}':raise ValueError('序号错误')
        data=ResidentInput.model_validate(item['data'])
        if data.name.startswith('测试·') or data.source!=SOURCE or data.contact_phone or data.assigned_account_ids:raise ValueError('须标明虚构、联系电话留空且不自动授权工作人员')
        rows.append((item['record_no'],data))
    return rows

def import_dataset(db,rows,admin_phone=None,refresh_labels=False):
    admins=list(db.scalars(select(Account).where(Account.role=='admin').order_by(Account.id)))
    if admin_phone:admins=[row for row in admins if row.phone==admin_phone]
    if len(admins)!=1:raise ValueError('未找到唯一管理员；多个管理员时请用 --admin-phone 指定导入操作人')
    actor=admins[0];pending=[];skipped=0;updates=[]
    for number,data in rows:
        key=str(uuid5(NAMESPACE,number))
        existing=db.scalar(select(Resident).where((Resident.id==key)|(Resident.record_no==number)).with_for_update())
        if existing:
            if existing.id!=key or existing.record_no!=number:raise ValueError('测试编号与现有档案冲突，未覆盖档案')
            changes={}
            if refresh_labels:
                if existing.name.startswith('测试·'): changes['name']=existing.name.removeprefix('测试·')
                i=int(number.rsplit('-',1)[1])
                old_location=f'演示楼 / {(i-1)//30+1}层 / {(i-1)//30+1}{(i-1)%30//2+1:02d}室 / {(i-1)%2+1:02d}床' if i<=90 else ''
                if existing.location==old_location and existing.location!=data.location: changes['location']=data.location
            if changes: updates.append((existing,changes))
            else: skipped+=1
        else:pending.append((key,number,data))
    try:
        for row,changes in updates:
            before=snapshot(db,row)
            for field,value in changes.items():setattr(row,field,value)
            row.version+=1;db.flush()
            db.add(ResidentChange(id=str(uuid4()),resident_id=row.id,actor_id=actor.id,actor_name=actor.name,reason='调整演示档案姓名与楼栋显示',before=before,after=snapshot(db,row)))
        for key,number,data in pending:
            row=Resident(id=key,record_no=number,version=1,**data.model_dump(exclude={'assigned_account_ids'}))
            db.add(row);db.flush()
            db.add(ResidentChange(id=str(uuid5(NAMESPACE,number+':created')),resident_id=key,actor_id=actor.id,actor_name=actor.name,reason='批量导入虚构测试档案（100人演示批次）',before=None,after=snapshot(db,row)))
        db.commit()
    except Exception:
        db.rollback();raise
    return {'created':len(pending),'skipped':skipped,'updated':len(updates),'batch_total':len(rows)}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--admin-phone',help='选择已有管理员作为操作人，不创建或提升账号')
    parser.add_argument('--refresh-labels',action='store_true',help='更新本批次旧姓名前缀及原始演示楼位置，不覆盖人工修改的位置或照护资料')
    parser.add_argument('--validate-only',action='store_true',help='只校验数据，不连接数据库')
    args=parser.parse_args()
    try:
        rows=read_dataset()
        if args.validate_only:
            print('校验通过：100份虚构档案，90位在院、10位离院，联系电话全部留空。');return 0
        with SessionLocal() as db:result=import_dataset(db,rows,args.admin_phone,args.refresh_labels)
        print(f"导入完成：新增 {result['created']} 份，显示调整 {result['updated']} 份，已存在跳过 {result['skipped']} 份；未自动分配工作人员。")
        return 0
    except ValueError as error:
        print(str(error));return 1
    except SQLAlchemyError:
        print('导入未完成：无法访问数据库或档案表未迁移。请检查 MySQL 并执行 alembic upgrade head；未报告为导入成功。');return 1
if __name__=='__main__':raise SystemExit(main())
