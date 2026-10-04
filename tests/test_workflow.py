"""Integration tests use real Temporal histories and isolated real artifact files."""
import asyncio
import os
from pathlib import Path
import uuid
import pytest
from temporalio.client import Client, WorkflowUpdateFailedError
from temporalio.worker import Worker
from engineering.activities import ACTIVITIES
from engineering.models import Clarification, RequirementChange, ReviewDecision, RunRequest
from engineering.workflow import EngineeringWorkflow
from engineering.workspace import Workspace

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    not os.getenv('TEMPORAL_TEST_ADDRESS'), reason='Set TEMPORAL_TEST_ADDRESS for integration tests')]


@pytest.fixture
def artifact_root(tmp_path, monkeypatch):
    monkeypatch.setenv('ARTIFACT_ROOT', str(tmp_path))
    return tmp_path


async def wait_stage(handle, *stages):
    async with asyncio.timeout(20):
        while True:
            state = await handle.query(EngineeringWorkflow.status)
            if state.stage in stages:
                return state
            await asyncio.sleep(.02)


async def decide(handle, state, approve=True):
    gate = 'apply' if state.stage == 'awaiting_apply' else 'review'
    decision = ReviewDecision(state.revision, approve, 'test', gate)
    if state.mode == 'claude':
        from engineering.approval_auth import sign_decision
        decision = sign_decision(state, decision, os.environ['ENGINEERING_APPROVAL_PRIVATE_KEY'])
    await handle.execute_update(EngineeringWorkflow.review, decision)


async def finish(handle, approve=True):
    async with asyncio.timeout(30):
        while True:
            state = await wait_stage(handle, 'awaiting_apply', 'awaiting_review', 'stopped', 'needs_intervention', 'completed')
            if state.stage in {'stopped', 'needs_intervention', 'completed'}:
                return await handle.result()
            await decide(handle, state, approve if state.stage == 'awaiting_review' else True)
            # Avoid observing the same gate while its Update completion is delivered.
            old = (state.stage, state.revision)
            while True:
                state = await handle.query(EngineeringWorkflow.status)
                if (state.stage, state.revision) != old:
                    break
                await asyncio.sleep(.02)


@pytest.mark.parametrize('failures,approved,expected', [(0,True,'completed'), (1,True,'completed'), (0,False,'stopped'), (3,True,'stopped')])
async def test_lifecycle(failures, approved, expected, artifact_root):
    client = await Client.connect(os.environ['TEMPORAL_TEST_ADDRESS'])
    queue = str(uuid.uuid4())
    async with Worker(client, task_queue=queue, workflows=[EngineeringWorkflow], activities=ACTIVITIES):
        handle = await client.start_workflow(EngineeringWorkflow.run,
            RunRequest('Build a shortener', demo_failures=failures), id=queue, task_queue=queue)
        state = await wait_stage(handle, 'awaiting_apply')
        store = Workspace(artifact_root, state.workspace_id)
        assert not store.path('workspace/change.json').exists()  # No write before approval.
        with pytest.raises(WorkflowUpdateFailedError):
            await handle.execute_update(EngineeringWorkflow.review, ReviewDecision(state.revision - 1, True, 'test', 'apply'))
        result = await finish(handle, approved)
        assert result.stage == expected
        assert result.repairs == min(failures, 2)
        assert result.metrics.elapsed_seconds > 0
        assert store.path('workspace/change.json').exists() == (expected == 'completed')
        if expected == 'stopped':
            assert result.metrics.rollbacks == 1


