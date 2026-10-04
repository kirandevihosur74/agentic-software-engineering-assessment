from dataclasses import dataclass, field


@dataclass
class RunRequest:
    requirement: str
    max_repairs: int = 2
    demo_failures: int = 0
    clarification_question: str = ""
    approval_timeout_seconds: int = 86400
    provider: str = "demo"
    baseline_hash: str = ""


@dataclass
class Task:
    name: str
    depends_on: list[str] = field(default_factory=list)


@dataclass
class StageInput:
    requirement: str
    attempt: int = 0
    demo_failures: int = 0
    workspace_id: str = ""
    version: int = 1
    revision: int = 1
    provider: str = "demo"
    baseline_hash: str = ""


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass
class ReviewDecision:
    revision: int
    approved: bool
    reviewer: str
    gate: str = "review"
    signature: str = ""
    expires_at: int = 0


@dataclass
class RequirementChange:
    expected_version: int
    requirement: str
    reason: str


@dataclass
class Clarification:
    expected_version: int
    answer: str


@dataclass
class AuditEvent:
    sequence: int
    timestamp: str
    kind: str
    version: int
    revision: int
    detail: str


@dataclass
class Metrics:
    activity_calls: int = 0
    activity_retries: int = 0
    activity_failures: int = 0
    repairs: int = 0
    replans: int = 0
    rollbacks: int = 0
    rollback_failures: int = 0
    recoveries: int = 0
    recovery_seconds: float = 0.0
    elapsed_seconds: float = 0.0
    stage_seconds: dict[str, float] = field(default_factory=dict)


@dataclass
class ActivityRequest:
    operation: str
    data: StageInput
    expected_hash: str = ""


@dataclass
class ActivityResult:
    detail: str = ""
    attempt: int = 1
    artifact: str = ""
    digest: str = ""
    check: CheckResult | None = None
    questions: list[str] = field(default_factory=list)


@dataclass
class RunState:
    stage: str = "created"
    mode: str = "demo"
    revision: int = 0
    repairs: int = 0
    requirement_version: int = 1
    requirement: str = ""
    workspace_id: str = ""
    question: str = ""
    baseline_hash: str = ""
    candidate_artifact: str = ""
    candidate_hash: str = ""
    tasks: list[Task] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    audit: list[AuditEvent] = field(default_factory=list)
    metrics: Metrics = field(default_factory=Metrics)
    summary: str = ""


@dataclass
class ApprovalVerification:
    workspace_id: str
    version: int
    candidate_hash: str
    decision: ReviewDecision
