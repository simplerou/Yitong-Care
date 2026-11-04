from datetime import date, datetime, timedelta, time
from uuid import uuid4
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, func
from app.models.auth import Account
from app.models.resident import Resident, ResidentAccountBinding
from app.models.meals import WeeklyMenu, MealProfile, MealSelection, MealChange
from app.schemas.meals import MenuInput
TZ=ZoneInfo('Asia/Shanghai')
def now():return datetime.now(TZ)
def audit(db,actor,kind,key,data):db.add(MealChange(id=str(uuid4()),actor_id=actor.id,kind=kind,entity_id=key,data=jsonable_encoder(data)))
def menu_dict(row):return {'id':row.id,'week_start':row.week_start,'status':row.status,'version':row.version,**row.data}
def profile_data(row):return {'version':row.version,'resident_version':row.resident_version,**row.data} if row else None
def reviewed(resident,profile):return bool(profile and profile.resident_version==resident.version and profile.data.get('confirmed') and profile.data.get('allergy_status')!='unknown')
def reasons(option,profile):
    data=profile.data
    result=[]
    # Exact controlled terms entered by the reviewer, never disease-name inference.
    hazards=set(data['allergens']) & (set(option['allergens'])|set(option['ingredients']))
    avoid=set(data['avoid_ingredients']) & set(option['ingredients'])
    if hazards:result.append('已登记过敏原：'+'、'.join(sorted(hazards)))
    if avoid:result.append('已登记禁用食材：'+'、'.join(sorted(avoid)))
    if option['texture'] not in data['allowed_textures']:result.append('不符合已核对的食物质地')
    if not set(data['required_tags'])<=set(option['tags']):result.append('缺少已确认的饮食要求标签')
    return result
def own_resident(db,actor,lock=False):
    if actor.role!='resident':raise HTTPException(403,'此功能仅供老人账号使用')
    statement=select(Resident).join(ResidentAccountBinding,Resident.id==ResidentAccountBinding.resident_id).where(ResidentAccountBinding.account_id==actor.id)
    if lock:statement=statement.with_for_update().execution_options(populate_existing=True)
    row=db.scalar(statement)
    if not row:raise HTTPException(409,'账号尚未绑定老人档案，请联系管理员')
    return row
def get_menu(db,key,lock=False):
    statement=select(WeeklyMenu).where(WeeklyMenu.id==key)
    if lock:statement=statement.with_for_update().execution_options(populate_existing=True)
    row=db.scalar(statement)
    if not row:raise HTTPException(404,'周菜单不存在')
    return row
def requirements(db):
    residents=db.scalars(select(Resident).where(Resident.status=='in_care').order_by(Resident.name,Resident.id)).all()
    profiles={p.resident_id:p for p in db.scalars(select(MealProfile))}
    return [{'id':r.id,'name':r.name,'record_no':r.record_no,'location':r.location,'resident_version':r.version,'allergies':r.allergies,'chronic_conditions':r.chronic_conditions,'dietary_notes':r.dietary_notes,'profile':profile_data(profiles.get(r.id)),'reviewed':reviewed(r,profiles.get(r.id))} for r in residents]
def save_profile(db,key,data,actor):
    resident=db.scalar(select(Resident).where(Resident.id==key).with_for_update())
    if not resident:raise HTTPException(404,'档案不存在')
    row=db.scalar(select(MealProfile).where(MealProfile.resident_id==key).with_for_update())
    if resident.version!=data.resident_version or (row.version if row else 0)!=data.version:raise HTTPException(409,'档案或饮食要求已变化，请刷新核对')
    before=profile_data(row)
    values=data.model_dump(exclude={'version','resident_version'})
    if row:row.version+=1;row.resident_version=resident.version;row.data=values
    else:row=MealProfile(resident_id=key,version=1,resident_version=resident.version,data=values);db.add(row)
    db.flush();audit(db,actor,'profile_review',key,{'before':before,'after':profile_data(row)});db.commit()
    return profile_data(row)
