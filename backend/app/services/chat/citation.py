from typing import Literal
from app.schemas.policy import Gap
from pydantic import BaseModel, ConfigDict, Field


class Paragraph(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    text: str = Field(min_length=1, max_length=2500)
    sources: list[int] = Field(min_length=1, max_length=5)


class Draft(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    coverage: Literal['complete','partial'] = 'complete'
    missing_topics: list[Gap] = Field(default_factory=list, max_length=6)
    sufficient: bool
    paragraphs: list[Paragraph] = Field(max_length=8)
