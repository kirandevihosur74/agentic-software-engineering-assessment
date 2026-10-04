import asyncio
from dataclasses import asdict
import hashlib
import json
from engineering.claude_agent import ClaudeAgent, Analysis, Design, Proposal
from engineering.models import ActivityRequest, ActivityResult, CheckResult
from engineering.proposals import current_files, save_proposal, apply_proposal, static_check
from engineering.test_runner import run_tests
from engineering.security_scan import run_security_scan
from engineering.workspace import Workspace, digest


async def execute_claude(request: ActivityRequest, store: Workspace) -> ActivityResult:
    data = request.data
    op = request.operation
    result = ActivityResult()
    if op in {'understand', 'plan', 'prepare'}:
        context = {'requirement': data.requirement, 'files': current_files(store),
                   'attempt': data.attempt, 'requirement_version': data.version}
        for name in ['understand', 'plan', 'tests', 'security']:
            if name == op or (op == 'understand'):
                continue
            path = f'context/{data.version}-{name}.json'
            if store.path(path).exists():
                context[name] = json.loads(store.read(path))
        if op == 'prepare':
            proposal_name = f'proposals/{data.version}-{data.revision}.json'
            if store.path(proposal_name).exists():
                content = store.read(proposal_name)
                result.artifact, result.digest = proposal_name, digest(content)
                result.detail = 'Reused persisted proposal'
                return result
        schema = {'understand': Analysis, 'plan': Design, 'prepare': Proposal}[op]
        cache_key = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
        receipt_name = f'claude/{op}-{cache_key}.json'
        if store.path(receipt_name).exists():
            receipt = json.loads(store.read(receipt_name))
        else:
            try:
                output = await ClaudeAgent().generate(op, context, schema)
            except Exception as exc:
                raise ValueError(f"Claude request failed ({type(exc).__name__}); check provider configuration and access") from None
            receipt = asdict(output)
            store.write(receipt_name, json.dumps(receipt, sort_keys=True).encode())
        validated = schema.model_validate(receipt['output']).model_dump()
        store.write(f'context/{data.version}-{op}.json', json.dumps(validated).encode())
        result.detail = validated['summary']
        result.artifact = receipt_name
        if op == 'understand':
            result.questions = validated['questions']
        if op == 'prepare':
            result.artifact, result.digest = save_proposal(store, data.version, data.revision, validated)
    elif op == 'apply':
        result.artifact = apply_proposal(store, data.version, data.revision, request.expected_hash)
        result.detail = 'Approved Claude file changes applied'
    elif op in {'tests', 'security'}:
        if op == 'tests':
            result.check = await asyncio.to_thread(run_tests, store)
        else:
            passed, detail = static_check(store, data.version, data.revision, request.expected_hash)
            result.check = await asyncio.to_thread(run_security_scan, store, data.version, data.revision) if passed else CheckResult('security', False, detail)
        store.write(f'context/{data.version}-{op}.json', json.dumps(asdict(result.check)).encode())
        result.detail = result.check.detail
    else:
        raise ValueError('Unsupported Claude operation')
    return result