async def test_clarification_replanning_and_worker_restart(artifact_root):
    client = await Client.connect(os.environ['TEMPORAL_TEST_ADDRESS'])
    queue = str(uuid.uuid4())
    async with Worker(client, task_queue=queue, workflows=[EngineeringWorkflow], activities=ACTIVITIES):
        handle = await client.start_workflow(EngineeringWorkflow.run,
            RunRequest('Privacy friendly analytics', clarification_question='What data may be stored?'), id=queue, task_queue=queue)
        await wait_stage(handle, 'awaiting_clarification')
        await handle.execute_update(EngineeringWorkflow.clarify, Clarification(1, 'Only aggregate click counts'))
        state = await wait_stage(handle, 'awaiting_apply')
        await decide(handle, state)
        state = await wait_stage(handle, 'awaiting_review')
        old_revision = state.revision
        await handle.execute_update(EngineeringWorkflow.change_requirement,
            RequirementChange(1, 'Add expiration with aggregate analytics', 'Scope updated'))
        state = await wait_stage(handle, 'awaiting_apply')
        assert state.requirement_version == 2
        assert state.metrics.rollbacks == 1
        assert state.metrics.replans == 1
        assert not Workspace(artifact_root, state.workspace_id).path('workspace/change.json').exists()
        with pytest.raises(WorkflowUpdateFailedError):
            await handle.execute_update(EngineeringWorkflow.review, ReviewDecision(old_revision, True, 'test', 'apply'))
        revision = state.revision
    # A fresh Worker replays the same history and resumes the approval wait.
    async with Worker(client, task_queue=queue, workflows=[EngineeringWorkflow], activities=ACTIVITIES):
        state = await wait_stage(handle, 'awaiting_apply')
        assert state.revision == revision
        result = await finish(handle)
        assert result.stage == 'completed'
        assert result.metrics.replans == 1
        assert result.metrics.activity_calls == 15
        assert b'Add expiration' in Workspace(artifact_root, state.workspace_id).read('workspace/change.json')


async def test_approval_timeout_and_explicit_stop(artifact_root):
    client = await Client.connect(os.environ['TEMPORAL_TEST_ADDRESS'])
    queue = str(uuid.uuid4())
    async with Worker(client, task_queue=queue, workflows=[EngineeringWorkflow], activities=ACTIVITIES):
        handle = await client.start_workflow(EngineeringWorkflow.run,
            RunRequest('Build', approval_timeout_seconds=1), id=queue, task_queue=queue)
        result = await asyncio.wait_for(handle.result(), 20)
        assert result.stage == 'stopped'
        assert 'timed out' in result.summary
        handle = await client.start_workflow(EngineeringWorkflow.run, RunRequest('Build'), id=queue+'-stop', task_queue=queue)
        state = await wait_stage(handle, 'awaiting_apply')
        await decide(handle, state)
        await wait_stage(handle, 'awaiting_review')
        await handle.execute_update(EngineeringWorkflow.request_stop, 'User requested stop')
        result = await asyncio.wait_for(handle.result(), 20)
        assert result.stage == 'stopped'
        assert result.metrics.rollbacks == 1


async def test_rollback_failure_requires_intervention(artifact_root):
    client = await Client.connect(os.environ['TEMPORAL_TEST_ADDRESS'])
    queue = str(uuid.uuid4())
    async with Worker(client, task_queue=queue, workflows=[EngineeringWorkflow], activities=ACTIVITIES):
        handle = await client.start_workflow(EngineeringWorkflow.run, RunRequest('Build'), id=queue, task_queue=queue)
        state = await wait_stage(handle, 'awaiting_apply')
        await decide(handle, state)
        state = await wait_stage(handle, 'awaiting_review')
        store = Workspace(artifact_root, state.workspace_id)
        store.path('snapshots/1.json').unlink()  # Deliberate failure injection.
        await decide(handle, state, False)
        result = await asyncio.wait_for(handle.result(), 20)
        assert result.stage == 'needs_intervention'
        assert result.metrics.rollback_failures == 1
        assert store.path('workspace/change.json').exists()


async def test_transient_retry_and_change_during_parallel_checks(artifact_root):
    from temporalio import activity
    from temporalio.exceptions import ApplicationError
    from engineering.activities import engineering_step
    from engineering.models import ActivityRequest, ActivityResult

    checking = asyncio.Event()
    release = asyncio.Event()

    @activity.defn(name='engineering_step')
    async def controlled_step(request: ActivityRequest) -> ActivityResult:
        if request.operation == 'tests' and request.data.version == 1:
            if activity.info().attempt == 1:
                raise ApplicationError('Injected transient failure')
            checking.set()
            await release.wait()
        return await engineering_step(request)

    client = await Client.connect(os.environ['TEMPORAL_TEST_ADDRESS'])
    queue = str(uuid.uuid4())
    async with Worker(client, task_queue=queue, workflows=[EngineeringWorkflow], activities=[controlled_step]):
        handle = await client.start_workflow(EngineeringWorkflow.run, RunRequest('Original'), id=queue, task_queue=queue)
        state = await wait_stage(handle, 'awaiting_apply')
        await decide(handle, state)
        await asyncio.wait_for(checking.wait(), 10)
        await handle.execute_update(EngineeringWorkflow.change_requirement,
            RequirementChange(1, 'Revised', 'Change while check is running'))
        release.set()
        state = await wait_stage(handle, 'awaiting_apply')
        assert state.requirement_version == 2
        assert state.metrics.activity_retries == 1
        assert state.metrics.rollbacks == 1
        assert state.checks == []
        result = await finish(handle)
        assert result.stage == 'completed'


