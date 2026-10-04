import json
import subprocess
import pytest
from engineering.workspace import Workspace
from engineering.security_scan import run_security_scan


@pytest.mark.parametrize('vulnerable,expected', [(True, False), (False, True)])
def test_real_bandit_blocks_unsafe_source_without_executing_it(tmp_path, monkeypatch, vulnerable, expected):
    import engineering.security_scan as module
    real_run = subprocess.run
    store=Workspace(tmp_path, 'e'*64)
    store.write('workspace/app.py', b'def f(value):\n    return eval(value)\n' if vulnerable else b'def f(value):\n    return value + 1\n')
    monkeypatch.setenv('ENGINEERING_TEST_IMAGE','test-image')
    def run(cmd, **kw):
        if cmd[0]=='docker':return subprocess.CompletedProcess(cmd,0,'fastapi==0.142.2\n','')
        if 'pip_audit' in cmd:return subprocess.CompletedProcess(cmd,0,json.dumps({'dependencies':[{'name':'fastapi','version':'0.142.2','vulns':[]}]}),'')
        return real_run(cmd, **kw)
    monkeypatch.setattr(module.subprocess,'run',run)
    result=run_security_scan(store,1,1)
    assert result.passed == expected
    if vulnerable:assert 'B307' in result.detail


@pytest.mark.parametrize('case', ['advisory_failure','known_vulnerability','skipped_package','manifest'])
def test_scan_fails_closed_on_vulnerabilities_and_incomplete_coverage(tmp_path, monkeypatch, case):
    import engineering.security_scan as module
    store=Workspace(tmp_path, 'e'*64)
    store.write('workspace/app.py',b'x = 1\n')
    if case=='manifest':store.write('workspace/requirements.txt',b'unknown==1\n')
    monkeypatch.setenv('ENGINEERING_TEST_IMAGE','test-image')
    def run(cmd, **kw):
        if 'bandit' in cmd:return subprocess.CompletedProcess(cmd,0,'{"results":[],"errors":[]}', '')
        if cmd[0]=='docker':return subprocess.CompletedProcess(cmd,0,'example==1\n','')
        if case=='advisory_failure':raise subprocess.TimeoutExpired(cmd,90)
        dep={'name':'example','version':'1','vulns':[]}
        if case=='known_vulnerability':dep['vulns']=[{'id':'TEST-1'}]
        if case=='skipped_package':dep['skip_reason']='not available'
        return subprocess.CompletedProcess(cmd,0,json.dumps({'dependencies':[dep]}),'')
    monkeypatch.setattr(module.subprocess,'run',run)
    assert not run_security_scan(store,1,1).passed
