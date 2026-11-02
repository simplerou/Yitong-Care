"""Dietitian agent contracts. Food tags, portions and triage are deterministic."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.chat import AnswerChecks, ChatTurn, Citation, ExecutionMetrics, WebDiagnostics, WebSource
from app.schemas.retrieval import SearchHit

Intent = Literal['meal_plan', 'protein', 'salt_control', 'fruit_staple', 'texture', 'food_safety',
                 'condition_diet', 'food_drug', 'education', 'prescription_diet', 'supplement_dose',
                 'extreme_diet', 'replace_medication', 'other']
Severity = Literal['high', 'moderate', 'note']
Load = Literal['low', 'moderate', 'high', 'unknown']
Gap = Literal['condition_list', 'chewing_swallowing', 'weight_trend', 'allergy_list', 'medication_list',
              'portion_evidence', 'menu_evidence', 'full_diet_scope']


class DietProfile(BaseModel):
    """Minimal profile: age, body size, conditions, allergies, chewing/swallowing, drug names."""
    model_config = ConfigDict(extra='forbid')
    age: int | None = Field(default=None, ge=0, le=130)
    sex: Literal['male', 'female', 'unknown'] = 'unknown'
    weight_kg: float | None = Field(default=None, gt=20, le=200)
    height_cm: float | None = Field(default=None, gt=100, le=220)
    conditions: list[Literal['hypertension', 'diabetes', 'ckd', 'heart_failure', 'gout', 'copd',
                             'stroke_history', 'peptic_ulcer', 'liver_disease']] = Field(default_factory=list, max_length=9)
    allergies: list[str] = Field(default_factory=list, max_length=10)
    chewing: Literal['normal', 'difficult', 'soft_only'] = 'normal'
    swallowing: Literal['normal', 'choking_history'] = 'normal'
    medications: list[str] = Field(default_factory=list, max_length=10)


class FoodInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=40)
    amount: str | None = Field(default=None, max_length=40)


class DietQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=6)
    foods: list[FoodInput] = Field(default_factory=list, max_length=20)
    profile: DietProfile = Field(default_factory=DietProfile)
    dialogue_state: 'DietDialogueState | None' = None

    @model_validator(mode='after')
    def nonblank(self):
        if not self.question.strip(): raise ValueError('请输入问题')
        self.question = self.question.strip()
        return self


class FoodMention(BaseModel):
    name: str
    canonical: str
    categories: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    label: str
    note: str = ''
    source: Literal['parsed', 'provided'] = 'parsed'


class NutritionFinding(BaseModel):
    id: str
    severity: Severity
    title: str
    foods: list[str] = Field(default_factory=list)
    detail: str
    action: str


class PortionItem(BaseModel):
    name: str
    range_text: str
    note: str = ''


class PortionReference(BaseModel):
    table_version: str
    items: list[PortionItem]
    disclaimer: str


class NutritionAssessment(BaseModel):
    foods: list[FoodMention] = Field(default_factory=list)
    unknown_foods: list[str] = Field(default_factory=list)
    findings: list[NutritionFinding] = Field(default_factory=list)
    salt_load: Load = 'unknown'
    oil_load: Load = 'unknown'
    sugar_load: Load = 'unknown'
    protein_risk: bool = False
    produce_risk: bool = False
    calcium_risk: bool = False
    hydration_risk: bool = False
    monotony_risk: bool = False
    bmi: float | None = None
    table_version: str


class DietTriage(BaseModel):
    level: Literal['L1', 'L2', 'L3', 'L4'] = 'L4'
    rule_ids: list[str] = Field(default_factory=list)
    required_action: Literal['call_120', 'emergency_department', 'contact_doctor_24h', 'dietitian_referral', 'self_care'] = 'self_care'
    red_flags: list[str] = Field(default_factory=list)
    table_version: str


class DietUnderstanding(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    supported: bool
    needs_clarification: bool
    clarification: str | None = Field(default=None, max_length=600)
    query: str | None = Field(default=None, max_length=1000)
    intent: Intent = 'other'
    foods: list[str] = Field(default_factory=list, max_length=12)
    missing_fields: list[str] = Field(default_factory=list, max_length=8)
    needs_freshness: bool = False
    possible_emergency: bool = False
    route: Literal['diet', 'health', 'medication', 'policy', 'safety', 'mind', 'none'] = 'diet'

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


class DietParagraph(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    text: str = Field(min_length=1, max_length=2000)
    sources: list[int] = Field(min_length=1, max_length=5)
    kind: Literal['meal', 'reason', 'tip', 'referral'] = 'meal'


class DietDraft(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    coverage: Literal['complete', 'partial'] = 'complete'
    missing_topics: list[Gap] = Field(default_factory=list, max_length=8)
    sufficient: bool
    paragraphs: list[DietParagraph] = Field(default_factory=list, max_length=8)


class DietQuote(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    source_index: int
    text: str = Field(default='', max_length=1600)
    span_ids: list[int] = Field(default_factory=list, max_length=8)


class DietReviewItem(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    paragraph: int = Field(ge=1)
    supported: bool
    addresses_question: bool = False
    reason: Literal['supported', 'off_topic', 'diet_prescription', 'portion_invention', 'unsafe_food',
                    'drug_food_claim', 'extreme_diet', 'overreach_diagnosis']
    quotes: list[DietQuote] = Field(default_factory=list, max_length=8)


class DietReview(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    assessments: list[DietReviewItem] = Field(min_length=1, max_length=8)


class DietDialogueState(BaseModel):
    conditions: list[str] = Field(default_factory=list, max_length=10)
    allergies: list[str] = Field(default_factory=list, max_length=10)
    chewing: str = 'normal'
    swallowing: str = 'normal'
    dislikes: list[str] = Field(default_factory=list, max_length=10)
    foods_suggested: list[str] = Field(default_factory=list, max_length=20)
    topic: str = Field(default='', max_length=40)


class AdviceItem(BaseModel):
    kind: Literal['meal', 'reason', 'tip', 'referral']
    text: str
    sources: list[int] = Field(default_factory=list, max_length=5)


class RouteSuggestion(BaseModel):
    agent: Literal['health', 'medication', 'policy', 'safety', 'mind', 'doctor', 'dietitian']
    reason: str = Field(max_length=200)


class DietAnswer(BaseModel):
    status: Literal['answered', 'clarification', 'insufficient', 'emergency', 'boundary']
    urgency: Literal['L1', 'L2', 'L3', 'L4'] | None = None
    required_action: str | None = None
    answer: str
    foods: list[FoodMention] = Field(default_factory=list)
    findings: list[NutritionFinding] = Field(default_factory=list)
    unknown_foods: list[str] = Field(default_factory=list)
    portion_reference: PortionReference | None = None
    nutrition_risks: list[str] = Field(default_factory=list)
    boundary: str | None = None
    advice: list[AdviceItem] = Field(default_factory=list)
    red_flags_observed: list[str] = Field(default_factory=list)
    triage_rule_ids: list[str] = Field(default_factory=list)
    missing_info: list[Gap] = Field(default_factory=list)
    route_suggestion: RouteSuggestion | None = None
    coverage: Literal['complete', 'partial', 'none'] | None = None
    missing_topics: list[Gap] = Field(default_factory=list)
    general_info: list[str] = Field(default_factory=list)
    dialogue_state: 'DietDialogueState | None' = None
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


DietQuestion.model_rebuild()
DietAnswer.model_rebuild()
