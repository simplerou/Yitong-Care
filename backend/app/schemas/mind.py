"""Mind companion contracts. Crisis handling and suicide-risk triage are code-owned."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.chat import AnswerChecks, ChatTurn, Citation, ExecutionMetrics, WebDiagnostics, WebSource
from app.schemas.retrieval import SearchHit

Intent = Literal['emotional_support', 'loneliness', 'grief', 'sleep', 'family_conflict', 'retirement',
                 'social_connection', 'education', 'diagnosis_request', 'medication_request',
                 'therapy_request', 'confidentiality', 'other']
Severity = Literal['high', 'moderate', 'note']
Gap = Literal['mood_detail', 'duration', 'sleep_detail', 'support_person', 'safety_status',
              'grief_context', 'social_situation', 'evidence']

CRISIS_LINE = '12356'


class MindProfile(BaseModel):
    """Minimal profile: age, living situation, support, recent losses. No identity fields."""
    model_config = ConfigDict(extra='forbid')
    age: int | None = Field(default=None, ge=0, le=130)
    living_alone: bool = False
    has_confidant: bool | None = None
    recent_loss: bool = False
    conditions: list[Literal['depression_history', 'anxiety_history', 'dementia', 'chronic_pain',
                             'insomnia', 'stroke_history']] = Field(default_factory=list, max_length=6)
    medications: list[str] = Field(default_factory=list, max_length=10)


class MindQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=6)
    profile: MindProfile = Field(default_factory=MindProfile)
    dialogue_state: 'MindDialogueState | None' = None

    @model_validator(mode='after')
    def nonblank(self):
        if not self.question.strip(): raise ValueError('请输入问题')
        self.question = self.question.strip()
        return self


class RiskSignal(BaseModel):
    id: str
    label: str
    kind: Literal['risk', 'protective', 'trigger']
    detail: str = ''


class ScreeningResult(BaseModel):
    low_mood: bool = False
    anhedonia: bool = False
    duration_two_weeks: bool = False
    functional_impairment: bool = False
    positive: bool = False
    note: str = ''


class MindAssessment(BaseModel):
    signals: list[RiskSignal] = Field(default_factory=list)
    screening: ScreeningResult = Field(default_factory=ScreeningResult)
    risk_level: Literal['low', 'medium', 'high', 'critical'] = 'low'
    table_version: str


class MindTriage(BaseModel):
    level: Literal['L1', 'L2', 'L3', 'L4'] = 'L4'
    rule_ids: list[str] = Field(default_factory=list)
    required_action: Literal['crisis_line', 'emergency_120', 'mental_health_referral', 'self_care'] = 'self_care'
    red_flags: list[str] = Field(default_factory=list)
    table_version: str


class MindUnderstanding(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    supported: bool
    needs_clarification: bool
    clarification: str | None = Field(default=None, max_length=600)
    query: str | None = Field(default=None, max_length=1000)
    intent: Intent = 'other'
    missing_fields: list[str] = Field(default_factory=list, max_length=8)
    needs_freshness: bool = False
    possible_crisis: bool = False
    route: Literal['mind', 'health', 'medication', 'policy', 'diet', 'safety', 'none'] = 'mind'

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


class MindParagraph(BaseModel):
    """Empathy paragraphs carry no citations; advice paragraphs must carry sources."""
    model_config = ConfigDict(strict=True, extra='forbid')
    text: str = Field(min_length=1, max_length=2000)
    sources: list[int] = Field(default_factory=list, max_length=5)
    kind: Literal['empathy', 'advice', 'referral'] = 'advice'

    @model_validator(mode='after')
    def check_sources(self):
        if self.kind == 'empathy' and self.sources:
            raise ValueError('empathy_paragraph_must_not_cite')
        if self.kind != 'empathy' and not self.sources:
            raise ValueError('advice_paragraph_requires_sources')
        return self


class MindDraft(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    coverage: Literal['complete', 'partial'] = 'complete'
    missing_topics: list[Gap] = Field(default_factory=list, max_length=8)
    sufficient: bool
    paragraphs: list[MindParagraph] = Field(default_factory=list, max_length=8)


class MindQuote(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    source_index: int
    text: str = Field(default='', max_length=1600)
    span_ids: list[int] = Field(default_factory=list, max_length=8)


class MindReviewItem(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    paragraph: int = Field(ge=1)
    supported: bool
    addresses_question: bool = False
    reason: Literal['supported', 'off_topic', 'harmful_advice', 'toxic_positivity', 'overreach_diagnosis',
                    'medication_advice', 'confidentiality_overclaim', 'unsupported_claim']
    quotes: list[MindQuote] = Field(default_factory=list, max_length=8)


class MindReview(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    assessments: list[MindReviewItem] = Field(min_length=1, max_length=8)


class MindDialogueState(BaseModel):
    topic: str = Field(default='', max_length=40)
    mood_words: list[str] = Field(default_factory=list, max_length=10)
    duration: str = Field(default='', max_length=40)
    sleep: str = Field(default='', max_length=40)
    support_person: str = Field(default='', max_length=40)
    losses: list[str] = Field(default_factory=list, max_length=5)


class RouteSuggestion(BaseModel):
    agent: Literal['health', 'medication', 'policy', 'diet', 'safety', 'doctor', 'counselor']
    reason: str = Field(max_length=200)


class AdviceItem(BaseModel):
    kind: Literal['empathy', 'advice', 'referral']
    text: str
    sources: list[int] = Field(default_factory=list, max_length=5)


class MindAnswer(BaseModel):
    status: Literal['answered', 'clarification', 'insufficient', 'crisis', 'boundary']
    urgency: Literal['L1', 'L2', 'L3', 'L4'] | None = None
    required_action: str | None = None
    answer: str
    signals: list[RiskSignal] = Field(default_factory=list)
    screening: ScreeningResult | None = None
    risk_level: Literal['low', 'medium', 'high', 'critical'] | None = None
    safety_plan: list[str] = Field(default_factory=list)
    crisis_notice: str | None = None
    boundary: str | None = None
    advice: list[AdviceItem] = Field(default_factory=list)
    red_flags_observed: list[str] = Field(default_factory=list)
    triage_rule_ids: list[str] = Field(default_factory=list)
    missing_info: list[Gap] = Field(default_factory=list)
    route_suggestion: RouteSuggestion | None = None
    coverage: Literal['complete', 'partial', 'none'] | None = None
    missing_topics: list[Gap] = Field(default_factory=list)
    general_info: list[str] = Field(default_factory=list)
    dialogue_state: 'MindDialogueState | None' = None
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


MindQuestion.model_rebuild()
MindAnswer.model_rebuild()
