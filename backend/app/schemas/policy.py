"""Manually curated policy facts; unknown is never treated as currently valid."""
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PolicyMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid')
    issuer: str = Field(default='', max_length=200)
    document_number: str = Field(default='', max_length=100)
    regions: list[str] = Field(default_factory=list, max_length=30)
    category: str = Field(default='', max_length=100)
    audience: str = Field(default='', max_length=1000)
    published_on: date | None = None
    effective_on: date | None = None
    expires_on: date | None = None
    validity: Literal['unknown', 'effective', 'repealed', 'expired'] = 'unknown'
    verification_source: str = Field(default='', max_length=1000)
    verified_on: date | None = None
    # Document numbers rather than foreign keys: preserve external policy relationships.
    amends: list[str] = Field(default_factory=list, max_length=30)
    replaces: list[str] = Field(default_factory=list, max_length=30)
    notes: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def check_dates(self):
        if any(not value.strip() or len(value)>100 for value in self.regions+self.amends+self.replaces):
            raise ValueError('地区和关联文号需为1至100字符')
        if self.effective_on and self.expires_on and self.expires_on < self.effective_on:
            raise ValueError('失效日期不能早于施行日期')
        if self.validity != 'unknown' and (not self.verification_source.strip() or not self.verified_on):
            raise ValueError('标注政策效力必须提供核验来源和核验日期')
        if self.verified_on and self.verified_on > date.today():
            raise ValueError('核验日期不能在未来')
        return self


class ConsultationContext(BaseModel):
    model_config = ConfigDict(extra='forbid')
    region: str = Field(default='', max_length=100)
    age: int | None = Field(default=None, ge=0, le=130)
    household: str = Field(default='', max_length=100)
    benefit: str = Field(default='', max_length=100)


class DialogueState(BaseModel):
    """Server-derived user context, independent of the retired manual conditions form."""
    region: str = Field(default='', max_length=100)
    district: str = Field(default='', max_length=100)
    household: str = Field(default='', max_length=150)
    age: int | None = Field(default=None, ge=0, le=130)
    benefit: str = Field(default='', max_length=100)
    aspect: str = Field(default='', max_length=100)


Gap = Literal['local_service_catalog','payment_rates','eligibility','application_process','current_validity','full_policy_scope']
