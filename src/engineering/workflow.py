import asyncio
import hashlib
from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from engineering.activities import engineering_step
    from engineering.approval_auth import authenticate_approval
    from engineering.models import (
        ActivityRequest, ActivityResult, ApprovalVerification, AuditEvent, Clarification, RequirementChange,
        ReviewDecision, RunRequest, RunState, StageInput,
    )
    from engineering.policy import lifecycle_graph, validate_request, validate_review
    from engineering.security import redact, validate_text


@workflow.defn
class EngineeringWorkflow:
    def __init__(self) -> None:
        self.state = RunState()
        self.decision: ReviewDecision | None = None
        self.pending: RequirementChange | None = None
        self.answer: str | None = None
        self.stop_reason = ""
        self.started = workflow.now()
        self.stage_started = self.started
        self.recovery_started = None

    def audit(self, kind: str, detail: str) -> None:
        detail = redact(detail)
        self.state.audit.append(AuditEvent(
            len(self.state.audit) + 1, workflow.now().isoformat(), kind,
            self.state.requirement_version, self.state.revision, detail))
        self.state.events.append(f"{kind}: {detail}")

    def stage(self, name: str) -> None:
        now = workflow.now()
        previous = self.state.stage
        metrics = self.state.metrics
        metrics.stage_seconds[previous] = metrics.stage_seconds.get(previous, 0) + (now - self.stage_started).total_seconds()
        metrics.elapsed_seconds = (now - self.started).total_seconds()
        self.state.stage = name
        self.stage_started = now

    @workflow.query
    def status(self) -> RunState:
        return self.state

    def validate_active(self) -> None:
        if self.state.stage in {"created", "completed", "stopped", "needs_intervention"}:
            raise ValueError("Workflow is not accepting changes")
        if self.stop_reason:
            raise ValueError("Stop already requested")

    @workflow.update
    async def review(self, decision: ReviewDecision) -> str:
        self.validate_decision(decision)
        if self.state.mode == "claude":
            try:
                await workflow.execute_activity(authenticate_approval, ApprovalVerification(
                    self.state.workspace_id, self.state.requirement_version,
                    self.state.candidate_hash, decision),
                    start_to_close_timeout=timedelta(seconds=10),
                    schedule_to_close_timeout=timedelta(seconds=15),
                    retry_policy=RetryPolicy(maximum_attempts=1))
            except ActivityError:
                self.audit("approval_rejected", "Signature verification failed")
                raise ApplicationError("Approval authentication failed") from None
            # A requirement update, deadline, or competing approval may have won while verifying.
            self.validate_decision(decision)
            self.audit("approval_authenticated", f"Verified signing key for {decision.reviewer}")
        self.decision = decision
        self.audit("approval", f"{decision.gate} r{decision.revision}: {decision.approved} by {decision.reviewer}")
        return "Decision recorded"

    @review.validator
    def validate_decision(self, decision: ReviewDecision) -> None:
        validate_review(self.state, decision, self.decision is not None)
        if self.state.mode == "claude" and (not decision.signature or len(decision.signature) > 128):
            raise ValueError("Claude approvals require a signed decision")
        validate_text(decision.reviewer)
        if len(decision.reviewer) > 100:
            raise ValueError("Reviewer label is too long")
        if self.pending or self.stop_reason:
            raise ValueError("Review invalidated")

    @workflow.update
    def change_requirement(self, change: RequirementChange) -> str:
        self.validate_change(change)
        self.pending = change
        self.decision = None
        self.state.checks = []
        self.audit("invalidation", "Requirement change accepted; plan, checks, and approvals invalidated")
        return "Change queued; current Activities finish before workspace restoration and replanning"

    @change_requirement.validator
    def validate_change(self, change: RequirementChange) -> None:
        self.validate_active()
        if self.pending:
            raise ValueError("A requirement change is already pending")
        if change.expected_version != self.state.requirement_version:
            raise ValueError("Stale requirement version")
        if self.state.metrics.replans >= 5:
            raise ValueError("Replan budget exhausted")
        if not change.requirement.strip() or not change.reason.strip() or len(change.requirement) > 10000 or len(change.reason) > 1000:
            raise ValueError("Provide a bounded requirement and change reason")
        validate_text(change.requirement)
        validate_text(change.reason)

    @workflow.update
    def clarify(self, answer: Clarification) -> str:
        self.validate_answer(answer)
        self.answer = answer.answer
        self.audit("clarification", answer.answer)
        return "Clarification recorded"

    @clarify.validator
    def validate_answer(self, answer: Clarification) -> None:
        self.validate_active()
        if self.state.stage != "awaiting_clarification" or self.answer is not None or self.pending:
            raise ValueError("No clarification is pending")
        if answer.expected_version != self.state.requirement_version:
            raise ValueError("Stale requirement version")
        if not answer.answer.strip() or len(answer.answer) > 5000:
            raise ValueError("Provide a bounded answer")
        validate_text(answer.answer)

    @workflow.update
    def request_stop(self, reason: str) -> str:
        self.validate_stop(reason)
        self.stop_reason = reason
        self.decision = None
        self.audit("stop_requested", reason)
        return "Stop queued; active Activities finish before restoration"

    @request_stop.validator
    def validate_stop(self, reason: str) -> None:
        self.validate_active()
        if not reason.strip() or len(reason) > 1000:
            raise ValueError("Provide a bounded stop reason")
        validate_text(reason)

    async def step(self, name: str, data: StageInput, expected_hash: str = "") -> ActivityResult:
        self.state.metrics.activity_calls += 1
        try:
            result = await workflow.execute_activity(
                engineering_step, ActivityRequest(name, data, expected_hash),
                start_to_close_timeout=timedelta(seconds=300 if data.provider == "claude" else 30),
                schedule_to_close_timeout=timedelta(seconds=310 if data.provider == "claude" else 100),
                retry_policy=RetryPolicy(maximum_attempts=1 if data.provider == "claude" else 3),
            )
        except ActivityError:
            self.state.metrics.activity_failures += 1
            self.audit("activity_failed", name)
            raise
        self.state.metrics.activity_retries += result.attempt - 1
        self.audit("activity_completed", f"{name}; attempts={result.attempt}; {result.detail}")
        return result

    async def gate(self, name: str, timeout: int) -> bool:
        self.decision = None
        self.stage("awaiting_apply" if name == "apply" else "awaiting_review")
        self.audit("approval_requested", f"{name}; artifact={self.state.candidate_artifact}; sha256={self.state.candidate_hash}")
        try:
            await workflow.wait_condition(
                lambda: self.decision is not None or self.pending is not None or bool(self.stop_reason),
                timeout=timedelta(seconds=timeout))
        except asyncio.TimeoutError:
            self.stop_reason = f"{name} approval timed out"
            return False
        if self.pending or self.stop_reason:
            return False
        if not self.decision or not self.decision.approved:
            self.stop_reason = f"Reviewer rejected {name}"
            return False
        return True

    async def restore(self, data: StageInput) -> bool:
        self.stage("rollback")
        try:
            await self.step("rollback", data)
            self.state.metrics.rollbacks += 1
            self.audit("rollback", "Restored version baseline; proposals and history retained")
            return True
        except ActivityError:
            self.state.metrics.rollback_failures += 1
            self.stop_reason = "Rollback failed; manual workspace recovery required"
            return False

    def finish(self, stage: str, summary: str) -> RunState:
        self.stage(stage)
        self.state.summary = summary
        self.audit("finished", summary)
        return self.state

    @workflow.run
    async def run(self, request: RunRequest) -> RunState:
        try:
            validate_request(request)
            validate_text(request.requirement)
            validate_text(request.clarification_question)
        except ValueError as exc:
            raise ApplicationError(str(exc), non_retryable=True) from exc
        self.state.baseline_hash = getattr(request, "baseline_hash", "")
        self.state.mode = request.provider
        self.state.tasks = lifecycle_graph()
        self.state.requirement = request.requirement
        self.state.question = request.clarification_question
        identity = f"{workflow.info().workflow_id}/{workflow.info().run_id}"
        self.state.workspace_id = hashlib.sha256(identity.encode()).hexdigest()
        self.stage("starting")
        while True:
            version = self.state.requirement_version
            data = StageInput(self.state.requirement, demo_failures=request.demo_failures,
                              workspace_id=self.state.workspace_id, version=version, provider=request.provider)
            if getattr(request, "baseline_hash", ""):
                data.baseline_hash = request.baseline_hash
            baseline = False
            dirty = False
            try:
                self.stage("snapshot")
                await self.step("snapshot", data)
                baseline = True
                if self.state.question and not self.pending and not self.stop_reason:
                    self.stage("awaiting_clarification")
                    try:
                        await workflow.wait_condition(
                            lambda: self.answer is not None or self.pending is not None or bool(self.stop_reason),
                            timeout=timedelta(seconds=request.approval_timeout_seconds))
                    except asyncio.TimeoutError:
                        self.stop_reason = "Clarification timed out"
                    if self.answer and not self.pending:
                        self.state.requirement += "\nClarification: " + self.answer
                        data.requirement = self.state.requirement
                        self.state.question = ""
                for name in ["understand", "plan"]:
                    if self.pending or self.stop_reason:
                        break
                    self.stage(name)
                    result = await self.step(name, data)
                    if name == "understand" and result.questions and not self.pending and not self.stop_reason:
                        self.state.question = "\n".join(result.questions)
                        self.answer = None
                        self.stage("awaiting_clarification")
                        try:
                            await workflow.wait_condition(
                                lambda: self.answer is not None or self.pending is not None or bool(self.stop_reason),
                                timeout=timedelta(seconds=request.approval_timeout_seconds))
                        except asyncio.TimeoutError:
                            self.stop_reason = "Clarification timed out"
                        if self.answer and not self.pending:
                            self.state.requirement += "\nClarification: " + self.answer
                            data.requirement = self.state.requirement
                            self.state.question = ""
                for attempt in range(request.max_repairs + 1):
                    if self.pending or self.stop_reason:
                        break
                    data.attempt = attempt
                    self.state.revision += 1
                    data.revision = self.state.revision
                    self.stage("prepare")
                    proposal = await self.step("prepare", data)
                    self.state.candidate_artifact = proposal.artifact
                    self.state.candidate_hash = proposal.digest
                    if self.pending or self.stop_reason or not await self.gate("apply", request.approval_timeout_seconds):
                        break
                    self.stage("apply")
                    dirty = True  # A failed or interrupted write still requires restoration.
                    await self.step("apply", data, proposal.digest)
                    if self.pending or self.stop_reason:
                        break
                    self.stage("validate")
                    # Wait for every branch, even if one fails, before any rollback.
                    results = await asyncio.gather(
                        self.step("tests", data), self.step("security", data, proposal.digest),
                        return_exceptions=True)
                    for result in results:
                        if isinstance(result, BaseException):
                            raise result
                    if self.pending or self.stop_reason:
                        break
                    self.state.checks = [result.check for result in results if result.check is not None]
                    if len(self.state.checks) == 2 and all(c.passed for c in self.state.checks):
                        if self.recovery_started is not None:
                            self.state.metrics.recovery_seconds += (workflow.now() - self.recovery_started).total_seconds()
                            self.state.metrics.recoveries += 1
                            self.recovery_started = None
                        if await self.gate("review", request.approval_timeout_seconds):
                            return self.finish("completed", "Claude changes approved; tests, source scanning, and dependency audit passed. Not deployed." if request.provider == "claude" else "Demo artifacts approved. No application code generated or deployed.")
                        break
                    self.audit("validation_failed", str(self.state.checks))
                    if any(c.detail.startswith("VALIDATION_BLOCKED:") for c in self.state.checks):
                        self.stop_reason = "Validation environment unavailable; provision the test runner before a new run"
                        break
                    if self.recovery_started is None:
                        self.recovery_started = workflow.now()
                    if attempt == request.max_repairs:
                        self.stop_reason = "Validation exhausted the repair budget"
                        break
                    self.state.repairs += 1
                    self.state.metrics.repairs += 1
            except ActivityError:
                self.stop_reason = "Activity failed; fallback is human review of retained evidence"
            if dirty and baseline:
                if not await self.restore(data):
                    return self.finish("needs_intervention", self.stop_reason)
            if self.stop_reason:
                return self.finish("stopped", self.stop_reason + "; evidence retained for human handoff")
            if self.pending:
                change = self.pending
                self.pending = None
                self.state.requirement_version += 1
                self.state.requirement = change.requirement
                self.state.metrics.replans += 1
                self.state.checks = []
                self.state.candidate_artifact = ""
                self.state.candidate_hash = ""
                self.decision = None
                self.answer = None
                self.state.question = ""
                self.recovery_started = None
                self.audit("replan", change.reason)
                continue
            return self.finish("stopped", "No valid continuation; human intervention required")
