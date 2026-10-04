"""Replace DemoAgent with a provider adapter; keep I/O inside Activities."""
from typing import Protocol
from engineering.models import CheckResult, StageInput


class EngineeringAgent(Protocol):
    async def understand(self, request: StageInput) -> str: ...
    async def plan(self, request: StageInput) -> str: ...
    async def implement(self, request: StageInput) -> str: ...
    async def check(self, name: str, request: StageInput) -> CheckResult: ...


class DemoAgent:
    """Orchestration fixture. Does not call an LLM, edit code, or run checks."""

    async def understand(self, request: StageInput) -> str:
        return f"DEMO requirement received: {request.requirement}"

    async def plan(self, request: StageInput) -> str:
        return "DEMO plan: implement API, storage, tests, and documentation"

    async def implement(self, request: StageInput) -> str:
        return f"DEMO implementation attempt {request.attempt}; no files changed"

    async def check(self, name: str, request: StageInput) -> CheckResult:
        passed = name != "tests" or request.attempt >= request.demo_failures
        return CheckResult(name, passed, "SIMULATED result; no real validation performed")
