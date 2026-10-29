from typing import Literal
from pydantic import BaseModel, Field, field_validator
from app.schemas.retrieval import SearchHit


class ChatTurn(BaseModel):
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=6000)


class PolicyQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=6)

    @field_validator('question')
    @classmethod
    def nonblank(cls, value):
        if not value.strip(): raise ValueError('请输入问题')
        return value.strip()


class WebSource(BaseModel):
    original_content_chars: int | None = None
    excerpt_start: int | None = None
    is_truncated: bool | None = None
    coverage: Literal['excerpt','extracted_text'] = 'excerpt'
    completeness_verified: Literal[False] = False
    title: str
    url: str
    content: str
    published_date: str | None = None
    retrieved_at: str


class WebPageDiagnostic(BaseModel):
    title: str
    url: str
    outcome: Literal['accepted', 'rejected']
    reason: str


class WebDiagnostics(BaseModel):
    stage: str = 'not_started'
    search_count: int = 0
    official_count: int = 0
    extraction_requested: int = 0
    extraction_returned: int = 0
    body_count: int = 0
    accepted_count: int = 0
    rejected_counts: dict[str, int] = Field(default_factory=dict)
    pages: list[WebPageDiagnostic] = Field(default_factory=list)


class Citation(BaseModel):
    index: int
    source_type: Literal['local', 'web'] = 'local'
    hit: SearchHit | None = None
    web: WebSource | None = None


class AnswerChecks(BaseModel):
    review_attempts: int = 0
    status: Literal['passed','partial','blocked','error']
    checked_paragraphs: int = 0
    accepted_paragraphs: int = 0
    issues: list[str] = Field(default_factory=list)


class PolicyAnswer(BaseModel):
    answer_checks: AnswerChecks | None = None
    policy_categories: list[str] = Field(default_factory=list)
    status: Literal['answered', 'clarification', 'insufficient']
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    retrieved_hits: list[SearchHit] = Field(default_factory=list)
    web_sources: list[WebSource] = Field(default_factory=list)
    web_status: Literal['not_used', 'not_configured', 'success', 'no_results', 'error'] = 'not_used'
    web_warning: str | None = None
    web_diagnostics: WebDiagnostics | None = None
    vector_count: int = 0
    reason: str | None = None
    retrieval_log_id: str | None = None
    model: str
    knowledge_scope: list[str]
    steps: list[str]