def save_menu(db,data,actor):
    row=db.scalar(select(WeeklyMenu).where(WeeklyMenu.week_start==data.week_start).with_for_update())
    if row and row.status!='draft':raise HTTPException(409,'已发布菜单不可修改，请复制到新一周')
    if (row.version if row else 0)!=data.version:raise HTTPException(409,'菜单版本已变化，请刷新')
    before=menu_dict(row) if row else None
    values={'slots':[slot.model_dump(mode='json') for slot in data.slots]}
    if row:row.version+=1;row.data=values
    else:row=WeeklyMenu(id=str(uuid4()),week_start=data.week_start,status='draft',version=1,data=values);db.add(row)
    db.flush();audit(db,actor,'menu_save',row.id,{'before':before,'after':menu_dict(row)});db.commit();return menu_dict(row)
def coverage(db,row):
    rs=db.scalars(select(Resident).where(Resident.status=='in_care')).all();profiles={p.resident_id:p for p in db.scalars(select(MealProfile))}
    pending=[];missing=[]
    for r in rs:
        p=profiles.get(r.id)
        if not reviewed(r,p):pending.append({'id':r.id,'name':r.name});continue
        for slot in row.data['slots']:
            if not any(not reasons(o,p) for o in slot['options']):missing.append({'resident_id':r.id,'name':r.name,'day':slot['day'],'meal':slot['meal']})
    return {'in_care':len(rs),'pending':pending,'missing':missing,'reviewed_count':len(rs)-len(pending)}
def publish(db,key,data,actor):
    row=get_menu(db,key,True)
    if row.version!=data.version or row.status!='draft':raise HTTPException(409,'菜单状态或版本变化，请刷新')
    report=coverage(db,row)
    if report['missing']:raise HTTPException(422,{'message':'部分已核实老人没有可选方案，请补充替代餐','coverage':report})
    if report['pending'] and not data.acknowledge_pending:raise HTTPException(422,{'message':'仍有待核实老人；明确确认后可发布，但这些老人不能自助确认选餐','coverage':report})
    row.status='published';row.version+=1;audit(db,actor,'menu_publish',key,report);db.commit();return menu_dict(row)
def deadline(row,slot):return datetime.combine(row.week_start+timedelta(days=slot['day']),time.fromisoformat(slot['cutoff']),TZ)
def choices(db,actor,week):
    resident=own_resident(db,actor);profile=db.get(MealProfile,resident.id)
    row=db.scalar(select(WeeklyMenu).where(WeeklyMenu.week_start==week,WeeklyMenu.status=='published'))
    if not row:return {'menu':None,'resident_name':resident.name,'reviewed':reviewed(resident,profile),'slots':[]}
    selected={(s.meal_date,s.meal):s for s in db.scalars(select(MealSelection).where(MealSelection.resident_id==resident.id,MealSelection.menu_id==row.id))}
    counts=dict(db.execute(select(MealSelection.option_id,func.count()).join(Resident,Resident.id==MealSelection.resident_id).where(MealSelection.menu_id==row.id,Resident.status=='in_care').group_by(MealSelection.option_id)).all())
    slots=[]
    for slot in row.data['slots']:
        meal_date=row.week_start+timedelta(days=slot['day']);pick=selected.get((meal_date,slot['meal']))
        options=[]
        for o in slot['options']:
            why=reasons(o,profile) if reviewed(resident,profile) else ['饮食要求尚未核实，请联系工作人员']
            used=counts.get(o['id'],0)
            options.append({**o,'reasons':why,'remaining':max(0,o['capacity']-used)})
        slots.append({**slot,'date':meal_date,'closed':now()>=deadline(row,slot),'options':options,'selection':{'option_id':pick.option_id,'version':pick.version,'needs_review':pick.profile_version!=(profile.version if profile else 0) or pick.resident_version!=resident.version} if pick else None})
    return {'menu':{'id':row.id,'week_start':row.week_start,'version':row.version},'resident_name':resident.name,'reviewed':reviewed(resident,profile),'in_care':resident.status=='in_care','slots':slots}
