"""Medication agent contracts. Interactions and triage come from rules, never from the model."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.chat import AnswerChecks, ChatTurn, Citation, ExecutionMetrics, WebDiagnostics, WebSource
from app.schemas.retrieval import SearchHit

Topic = Literal['timing', 'missed_dose', 'interaction', 'adverse_reaction', 'duplication', 'education', 'dose_change', 'stop_or_switch', 'other']
Severity = Literal['high', 'moderate', 'note']
Frequency = Literal['once_daily', 'twice_daily', 'three_daily', 'four_daily', 'weekly', 'as_needed', 'unknown']
Gap = Literal['drug_list', 'dose_frequency', 'last_dose_time', 'symptom_detail', 'interaction_evidence', 'timing_evidence', 'adverse_evidence', 'full_medication_scope']

class MedicationProfile(BaseModel):
    """Minimal profile: age, conditions, allergies. No identity, no dose history."""
    model_config = ConfigDict(extra='forbid')
    age: int | None = Field(default=None, ge=0, le=130)
    conditions: list[Literal['hypertension', 'diabetes', 'ckd', 'heart_failure', 'copd', 'stroke_history', 'liver_disease', 'peptic_ulcer', 'asthma']] = Field(default_factory=list, max_length=9)
    allergies: list[str] = Field(default_factory=list, max_length=10)


class MedicationItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=60)
    frequency: Literal['once_daily', 'twice_daily', 'three_daily', 'four_daily', 'weekly', 'as_needed', 'unknown'] = 'unknown'


class MedicationQuestion(BaseModel):
    dialogue_state: 'MedicationDialogueState | None' = None
    profile: MedicationProfile = Field(default_factory=MedicationProfile)
    medications: list[MedicationItem] = Field(default_factory=list, max_length=20)
    question: str = Field(min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=6)

    @model_validator(mode='after')
    def nonblank(self):
        if not self.question.strip(): raise ValueError('请输入问题')
        self.question = self.question.strip()
        return self


class DrugMention(BaseModel):
    name: str
    canonical: str
    classes: list[str] = Field(default_factory=list)
    class_label: str
    tags: list[str] = Field(default_factory=list)
    indication: str
    timing_hint: str | None = None
    user_frequency: str = 'unknown'
    source: Literal['parsed', 'provided'] = 'parsed'


class InteractionFinding(BaseModel):
    id: str
    severity: Severity
    title: str
    drugs: list[str]
    detail: str
    action: str


class MedicationAssessment(BaseModel):
    drugs: list[DrugMention] = Field(default_factory=list)
    interactions: list[InteractionFinding] = Field(default_factory=list)
    unknown_names: list[str] = Field(default_factory=list)
    frequency: Frequency = 'unknown'
    table_version: str

    def high_count(self) -> int:
        return sum(1 for item in self.interactions if item.severity == 'high')


class MedicationTriage(BaseModel):
    level: Literal['L1', 'L2', 'L3', 'L4'] = 'L4'
    rule_ids: list[str] = Field(default_factory=list)
    required_action: Literal['call_120', 'emergency_department', 'contact_doctor_24h', 'pharmacist_advice', 'self_care'] = 'self_care'
    red_flags: list[str] = Field(default_factory=list)
    table_version: str


class MedicationUnderstanding(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    supported: bool
    needs_clarification: bool
    clarification: str | None = Field(default=None, max_length=600)
    query: str | None = Field(default=None, max_length=1000)
    topic: Topic = 'other'
    drugs: list[str] = Field(default_factory=list, max_length=10)
    missing_fields: list[str] = Field(default_factory=list, max_length=8)
    needs_freshness: bool = False
    possible_emergency: bool = False
    route: Literal['medication', 'health', 'policy', 'safety', 'diet', 'mind', 'none'] = 'medication'

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


class MedicationParagraph(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    text: str = Field(min_length=1, max_length=2000)
    sources: list[int] = Field(min_length=1, max_length=5)
    kind: Literal['explain', 'timing', 'caution', 'referral'] = 'explain'


class MedicationDraft(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    coverage: Literal['complete', 'partial'] = 'complete'
    missing_topics: list[Gap] = Field(default_factory=list, max_length=8)
    sufficient: bool
    paragraphs: list[MedicationParagraph] = Field(default_factory=list, max_length=6)


class MedicationQuote(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    source_index: int
    text: str = Field(default='', max_length=1600)
    span_ids: list[int] = Field(default_factory=list, max_length=8)


class MedicationReviewItem(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    paragraph: int = Field(ge=1)
    supported: bool
    addresses_question: bool = False
    reason: Literal['supported', 'off_topic', 'dose_advice', 'interaction_claim', 'substitution', 'overreach_diagnosis', 'unsupported_number']
    quotes: list[MedicationQuote] = Field(default_factory=list, max_length=8)


class MedicationReview(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    assessments: list[MedicationReviewItem] = Field(min_length=1, max_length=6)


class MedicationDialogueState(BaseModel):
    drugs: list[str] = Field(default_factory=list, max_length=12)
    topic: str = Field(default='', max_length=40)
    frequency: str = 'unknown'
    symptoms: list[str] = Field(default_factory=list, max_length=10)
    age: int | None = Field(default=None, ge=0, le=130)
    conditions: list[str] = Field(default_factory=list, max_length=10)


class RouteSuggestion(BaseModel):
    agent: Literal['health', 'policy', 'safety', 'diet', 'mind', 'doctor', 'pharmacist']
    reason: str = Field(max_length=200)


class MedicationAnswer(BaseModel):
    status: Literal['answered', 'clarification', 'insufficient', 'emergency', 'boundary']
    urgency: Literal['L1', 'L2', 'L3', 'L4'] | None = None
    required_action: str | None = None
    answer: str
    drugs: list[DrugMention] = Field(default_factory=list)
    interactions: list[InteractionFinding] = Field(default_factory=list)
    unknown_names: list[str] = Field(default_factory=list)
    missed_dose_advice: str | None = None
    boundary: str | None = None
    red_flags_observed: list[str] = Field(default_factory=list)
    triage_rule_ids: list[str] = Field(default_factory=list)
    missing_info: list[Gap] = Field(default_factory=list)
    route_suggestion: RouteSuggestion | None = None
    coverage: Literal['complete', 'partial', 'none'] | None = None
    missing_topics: list[Gap] = Field(default_factory=list)
    general_info: list[str] = Field(default_factory=list)
    dialogue_state: 'MedicationDialogueState | None' = None
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


MedicationQuestion.model_rebuild()
MedicationAnswer.model_rebuild()
