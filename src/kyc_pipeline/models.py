
from pydantic import BaseModel, Field
from typing import List, Optional

class ExtractedKyc(BaseModel):
    name: Optional[str]
    dob: Optional[str]
    address: Optional[str]
    id_number: Optional[str]
    email: Optional[str]
    has_face_photo: Optional[bool]
    coverage_notes: Optional[str] = None
    confidence: float = 0.0

class JudgeVerdict(BaseModel):
    passed: bool
    confidence: float
    rationale: str
    rework_notes: Optional[str] = None

class RuleViolation(BaseModel):
    code: str
    text: str
    citation: str

class RuleEvaluation(BaseModel):
    violations: List[RuleViolation] = Field(default_factory=list)
    decision_hint: str  # APPROVE | REJECT

class RiskAssessment(BaseModel):
    risk_grade: str     # LOW | MEDIUM | HIGH
    explanation: str
    matches: list = Field(default_factory=list)

class FinalDecision(BaseModel):
    decision: str       # APPROVE | REJECT | HUMAN_REVIEW
    reasons: List[str]
    message: str