@pytest.mark.parametrize('runner_ready', [True, False])
async def test_claude_provider_flow_with_stubbed_sdk(artifact_root, monkeypatch, runner_ready, signing):
    from engineering.claude_agent import ClaudeAgent, AgentOutput
    from engineering.models import CheckResult
    from engineering import claude_steps
    async def generate(self, stage, context, schema):
        if stage == 'understand':
            output = {'summary':'understood','acceptance_criteria':['sum'],'questions':[]}
        elif stage == 'plan':
            output = {'summary':'planned','tasks':['add'],'risks':[]}
        else:
            output = {'summary':'implemented','files':[{'path':'app.py','content':'def add(a, b):\n    return a + b\n'}]}
        return AgentOutput(output,'stub-session','stub',0,{})
    monkeypatch.setattr(ClaudeAgent, 'generate', generate)
    monkeypatch.setattr(claude_steps, 'run_security_scan', lambda *a: CheckResult('security', True, 'Stubbed security success'))
    monkeypatch.setattr(claude_steps, 'run_tests', lambda store: CheckResult('tests', runner_ready,
        'Stubbed test success' if runner_ready else 'VALIDATION_BLOCKED: test runner unavailable'))
    client = await Client.connect(os.environ['TEMPORAL_TEST_ADDRESS'])
    queue = str(uuid.uuid4())
    async with Worker(client, task_queue=queue, workflows=[EngineeringWorkflow], activities=ACTIVITIES):
        handle = await client.start_workflow(EngineeringWorkflow.run, RunRequest('Add numbers', provider='claude'),
                                            id=queue, task_queue=queue)
        state = await wait_stage(handle, 'awaiting_apply')
        with pytest.raises(WorkflowUpdateFailedError):
            await handle.execute_update(EngineeringWorkflow.review, ReviewDecision(state.revision, True, 'test', 'apply'))
        with pytest.raises(WorkflowUpdateFailedError):
            await handle.execute_update(EngineeringWorkflow.review, ReviewDecision(state.revision, True, 'test', 'apply', 'bad-signature', 1))
        result = await finish(handle)
        assert any(a.kind == 'approval_authenticated' for a in result.audit)
        assert result.mode == 'claude'
        assert result.stage == ('completed' if runner_ready else 'stopped')
        assert result.repairs == 0
        store = Workspace(artifact_root, result.workspace_id)
        assert store.path('workspace/app.py').exists() == runner_ready


async def test_brownfield_baseline_preserved_through_replan_and_rejection(artifact_root):
    from engineering.baselines import bundle_baseline
    source = Workspace(artifact_root, 'f'*64)
    source.write('workspace/app.py', b'original = True\n')
    sha = bundle_baseline(artifact_root, 'f'*64, 'source')
    client = await Client.connect(os.environ['TEMPORAL_TEST_ADDRESS'])
    queue = str(uuid.uuid4())
    async with Worker(client, task_queue=queue, workflows=[EngineeringWorkflow], activities=ACTIVITIES):
        handle = await client.start_workflow(EngineeringWorkflow.run,
            RunRequest('Extend existing code', baseline_hash=sha), id=queue, task_queue=queue)
        state = await wait_stage(handle, 'awaiting_apply')
        target = Workspace(artifact_root, state.workspace_id)
        assert target.read('workspace/app.py') == source.read('workspace/app.py')
        assert state.baseline_hash == sha
        await decide(handle, state)
        await wait_stage(handle, 'awaiting_review')
        await handle.execute_update(EngineeringWorkflow.change_requirement,
            RequirementChange(1, 'Change extension behavior', 'Test replanning'))
        state = await wait_stage(handle, 'awaiting_apply')
        assert state.requirement_version == 2
        assert target.read('workspace/app.py') == source.read('workspace/app.py')
        assert not target.path('workspace/change.json').exists()
        assert target.path('workspace/app.py').stat().st_mode & 0o444 == 0o444
        await decide(handle, state, False)
        result = await handle.result()
        assert result.stage == 'stopped'
        assert source.read('workspace/app.py') == b'original = True\n'
