import re
from engineering.models import ReviewDecision, RunRequest, RunState, Task


def validate_request(request: RunRequest) -> None:
    if getattr(request, "baseline_hash", "") and not re.fullmatch(r"[a-f0-9]{64}", request.baseline_hash):
        raise ValueError("Invalid baseline hash")
    if request.provider not in {"demo", "claude"}:
        raise ValueError("Unsupported provider")
    if request.provider == "claude" and request.demo_failures:
        raise ValueError("Simulated failures are available only in demo mode")
    if not request.requirement.strip():
        raise ValueError("Requirement must not be empty")
    if len(request.requirement) > 10000:
        raise ValueError("Requirement exceeds 10000 characters")
    if not 1 <= request.approval_timeout_seconds <= 86400:
        raise ValueError("Approval timeout must be between 1 and 86400 seconds")
    if not 0 <= request.max_repairs <= 2:
        raise ValueError("Repair budget must be between zero and two")
    if not 0 <= request.demo_failures <= 3:
        raise ValueError("Demo failures must be between zero and three")


def validate_review(state: RunState, decision: ReviewDecision, decided: bool) -> None:
    if state.stage not in {"awaiting_review", "awaiting_apply"} or decided:
        raise ValueError("No review is pending")
    expected_gate = "apply" if state.stage == "awaiting_apply" else "review"
    if decision.gate != expected_gate:
        raise ValueError("Wrong approval gate")
    if decision.revision != state.revision:
        raise ValueError("Stale review revision")
    if not decision.reviewer.strip():
        raise ValueError("Reviewer is required")


def lifecycle_graph() -> list[Task]:
    return [
        Task("understand"), Task("plan", ["understand"]),
        Task("apply_approval", ["plan"]), Task("implement", ["apply_approval"]), Task("tests", ["implement"]),
        Task("security", ["implement"]),
        Task("review", ["tests", "security"]), Task("summary", ["review"]),
    ]
