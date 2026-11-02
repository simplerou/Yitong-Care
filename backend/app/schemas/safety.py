"""Safety guardian contracts. Hazards, risk factors and post-fall triage are deterministic."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.chat import AnswerChecks, ChatTurn, Citation, ExecutionMetrics, WebDiagnostics, WebSource
from app.schemas.retrieval import SearchHit

Intent = Literal['fall_event', 'fall_prevention', 'environment', 'gait_aid', 'exercise', 'risk_assessment',
                 'education', 'rehab_prescription', 'construction_quote', 'restraint', 'other']
Severity = Literal['high', 'moderate', 'note']
Gap = Literal['fall_history', 'living_situation', 'mobility', 'medication_list', 'home_layout',
              'injury_detail', 'environment_evidence', 'full_safety_scope']


class SafetyProfile(BaseModel):
    """Minimal profile: age, living situation, conditions, mobility, drugs. No identity fields."""
    model_config = ConfigDict(extra='forbid')
    age: int | None = Field(default=None, ge=0, le=130)
    living_alone: bool = False
    previous_falls: int | None = Field(default=None, ge=0, le=100)
    mobility: Literal['independent', 'cane', 'walker', 'wheelchair', 'bedbound'] = 'independent'
    vision: Literal['normal', 'impaired'] = 'normal'
    cognition: Literal['normal', 'impaired'] = 'normal'
    conditions: list[Literal['osteoporosis', 'parkinson', 'stroke_history', 'arthritis', 'diabetes',
                             'hypertension', 'heart_disease', 'cognitive_impairment', 'vertigo']] = Field(default_factory=list, max_length=9)
    medications: list[str] = Field(default_factory=list, max_length=10)


class SafetyQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=6)
    profile: SafetyProfile = Field(default_factory=SafetyProfile)
    dialogue_state: 'SafetyDialogueState | None' = None

    @model_validator(mode='after')
    def nonblank(self):
        if not self.question.strip(): raise ValueError('请输入问题')
        self.question = self.question.strip()
        return self


class HazardFinding(BaseModel):
    id: str
    room: str
    issue: str
    severity: Severity
    action: str
    reference: str = ''


class RiskFactor(BaseModel):
    id: str
    label: str
    kind: Literal['history', 'environment', 'body', 'medication', 'living']
    action: str


class PostFallFinding(BaseModel):
    id: str
    severity: Severity
    title: str
    detail: str
    action: str


class SafetyAssessment(BaseModel):
    hazards: list[HazardFinding] = Field(default_factory=list)
    risk_factors: list[RiskFactor] = Field(default_factory=list)
    risk_level: Literal['low', 'medium', 'high'] = 'low'
    post_fall: list[PostFallFinding] = Field(default_factory=list)
    table_version: str


class SafetyTriage(BaseModel):
    level: Literal['L1', 'L2', 'L3', 'L4'] = 'L4'
    rule_ids: list[str] = Field(default_factory=list)
    required_action: Literal['call_120', 'emergency_department', 'contact_doctor_24h', 'safety_referral', 'self_care'] = 'self_care'
    red_flags: list[str] = Field(default_factory=list)
    table_version: str


class SafetyUnderstanding(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    supported: bool
    needs_clarification: bool
    clarification: str | None = Field(default=None, max_length=600)
    query: str | None = Field(default=None, max_length=1000)
    intent: Intent = 'other'
    missing_fields: list[str] = Field(default_factory=list, max_length=8)
    needs_freshness: bool = False
    possible_emergency: bool = False
    route: Literal['safety', 'health', 'medication', 'policy', 'diet', 'mind', 'none'] = 'safety'

    @model_validator(mode='after')
    def validate_active_branch(self):
        if not self.supported: return self
        if self.needs_clarification:
            if not self.clarification or not self.clarification.strip():
                raise ValueError('clarification_required_for_clarify_branch')
            self.clarification = self.clarification.strip()
            self.query = None
        else:
            if not self.query or not self.query.strip():
                raise ValueError('query_required_for_retrieve_branch')
            self.query = self.query.strip()
            self.clarification = None
        return self


class SafetyParagraph(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    text: str = Field(min_length=1, max_length=2000)
    sources: list[int] = Field(min_length=1, max_length=5)
    kind: Literal['environment', 'action', 'reason', 'referral'] = 'action'


class SafetyDraft(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    coverage: Literal['complete', 'partial'] = 'complete'
    missing_topics: list[Gap] = Field(default_factory=list, max_length=8)
    sufficient: bool
    paragraphs: list[SafetyParagraph] = Field(default_factory=list, max_length=8)


class SafetyQuote(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    source_index: int
    text: str = Field(default='', max_length=1600)
    span_ids: list[int] = Field(default_factory=list, max_length=8)


class SafetyReviewItem(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    paragraph: int = Field(ge=1)
    supported: bool
    addresses_question: bool = False
    reason: Literal['supported', 'off_topic', 'unsafe_move', 'rehab_prescription', 'construction_claim',
                    'overreach_diagnosis', 'unsupported_dimension']
    quotes: list[SafetyQuote] = Field(default_factory=list, max_length=8)


class SafetyReview(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    assessments: list[SafetyReviewItem] = Field(min_length=1, max_length=8)


class SafetyDialogueState(BaseModel):
    conditions: list[str] = Field(default_factory=list, max_length=10)
    medications: list[str] = Field(default_factory=list, max_length=10)
    previous_falls: int | None = Field(default=None, ge=0, le=100)
    living_alone: bool | None = None
    mobility: str = ''
    rooms: list[str] = Field(default_factory=list, max_length=10)
    topic: str = Field(default='', max_length=40)


class RouteSuggestion(BaseModel):
    agent: Literal['health', 'medication', 'policy', 'diet', 'mind', 'doctor', 'therapist']
    reason: str = Field(max_length=200)


class AdviceItem(BaseModel):
    kind: Literal['environment', 'action', 'reason', 'referral']
    text: str
    sources: list[int] = Field(default_factory=list, max_length=5)


class SafetyAnswer(BaseModel):
    status: Literal['answered', 'clarification', 'insufficient', 'emergency', 'boundary']
    urgency: Literal['L1', 'L2', 'L3', 'L4'] | None = None
    required_action: str | None = None
    answer: str
    hazards: list[HazardFinding] = Field(default_factory=list)
    risk_factors: list[RiskFactor] = Field(default_factory=list)
    risk_level: Literal['low', 'medium', 'high'] | None = None
    post_fall: list[PostFallFinding] = Field(default_factory=list)
    post_fall_advice: str | None = None
    boundary: str | None = None
    advice: list[AdviceItem] = Field(default_factory=list)
    red_flags_observed: list[str] = Field(default_factory=list)
    triage_rule_ids: list[str] = Field(default_factory=list)
    missing_info: list[Gap] = Field(default_factory=list)
    route_suggestion: RouteSuggestion | None = None
    coverage: Literal['complete', 'partial', 'none'] | None = None
    missing_topics: list[Gap] = Field(default_factory=list)
    general_info: list[str] = Field(default_factory=list)
    dialogue_state: 'SafetyDialogueState | None' = None
    citations: list[Citation] = Field(default_factory=list)
    retrieved_hits: list[SearchHit] = Field(default_factory=list)
    web_sources: list[WebSource] = Field(default_factory=list)
    web_status: Literal['not_used', 'not_configured', 'success', 'no_results', 'error'] = 'not_used'
    web_warning: str | None = None
    web_diagnostics: WebDiagnostics | None = None
    answer_checks: AnswerChecks | None = None
    metrics: ExecutionMetrics | None = None
    disclaimer: str = ''
    table_version: str
    vector_count: int = 0
    reason: str | None = None
    retrieval_log_id: str | None = None
    model: str
    knowledge_scope: list[str]
    steps: list[str]


SafetyQuestion.model_rebuild()
SafetyAnswer.model_rebuild()
