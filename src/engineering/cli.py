import argparse
import asyncio
from dataclasses import asdict
import json
import os
from pathlib import Path
from temporalio.client import Client, WorkflowExecutionStatus
from engineering.config import ADDRESS, NAMESPACE, TASK_QUEUE
from engineering.models import Clarification, RequirementChange, ReviewDecision, RunRequest
from engineering.policy import validate_request
from engineering.security import validate_text
from engineering.metrics import aggregate
from engineering.workflow import EngineeringWorkflow


async def execute(args: argparse.Namespace) -> None:
    if args.command == "metrics":
        print(json.dumps(aggregate(json.loads(Path(p).read_text()) for p in args.reports), indent=2))
        return
    # Validate before sending: secrets in workflow inputs otherwise enter server history.
    for name in ("requirement", "reason", "answer", "question", "reviewer"):
        value = getattr(args, name, None)
        if value:
            validate_text(value)
    client = await Client.connect(ADDRESS, namespace=NAMESPACE)
    if args.command == "start":
        request = RunRequest(args.requirement, demo_failures=args.demo_failures,
                             clarification_question=args.question,
                             approval_timeout_seconds=args.approval_timeout, provider=args.provider)
        if args.from_workflow:
            from engineering.baselines import bundle_baseline
            source_handle = client.get_workflow_handle(args.from_workflow)
            if (await source_handle.describe()).status != WorkflowExecutionStatus.COMPLETED:
                raise ValueError('Brownfield source must be completed')
            original = await source_handle.result()
            if original['stage'] != 'completed' or not original['checks'] or not all(check['passed'] for check in original['checks']):
                raise ValueError('Brownfield source must be a completed run with passing checks')
            request.baseline_hash = bundle_baseline(
                Path(os.getenv('ARTIFACT_ROOT', 'artifacts')), original['workspace_id'], args.from_workflow)
        validate_request(request)
        handle = await client.start_workflow(EngineeringWorkflow.run, request,
                                            id=args.id, task_queue=TASK_QUEUE)
        print(handle.id)
        return
    handle = client.get_workflow_handle(args.id)
    if args.command in {"status", "export"}:
        if (await handle.describe()).status == WorkflowExecutionStatus.COMPLETED:
            state = await handle.result()
        else:
            state = asdict(await handle.query(EngineeringWorkflow.status))
        if args.command == "export":
            Path(args.output).write_text(json.dumps(state, indent=2))
            print(args.output)
        else:
            print(json.dumps(state, indent=2))
    elif args.command == "review":
        decision = ReviewDecision(args.revision, args.decision == "approve", args.reviewer, args.gate)
        state = await handle.query(EngineeringWorkflow.status)
        if state.mode == "claude":
            from engineering.approval_auth import sign_decision
            key_path = os.environ.get("ENGINEERING_APPROVAL_PRIVATE_KEY")
            if not key_path:
                raise ValueError("Set ENGINEERING_APPROVAL_PRIVATE_KEY to your local signing key")
            decision = sign_decision(state, decision, key_path)
        print(await handle.execute_update(EngineeringWorkflow.review, decision))
    elif args.command == "change":
        print(await handle.execute_update(EngineeringWorkflow.change_requirement,
            RequirementChange(args.version, args.requirement, args.reason)))
    elif args.command == "clarify":
        print(await handle.execute_update(EngineeringWorkflow.clarify,
            Clarification(args.version, args.answer)))
    elif args.command == "stop":
        print(await handle.execute_update(EngineeringWorkflow.request_stop, args.reason))
    elif args.command == "result":
        print(json.dumps(await handle.result(), indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Controlled local engineering demo")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start")
    start.add_argument("--id", required=True)
    start.add_argument("--requirement", required=True)
    start.add_argument("--demo-failures", type=int, choices=range(4), default=0)
    start.add_argument("--question", default="")
    start.add_argument("--from-workflow", help="Copy a completed run into an isolated brownfield workspace")
    start.add_argument("--provider", choices=["demo", "claude"], default="demo")
    start.add_argument("--approval-timeout", type=int, default=86400)
    for command in ["status", "result", "review", "change", "clarify", "stop", "export"]:
        child = sub.add_parser(command)
        child.add_argument("--id", required=True)
        if command == "review":
            child.add_argument("--revision", type=int, required=True)
            child.add_argument("--reviewer", required=True)
            child.add_argument("--gate", choices=["apply", "review"], required=True)
            child.add_argument("--decision", choices=["approve", "reject"], required=True)
        elif command == "change":
            child.add_argument("--version", type=int, required=True)
            child.add_argument("--requirement", required=True)
            child.add_argument("--reason", required=True)
        elif command == "clarify":
            child.add_argument("--version", type=int, required=True)
            child.add_argument("--answer", required=True)
        elif command == "stop":
            child.add_argument("--reason", required=True)
        elif command == "export":
            child.add_argument("--output", required=True)
    metrics = sub.add_parser("metrics")
    metrics.add_argument("reports", nargs="+")
    asyncio.run(execute(parser.parse_args()))


if __name__ == "__main__":
    main()
