from datetime import date
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from app.core.auth import require_account, require_admin
from app.core.deps import DatabaseSession
from app.models.auth import Account
from app.models.meals import WeeklyMenu
from app.schemas.meals import MenuInput,ProfileInput,PublishInput,SelectionInput,Meal
from app.services import meals
router=APIRouter(prefix='/meals',tags=['meals'])
Admin=Annotated[Account,Depends(require_admin)]
Principal=Annotated[Account,Depends(require_account)]
@router.get('/requirements')
def requirements(db:DatabaseSession,actor:Admin):return {'items':meals.requirements(db)}
@router.put('/profiles/{key}')
def profile(key:UUID,data:ProfileInput,db:DatabaseSession,actor:Admin):return meals.save_profile(db,str(key),data,actor)
@router.get('/menus')
def menus(week_start:date,db:DatabaseSession,actor:Admin):
    row=db.scalar(select(WeeklyMenu).where(WeeklyMenu.week_start==week_start))
    return {'menu':meals.menu_dict(row) if row else None}
@router.put('/menus')
def save(data:MenuInput,db:DatabaseSession,actor:Admin):return meals.save_menu(db,data,actor)
@router.get('/menus/{key}/coverage')
def coverage(key:UUID,db:DatabaseSession,actor:Admin):return meals.coverage(db,meals.get_menu(db,str(key)))
@router.post('/menus/{key}/publish')
def publish(key:UUID,data:PublishInput,db:DatabaseSession,actor:Admin):return meals.publish(db,str(key),data,actor)
@router.get('/menus/{key}/kitchen')
def kitchen(key:UUID,meal_date:date,meal:Meal,db:DatabaseSession,actor:Admin):return meals.kitchen(db,str(key),meal_date,meal)
@router.get('/mine')
def mine(week_start:date,db:DatabaseSession,actor:Principal):return meals.choices(db,actor,week_start)
@router.put('/mine')
def choose(data:SelectionInput,db:DatabaseSession,actor:Principal):return meals.select_meal(db,data,actor)


from app.schemas.meals import GenerateMenuInput
from app.services.chat.llm import QwenClient,get_menu_llm
from app.agents.menu_planner import generate
from pathlib import Path
from app.services.menu_diagnostics import get_menu_diagnostic_dir
@router.post('/generate')
def generate_menu(data:GenerateMenuInput,db:DatabaseSession,actor:Admin,llm:Annotated[QwenClient,Depends(get_menu_llm)],diagnostic_dir:Annotated[Path,Depends(get_menu_diagnostic_dir)]):
    return generate(db,data,actor,llm,diagnostic_dir)

from app.services.chat.llm import get_llm
from app.models.resident import Resident
from fastapi import HTTPException
from app.services.diet_profile_reader import extract

@router.post('/profiles/{key}/read')
def read_profile(key:UUID,db:DatabaseSession,actor:Admin,llm:Annotated[QwenClient,Depends(get_llm)]):
    resident=db.scalar(select(Resident).where(Resident.id==str(key)))
    if not resident or resident.status!='in_care':raise HTTPException(404,'在院老人档案不存在')
    version=resident.version
    records={k:getattr(resident,k) or '' for k in ['allergies','chronic_conditions','dietary_notes']}
    if not any(records.values()):raise HTTPException(422,'档案中暂无可读取的健康或饮食记录，请先补充资料')
    db.rollback()
    result=extract(records,llm)
    db.expire_all()
    fresh=db.scalar(select(Resident).where(Resident.id==str(key)))
    if not fresh or fresh.status!='in_care' or fresh.version!=version:raise HTTPException(409,'读取期间档案已变化，请刷新后重试')
    return {**result,'resident_version':version,'resident_id':str(key)}


from app.services.howtocook import configuration
@router.get('/recipe-source')
def recipe_source(actor:Admin):return configuration()
