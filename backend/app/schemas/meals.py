from datetime import date, time
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
Meal=Literal['breakfast','lunch','dinner']
Texture=Literal['normal','soft','minced','pureed']
class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    @field_validator('allergens','avoid_ingredients','required_tags','tags','ingredients','foods',mode='after',check_fields=False)
    @classmethod
    def clean_tokens(cls,values):
        if any(not v or len(v)>60 for v in values) or len(set(values))!=len(values):raise ValueError('条目不能为空、重复或超过60字')
        return values
class MealOption(Strict):
    id:UUID
    name:str=Field(min_length=1,max_length=80)
    foods:list[str]=Field(min_length=1,max_length=20)
    ingredients:list[str]=Field(min_length=1,max_length=60)
    allergens:list[str]=Field(default_factory=list,max_length=30)
    tags:list[str]=Field(default_factory=list,max_length=20)
    texture:Texture
    capacity:int=Field(ge=1,le=10000)
    notes:str=Field(default='',max_length=500)
class MenuSlot(Strict):
    day:int=Field(ge=0,le=6)
    meal:Meal
    cutoff:time
    options:list[MealOption]=Field(min_length=1,max_length=8)
class MenuInput(Strict):
    week_start:date
    slots:list[MenuSlot]=Field(min_length=21,max_length=21)
    version:int=Field(default=0,ge=0)
    @model_validator(mode='after')
    def valid_week(self):
        if self.week_start.weekday()!=0:raise ValueError('周菜单开始日期必须为周一')
        if {(s.day,s.meal) for s in self.slots}!={(d,m) for d in range(7) for m in ['breakfast','lunch','dinner']}:raise ValueError('必须完整安排7天三餐，餐次不得重复')
        ids=[o.id for s in self.slots for o in s.options]
        if len(ids)!=len(set(ids)):raise ValueError('餐食方案ID不得重复')
        if any(s.cutoff.tzinfo is not None for s in self.slots):raise ValueError('截止时间使用北京时间，不附时区')
        return self
class ProfileInput(Strict):
    version:int=Field(ge=0)
    resident_version:int=Field(ge=1)
    allergy_status:Literal['unknown','known','confirmed_none']
    confirmed:bool
    allergens:list[str]=Field(default_factory=list,max_length=30)
    avoid_ingredients:list[str]=Field(default_factory=list,max_length=60)
    required_tags:list[str]=Field(default_factory=list,max_length=20)
    allowed_textures:list[Texture]=Field(min_length=1,max_length=4)
    source:str=Field(min_length=1,max_length=300)
    notes:str=Field(default='',max_length=1000)
    @model_validator(mode='after')
    def allergy_consistency(self):
        if self.allergy_status=='known' and not self.allergens:raise ValueError('已知过敏时须列出过敏原')
        if self.allergy_status=='confirmed_none' and self.allergens:raise ValueError('已核对无过敏不能同时填写过敏原')
        return self
    @field_validator('allowed_textures')
    @classmethod
    def unique_textures(cls,v):
        if len(v)!=len(set(v)):raise ValueError('质地不得重复')
        return v
class PublishInput(Strict):
    version:int=Field(ge=1)
    acknowledge_pending:bool=False
class SelectionInput(Strict):
    menu_id:UUID
    day:int=Field(ge=0,le=6)
    meal:Meal
    option_id:UUID
    version:int=Field(default=0,ge=0)


class GenerateMenuInput(Strict):
    week_start:date
    version:int=Field(default=0,ge=0)
    options_per_meal:int=Field(default=2,ge=2,le=4)
    available_ingredients:list[str]=Field(default_factory=list,max_length=150)
    kitchen_notes:str=Field(default='',max_length=1000)
    budget_notes:str=Field(default='',max_length=300)
    season:str=Field(default='',max_length=30)
    capacity_per_option:int|None=Field(default=None,ge=1,le=10000)
    avoid_previous:bool=True
    acknowledge_pending:bool=False
    @field_validator('week_start')
    @classmethod
    def monday_only(cls,v):
        if v.weekday()!=0:raise ValueError('开始日期必须为周一')
        return v
    @field_validator('available_ingredients')
    @classmethod
    def inventory_tokens(cls,v):
        if any(not item or len(item)>60 for item in v) or len(v)!=len(set(v)):raise ValueError('食材不能重复、为空或超过60字')
        return v

class PlannedOption(Strict):
    name:str=Field(min_length=1,max_length=80)
    foods:list[str]=Field(min_length=1,max_length=20)
    ingredients:list[str]=Field(min_length=1,max_length=60)
    allergens:list[str]=Field(max_length=30)
    tags:list[str]=Field(max_length=20)
    texture:Texture
    notes:str=Field(default='',max_length=500)
class PlannedSlot(Strict):
    meal:Meal
    options:list[PlannedOption]=Field(min_length=2,max_length=4)
class PlannedDay(Strict):
    slots:list[PlannedSlot]=Field(min_length=3,max_length=3)
    @model_validator(mode='after')
    def three_meals(self):
        if {s.meal for s in self.slots}!={'breakfast','lunch','dinner'}:raise ValueError('一天必须有不重复的早餐、午餐、晚餐')
        return self
