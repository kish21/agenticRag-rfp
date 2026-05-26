from enum import Enum


class SectionType(str, Enum):
    REQUIREMENT_RESPONSE = "requirement_response"
    SUPPORTING_EVIDENCE = "supporting_evidence"
    BACKGROUND = "background"
    BOILERPLATE = "boilerplate"

class CriticSeverity(str, Enum):
    HARD = "hard"
    SOFT = "soft"
    LOG = "log"

class CriticVerdict(str, Enum):
    APPROVED = "approved"
    APPROVED_WITH_WARNINGS = "approved_with_warnings"
    BLOCKED = "blocked"
    ESCALATED = "escalated"

class ComplianceStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"

class DocumentStatus(str, Enum):
    CURRENT = "current"
    PENDING = "pending"
    EXPIRED = "expired"
    NOT_MENTIONED = "not_mentioned"

class DecisionBasis(str, Enum):
    EXPLICIT_CONFIRMATION = "explicit_confirmation"
    IMPLICIT_CONFIRMATION = "implicit_confirmation"
    PARTIAL_COMPLIANCE = "partial_compliance"
    EXPLICIT_DENIAL = "explicit_denial"
    NOT_ADDRESSED = "not_addressed"
