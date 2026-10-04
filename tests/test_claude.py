import json
import pytest
from claude_agent_sdk import ResultMessage
from engineering.claude_agent import ClaudeAgent, Analysis, AgentOutput
from engineering.claude_steps import execute_claude
from engineering.models import ActivityRequest, StageInput
from engineering.proposals import validate_files, save_proposal, apply_proposal, static_check
from engineering.workspace import Workspace
from engineering.test_runner import run_tests


def message(**kwargs):
    fields = dict(subtype='success', duration_ms=1, duration_api_ms=1, is_error=False,
                  num_turns=1, session_id='test-session', total_cost_usd=.001,
                  structured_output={'summary':'Add numbers', 'acceptance_criteria':['sum'], 'questions':[]})
    fields.update(kwargs)
    return ResultMessage(**fields)


async def test_sdk_options_and_structured_result(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-key')
    async def fake_query(*, prompt, options):
        assert options.tools == []
        assert options.setting_sources == []
        assert options.strict_mcp_config
        assert options.permission_mode == 'dontAsk'
        assert options.max_budget_usd <= 5
        assert 'test-key' not in prompt
        assert options.output_format['type'] == 'json_schema'
        yield message(terminal_reason="completed")
    result = await ClaudeAgent(fake_query).generate('understand', {'requirement':'Add numbers'}, Analysis)
    assert result.output['summary'] == 'Add numbers'
    assert result.cost_usd == .001


@pytest.mark.parametrize('result', [message(is_error=True), message(subtype='error_max_budget_usd'),
    message(terminal_reason='api_error'), message(structured_output={'unexpected':True})])
async def test_sdk_rejects_failure_and_invalid_schema(monkeypatch, result):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-key')
    async def fake_query(**kwargs):
        yield result
    with pytest.raises(ValueError):
        await ClaudeAgent(fake_query).generate('understand', {}, Analysis)


async def test_missing_key_fails_before_query(monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    with pytest.raises(ValueError, match='ANTHROPIC_API_KEY'):
        await ClaudeAgent().generate('understand', {}, Analysis)


@pytest.mark.parametrize('path', ['../bad.py', '/tmp/bad.py', '.env', 'a/../../bad.py', 'run.sh', 'a//b.py'])
def test_forbidden_proposal_paths(path):
    with pytest.raises(ValueError):
        validate_files({'summary':'bad', 'files':[{'path':path,'content':'x = 1'}]})


def test_proposal_application_and_real_static_checks(tmp_path):
    store=Workspace(tmp_path,'c'*64)
    store.snapshot(1)
    proposal={'summary':'Add code','files':[{'path':'app.py','content':'x = 1\n'}]}
    _, sha=save_proposal(store,1,1,proposal)
    assert not store.path('workspace/app.py').exists()
    apply_proposal(store,1,1,sha)
    assert static_check(store,1,1,sha)[0]
    store.write('workspace/app.py',b'x=2')
    assert not static_check(store,1,1,sha)[0]
    store.restore(1)
    assert not store.path('workspace/app.py').exists()


async def test_stage_context_and_cached_proposal(monkeypatch,tmp_path):
    calls=[]
    async def fake_generate(self,stage,context,schema):
        calls.append(stage)
        if stage=='understand':
            output={'summary':'Requirement','acceptance_criteria':['sum'],'questions':[]}
        elif stage=='plan':
            assert context['understand']['acceptance_criteria']==['sum']
            output={'summary':'Design','tasks':['Implement sum'],'risks':[]}
        else:
            assert context['plan']['tasks']==['Implement sum']
            assert context['tests']['detail']=='Previous failure evidence'
            output={'summary':'Fix','files':[{'path':'app.py','content':'x = 1'}]}
        return AgentOutput(output,'test','test',.001,{})
    monkeypatch.setattr(ClaudeAgent,'generate',fake_generate)
    store=Workspace(tmp_path,'d'*64)
    data=StageInput('Build',workspace_id='d'*64,provider='claude')
    for stage in ['understand','plan']:
        await execute_claude(ActivityRequest(stage,data),store)
    store.write('context/1-tests.json',json.dumps({'detail':'Previous failure evidence'}).encode())
    first=await execute_claude(ActivityRequest('prepare',data),store)
    second=await execute_claude(ActivityRequest('prepare',data),store)
    assert first.digest==second.digest
    assert calls==['understand','plan','prepare']


def test_test_runner_fails_closed_without_image(monkeypatch,tmp_path):
    monkeypatch.delenv('ENGINEERING_TEST_IMAGE',raising=False)
    result=run_tests(Workspace(tmp_path,'e'*64))
    assert not result.passed
    assert result.detail.startswith('VALIDATION_BLOCKED:')
