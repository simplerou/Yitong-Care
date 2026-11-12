"""Strict contracts shared with the independently deployed validation service."""
from datetime import date,datetime
from zoneinfo import ZoneInfo
def current_date():return datetime.now(ZoneInfo('Asia/Shanghai')).date()
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator
class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True,allow_inf_nan=False)
class Dose(Strict):
    drug_id:str=Field(min_length=1,max_length=80)
    mg_per_dose:Decimal=Field(gt=0,le=100000)
    times_daily:int=Field(ge=1,le=24)
class Food(Strict):
    food_id:str=Field(min_length=1,max_length=80)
    grams:Decimal=Field(gt=0,le=10000)
class Patient(Strict):
    allergens:list[str]=Field(max_length=50)
    diseases:list[str]=Field(max_length=50)
    medicines:list[Dose]=Field(max_length=30)
    energy_min:Decimal=Field(gt=0,le=10000)
    energy_max:Decimal=Field(gt=0,le=10000)
    protein_min:Decimal=Field(ge=0,le=500)
    sodium_max:Decimal=Field(gt=0,le=10000)
    source:str=Field(min_length=1,max_length=500)
    @model_validator(mode='after')
    def bounds(self):
        if self.energy_min>self.energy_max:raise ValueError('能量上下限不正确')
        return self
    @model_validator(mode='after')
    def unique_medicines(self):
        if len({m.drug_id for m in self.medicines})!=len(self.medicines):raise ValueError('药品不得重复')
        return self
class CheckRequest(Strict):
    kind:Literal['medication','menu','meal_swap']
    patients:list[Patient]=Field(min_length=1,max_length=500)
    medicines:list[Dose]=Field(default_factory=list,max_length=30)
    foods:list[Food]=Field(default_factory=list,max_length=30)
    @model_validator(mode='after')
    def unique_items(self):
        if len({m.drug_id for m in self.medicines})!=len(self.medicines):raise ValueError('药品不得重复')
        if len({f.food_id for f in self.foods})!=len(self.foods):raise ValueError('食物请合并为每日总量')
        return self
class MedicationInput(Strict):
    resident_id:str=Field(min_length=1,max_length=36)
    medicines:list[Dose]=Field(min_length=1,max_length=30)
    rationale:str=Field(min_length=1,max_length=1000)
class MenuInput(Strict):
    service_date:date=Field(default_factory=current_date)
    constraint_token:str=Field(min_length=1,max_length=36)
    foods:list[Food]=Field(min_length=1,max_length=30)
    title:str=Field(min_length=1,max_length=100)
class SwapInput(Strict):
    service_date:date=Field(default_factory=current_date)
    resident_id:str=Field(min_length=1,max_length=36)
    foods:list[Food]=Field(min_length=1,max_length=30)
    reason:str=Field(min_length=1,max_length=500)
class ShiftInput(Strict):
    account_id:str=Field(min_length=1,max_length=36)
    start_at:datetime
    end_at:datetime
    hourly_rate:Decimal=Field(gt=0,le=10000)
    @model_validator(mode='after')
    def valid(self):
        if self.start_at.tzinfo is not None or self.end_at.tzinfo is not None:raise ValueError('排班时间使用本地无时区时间（北京时间）')
        if not 0<(self.end_at-self.start_at).total_seconds()<=12*3600:raise ValueError('单班须在0至12小时内')
        return self
class ScheduleInput(Strict):
    shifts:list[ShiftInput]=Field(min_length=1,max_length=100)
class PayrollInput(Strict):
    month:str=Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')
    @model_validator(mode='after')
    def valid_year(self):
        if not 1<=int(self.month[:4])<=9998:raise ValueError('核薪年份超出有效范围')
        return self
class IncidentInput(Strict):
    resident_id:str=Field(min_length=1,max_length=36)
    severity:Literal['routine','urgent']
    observation:str=Field(min_length=1,max_length=2000)
class RunInput(Strict):
    task:Literal['medication','menu','schedule','payroll','meal_swap','incident']
    payload:dict
    instruction:str=Field(default='',max_length=1000)
    use_model:bool=False
class Decision(Strict):
    version:int=Field(ge=1)
    action:Literal['approve','reject']
    note:str=Field(default='',max_length=1000)
class Revision(Strict):
    version:int=Field(ge=1)
    payload:dict
    route:Literal['rule','agent','training']
    tag:Literal['evidence','dose','nutrition','scope','format','workflow','other']
    reason:str=Field(min_length=1,max_length=1000)
class ProfileInput(Patient):
    version:int=Field(default=0,ge=0)
    resident_version:int=Field(ge=1)
class StaffInput(Strict):
    account_id:str=Field(min_length=1,max_length=36)
    role:Literal['admin','medical','kitchen','nursing','finance','user']
    qualification:str=Field(default='',max_length=80)
    valid_until:date|None=None

from pydantic import StrictBool,StrictInt
class ValidationResult(Strict):
    passed:StrictBool
    rule_version:str=Field(min_length=1,max_length=100)
    graph_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    demo:StrictBool
    issues:list[dict]=Field(max_length=10000)
    paths:list[dict]=Field(max_length=10000)
    references:list[dict]=Field(default_factory=list,max_length=10000)
    nutrition_references:list[dict]=Field(default_factory=list,max_length=1000)
    calculations:list[dict]=Field(default_factory=list,max_length=20000)
    nutrients:dict[str,str]=Field(default_factory=dict)
    risk:StrictInt=Field(ge=1,le=3)