def select_meal(db,data,actor):
    row=get_menu(db,str(data.menu_id),True)
    if row.status!='published':raise HTTPException(409,'菜单尚未发布')
    resident=own_resident(db,actor,True)
    profile=db.scalar(select(MealProfile).where(MealProfile.resident_id==resident.id).with_for_update())
    if resident.status!='in_care':raise HTTPException(409,'已离院档案不能确认在院餐食')
    if not reviewed(resident,profile):raise HTTPException(409,'饮食资料尚未核实或档案已变化，请联系工作人员')
    slot=next((s for s in row.data['slots'] if s['day']==data.day and s['meal']==data.meal),None)
    if slot is None:raise HTTPException(422,'餐次不存在')
    if now()>=deadline(row,slot):raise HTTPException(409,'已过选餐截止时间，请联系工作人员')
    option=next((o for o in slot['options'] if o['id']==str(data.option_id)),None)
    if option is None:raise HTTPException(422,'餐食方案不属于该餐次')
    why=reasons(option,profile)
    if why:raise HTTPException(422,'；'.join(why))
    meal_date=row.week_start+timedelta(days=data.day)
    pick=db.scalar(select(MealSelection).where(MealSelection.resident_id==resident.id,MealSelection.meal_date==meal_date,MealSelection.meal==data.meal).with_for_update())
    if (pick.version if pick else 0)!=data.version:raise HTTPException(409,'选餐记录已变化，请刷新')
    used=db.scalar(select(func.count()).select_from(MealSelection).join(Resident,Resident.id==MealSelection.resident_id).where(MealSelection.menu_id==row.id,MealSelection.option_id==option['id'],MealSelection.resident_id!=resident.id,Resident.status=='in_care')) or 0
    if used>=option['capacity']:raise HTTPException(409,'该餐食份数已用完，请选择其他方案')
    if pick:
        pick.option_id=option['id'];pick.version+=1;pick.profile_version=profile.version;pick.resident_version=resident.version
    else:pick=MealSelection(id=str(uuid4()),resident_id=resident.id,menu_id=row.id,meal_date=meal_date,meal=data.meal,option_id=option['id'],version=1,profile_version=profile.version,resident_version=resident.version);db.add(pick)
    db.flush();audit(db,actor,'meal_select',pick.id,{'resident_id':resident.id,'menu_id':row.id,'date':meal_date,'meal':data.meal,'option_id':pick.option_id,'version':pick.version});db.commit()
    return {'option_id':pick.option_id,'version':pick.version}
def kitchen(db,key,meal_date,meal):
    row=get_menu(db,key);day=(meal_date-row.week_start).days
    slot=next((s for s in row.data['slots'] if s['day']==day and s['meal']==meal),None)
    if not slot:raise HTTPException(422,'日期或餐次不在菜单内')
    rs=db.scalars(select(Resident).where(Resident.status=='in_care').order_by(Resident.name)).all();ps={p.resident_id:p for p in db.scalars(select(MealProfile))}
    orders={s.resident_id:s for s in db.scalars(select(MealSelection).where(MealSelection.menu_id==key,MealSelection.meal_date==meal_date,MealSelection.meal==meal))}
    counts={o['id']:0 for o in slot['options']};pending=[];unselected=[]
    for r in rs:
        pick=orders.get(r.id);p=ps.get(r.id)
        info={'id':r.id,'name':r.name,'location':r.location}
        if not pick:unselected.append(info);continue
        option=next((o for o in slot['options'] if o['id']==pick.option_id),None)
        if not reviewed(r,p) or pick.profile_version!=p.version or pick.resident_version!=r.version or not option or reasons(option,p):pending.append(info)
        else:counts[pick.option_id]+=1
    return {'date':meal_date,'meal':meal,'options':[{'id':o['id'],'name':o['name'],'foods':o['foods'],'count':counts[o['id']],'capacity':o['capacity']} for o in slot['options']],'needs_review':pending,'unselected':unselected,'in_care':len(rs)}
