from pydantic import BaseModel, ConfigDict, Field


class Paragraph(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    text: str = Field(min_length=1, max_length=2500)
    sources: list[int] = Field(min_length=1, max_length=5)


class Draft(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    sufficient: bool
    paragraphs: list[Paragraph] = Field(max_length=8)
