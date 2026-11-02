from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

class ResidentInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    name: str = Field(min_length=1, max_length=50)
    gender: Literal['unknown','male','female'] = 'unknown'
    birth_date: date | None = None
    admission_date: date | None = None
    status: Literal['in_care','discharged'] = 'in_care'
    location: str = Field(default='', max_length=100)
    care_level: Literal['未评估','自理','部分协助','全面协助','专人照护'] = '未评估'
    contact_name: str = Field(default='', max_length=50)
    contact_relation: str = Field(default='', max_length=30)
    contact_phone: str = Field(default='', max_length=32, pattern=r'^[0-9+()\-\s]*$')
    allergies: str = Field(default='', max_length=2000)
    chronic_conditions: str = Field(default='', max_length=2000)
    dietary_notes: str = Field(default='', max_length=2000)
    mobility_notes: str = Field(default='', max_length=2000)
    communication_notes: str = Field(default='', max_length=2000)
    care_notes: str = Field(default='', max_length=4000)
    source: str = Field(min_length=1, max_length=200)
    assigned_account_ids: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def dates(self):
        if self.birth_date and self.birth_date > date.today():
            raise ValueError('出生日期不能晚于今天')
        if self.admission_date and self.admission_date > date.today():
            raise ValueError('实际入住日期不能晚于今天')
        if self.birth_date and self.admission_date and self.admission_date < self.birth_date:
            raise ValueError('入住日期不能早于出生日期')
        if len(set(self.assigned_account_ids)) != len(self.assigned_account_ids):
            raise ValueError('负责人员不能重复')
        return self

class ResidentUpdate(ResidentInput):
    version: int = Field(ge=1)
    change_reason: str = Field(min_length=1, max_length=300)
