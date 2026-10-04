import asyncio
import os
from pathlib import Path
from temporalio import activity
from temporalio.exceptions import ApplicationError
from engineering.agents import DemoAgent
from engineering.models import ActivityRequest, ActivityResult
from engineering.workspace import Workspace, digest, run_allowed_check

agent = DemoAgent()


@activity.defn
async def engineering_step(request: ActivityRequest) -> ActivityResult:
    """All external work is behind one allowlisted Activity dispatcher."""
    data = request.data
    store = Workspace(Path(os.getenv("ARTIFACT_ROOT", "artifacts")), data.workspace_id)
    result = ActivityResult(attempt=activity.info().attempt)
    try:
        if data.provider == 'claude' and request.operation in {'understand', 'plan', 'prepare', 'apply', 'tests', 'security'}:
            from engineering.claude_steps import execute_claude
            result = await execute_claude(request, store)
            result.attempt = activity.info().attempt
            return result
        match request.operation:
            case "snapshot":
                if data.baseline_hash and data.version == 1:
                    from engineering.baselines import initialize_baseline
                    await asyncio.to_thread(initialize_baseline,
                        Path(os.getenv("ARTIFACT_ROOT", "artifacts")), store, data.baseline_hash)
                    result.detail = f"Brownfield baseline verified: {data.baseline_hash}"
                result.artifact = await asyncio.to_thread(store.snapshot, data.version)
            case "understand":
                result.detail = await agent.understand(data)
            case "plan":
                result.detail = await agent.plan(data)
            case "prepare":
                result.artifact, result.digest = await asyncio.to_thread(
                    store.prepare, data.version, data.revision, data.requirement, data.attempt)
                result.detail = "Demo proposal prepared for review; no application code generated"
            case "apply":
                result.artifact = await asyncio.to_thread(store.apply, data.version, data.revision, request.expected_hash)
                result.detail = "Approved demo artifact applied"
            case "tests":
                result.check = await agent.check("tests", data)
            case "security":
                result.check = await agent.check("security", data)
                content = await asyncio.to_thread(store.read, "workspace/change.json")
                if digest(content) != request.expected_hash:
                    result.check.passed = False
                    result.check.detail = "Workspace does not match approved artifact"
                else:
                    result.check.detail = "Artifact integrity passed; application security scan still simulated"
            case "rollback":
                await asyncio.to_thread(store.restore, data.version)
                result.detail = "Workspace restored to the version baseline"
            case "syntax":
                passed = await asyncio.to_thread(run_allowed_check, "python_syntax", data.requirement)
                result.detail = f"Syntax valid: {passed}"
            case _:
                raise ValueError("Activity operation is not allowed")
    except (ValueError, FileNotFoundError, TimeoutError) as exc:
        raise ApplicationError(str(exc), non_retryable=True) from exc
    return result


from engineering.approval_auth import authenticate_approval

ACTIVITIES = [engineering_step, authenticate_approval]
