"""Health agent contracts. Deterministic vitals classification is never delegated to the model."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.chat import AnswerChecks, ChatTurn, Citation, ExecutionMetrics, WebDiagnostics, WebSource
from app.schemas.retrieval import SearchHit

Metric = Literal['blood_pressure', 'heart_rate', 'fasting_glucose', 'postprandial_glucose', 'random_glucose', 'spo2', 'temperature', 'weight']
Condition = Literal['unknown', 'home', 'clinic']
MeasurementState = Literal['unknown', 'fasting', 'postprandial_2h', 'random', 'resting', 'after_exercise']

CategoryCode = Literal[
    'normal', 'elevated', 'stage1', 'stage2', 'stage3', 'crisis', 'low', 'severe_low',
    'high', 'severe_high', 'impaired', 'diabetes_range', 'igt', 'low_fever', 'moderate_fever',
    'high_fever', 'hyperpyrexia', 'hypothermia', 'recorded', 'unverified',
]

MissingField = Literal[
    'measurement_context', 'measurement_time', 'fasting_status', 'diastolic_value',
    'symptoms', 'age', 'conditions', 'explicit_value',
]

Gap = Literal[
    'measurement_method', 'target_values', 'symptom_triage_criteria', 'lifestyle_evidence',
    'medication_boundary', 'emergency_signs', 'lab_reference_range', 'full_health_scope',
]

Route = Literal['health', 'medication', 'policy', 'safety', 'diet', 'mind', 'none']


class VitalsInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    metric: Metric
    systolic: int | None = Field(default=None, ge=40, le=300)
    diastolic: int | None = Field(default=None, ge=20, le=200)
    value: float | None = Field(default=None, gt=0, le=600)
    unit: Literal['mmHg', 'bpm', 'mmol/L', 'mg/dL', '%', '°C', 'kg']
    context: Condition = 'unknown'
    condition: MeasurementState = 'unknown'
    measured_at: datetime | None = None

    @model_validator(mode='after')
    def check_shape(self):
        if self.metric == 'blood_pressure':
            if self.systolic is None or self.diastolic is None:
                raise ValueError('血压需同时提供 systolic 与 diastolic')
            if self.diastolic >= self.systolic:
                raise ValueError('舒张压需小于收缩压')
            if self.unit != 'mmHg':
                raise ValueError('血压单位应为 mmHg')
        elif self.value is None:
            raise ValueError('该指标需提供 value')
        return self


class HealthProfile(BaseModel):
    """Minimal profile. Never collects name, ID number, phone or address."""
    model_config = ConfigDict(extra='forbid')
    age: int | None = Field(default=None, ge=0, le=130)
    conditions: list[Literal['hypertension', 'diabetes', 'ckd', 'heart_failure', 'copd', 'stroke_history']] = Field(default_factory=list, max_length=6)
    medications: list[str] = Field(default_factory=list, max_length=10)


class HealthDialogueState(BaseModel):
    metric: str = Field(default='', max_length=40)
    value_text: str = Field(default='', max_length=80)
    symptoms: list[str] = Field(default_factory=list, max_length=10)
    age: int | None = Field(default=None, ge=0, le=130)
    conditions: list[str] = Field(default_factory=list, max_length=10)
    topic: str = Field(default='', max_length=40)
    last_reading_keys: list[str] = Field(default_factory=list, max_length=20)


class HealthQuestion(BaseModel):
    dialogue_state: HealthDialogueState | None = None
    profile: HealthProfile = Field(default_factory=HealthProfile)
    vitals: list[VitalsInput] = Field(default_factory=list, max_length=12)
    question: str = Field(min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=6)

    @model_validator(mode='after')
    def nonblank(self):
        if not self.question.strip(): raise ValueError('请输入问题')
        self.question = self.question.strip()
        return self


class VitalsReading(BaseModel):
    metric: Metric
    systolic: int | None = None
    diastolic: int | None = None
    value: float | None = None
    unit: str
    display: str
    context: Condition = 'unknown'
    condition: MeasurementState = 'unknown'
    category: str
    category_code: CategoryCode
    reference_basis: str
    table_version: str
    flags: list[str] = Field(default_factory=list)
    source: Literal['parsed', 'provided'] = 'parsed'


class VitalsAssessment(BaseModel):
    readings: list[VitalsReading] = Field(default_factory=list)
    primary: VitalsReading | None = None
    missing: list[MissingField] = Field(default_factory=list)
    implausible: bool = False
    unverified_from_model: bool = False
    table_version: str

    def summary_lines(self) -> list[str]:
        lines = []
        for reading in self.readings:
            line = f'本次记录：{reading.display} → {reading.category}'
            if reading.reference_basis:
                line += f'\n判读依据：{reading.reference_basis}（判读表 {reading.table_version}）'
            if 'implausible' in reading.flags:
                line += '\n该数值明显超出可测量范围，可能记录有误，未参与分级。'
            lines.append(line)
        return lines


class Triage(BaseModel):
    level: Literal['L1', 'L2', 'L3', 'L4'] = 'L4'
    rule_ids: list[str] = Field(default_factory=list)
    required_action: Literal['call_120', 'emergency_department', 'contact_doctor_24h', 'clinic_visit', 'self_care'] = 'self_care'
    red_flags: list[str] = Field(default_factory=list)
    table_version: str


class HealthUnderstanding(BaseModel):
    """Model output for the understand node. Only shape is enforced here."""
    model_config = ConfigDict(strict=True, extra='forbid')
    supported: bool
    needs_clarification: bool
    clarification: str | None = Field(default=None, max_length=600)
    query: str | None = Field(default=None, max_length=1000)
    metric: str | None = Field(default=None, max_length=40)
    missing_fields: list[str] = Field(default_factory=list, max_length=8)
    needs_freshness: bool = False
    possible_emergency: bool = False
    route: Route = 'health'
    reported_value: str | None = Field(default=None, max_length=60)

    @model_validator(mode='after')
    def validate_active_branch(self):
        if not self.supported:
            return self
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


class HealthParagraph(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    text: str = Field(min_length=1, max_length=2000)
    sources: list[int] = Field(min_length=1, max_length=5)
    kind: Literal['explain', 'lifestyle', 'monitor', 'referral'] = 'explain'


class HealthDraft(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    coverage: Literal['complete', 'partial'] = 'complete'
    missing_topics: list[Gap] = Field(default_factory=list, max_length=8)
    sufficient: bool
    paragraphs: list[HealthParagraph] = Field(default_factory=list, max_length=6)


class HealthQuote(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    source_index: int
    text: str = Field(default='', max_length=1600)
    span_ids: list[int] = Field(default_factory=list, max_length=8)


class HealthReviewItem(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    paragraph: int = Field(ge=1)
    supported: bool
    addresses_question: bool = False
    reason: Literal['supported', 'off_topic', 'unsafe_advice', 'medication_instruction',
                    'overreach_diagnosis', 'unsupported_number', 'missing_referral', 'wrong_category']
    quotes: list[HealthQuote] = Field(default_factory=list, max_length=8)


class HealthReview(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    assessments: list[HealthReviewItem] = Field(min_length=1, max_length=6)


class AdviceItem(BaseModel):
    kind: Literal['explain', 'lifestyle', 'monitor', 'referral']
    text: str
    sources: list[int] = Field(default_factory=list, max_length=5)


class RouteSuggestion(BaseModel):
    agent: Literal['medication', 'policy', 'safety', 'diet', 'mind']
    reason: str = Field(max_length=200)


class HealthAnswer(BaseModel):
    status: Literal['answered', 'clarification', 'insufficient', 'emergency']
    urgency: Literal['L1', 'L2', 'L3', 'L4'] | None = None
    required_action: Literal['call_120', 'emergency_department', 'contact_doctor_24h', 'clinic_visit', 'self_care'] | None = None
    answer: str
    vitals_assessment: VitalsAssessment | None = None
    red_flags_observed: list[str] = Field(default_factory=list)
    missing_info: list[MissingField] = Field(default_factory=list)
    advice: list[AdviceItem] = Field(default_factory=list)
    triage_rule_ids: list[str] = Field(default_factory=list)
    route_suggestion: RouteSuggestion | None = None
    coverage: Literal['complete', 'partial', 'none'] | None = None
    missing_topics: list[Gap] = Field(default_factory=list)
    general_info: list[str] = Field(default_factory=list)
    dialogue_state: HealthDialogueState | None = None
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
