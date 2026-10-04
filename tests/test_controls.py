import subprocess
from pathlib import Path
import pytest
from engineering.workspace import Workspace, digest, run_allowed_check
from engineering.security import redact, validate_text
from engineering.metrics import aggregate


def test_workspace_rejects_traversal_symlinks_and_modified_approval(tmp_path):
    store = Workspace(tmp_path, 'a' * 64)
    for path in ['../outside', '/tmp/outside']:
        with pytest.raises(ValueError):
            store.write(path, b'bad')
    store.path('escape').symlink_to(tmp_path)
    with pytest.raises(ValueError):
        store.write('escape/nope', b'bad')
    proposal, sha = store.prepare(1, 1, 'shortener', 0)
    store.write(proposal, b'changed after approval')
    with pytest.raises(ValueError, match='Approved artifact changed'):
        store.apply(1, 1, sha)
    assert not store.path('workspace/change.json').exists()


def test_snapshot_survives_retries_and_rollback_restores_real_files(tmp_path):
    store = Workspace(tmp_path, 'b' * 64)
    store.write('workspace/existing.py', b'print("baseline")')
    store.snapshot(1)
    store.write('workspace/existing.py', b'print("modified")')
    store.write('workspace/new.py', b'new = True')
    store.snapshot(1)
    store.restore(1)
    store.restore(1)
    assert store.read('workspace/existing.py') == b'print("baseline")'
    assert not store.path('workspace/new.py').exists()


def test_command_policy_parses_but_never_executes_input(tmp_path):
    marker = tmp_path / 'must-not-exist'
    assert run_allowed_check('python_syntax', f'open({str(marker)!r}, "w").write("bad")')
    assert not marker.exists()
    assert not run_allowed_check('python_syntax', 'invalid syntax !')
    with pytest.raises(ValueError, match='not allowed'):
        run_allowed_check('sh', 'echo bad')
    with pytest.raises(subprocess.TimeoutExpired):
        run_allowed_check('python_syntax', 'x = 1', timeout=0.000001)


def test_redaction_and_rejection():
    assert 'abc123' not in redact('api_key=abc123')
    with pytest.raises(ValueError, match='credentials'):
        validate_text('password=abc123')


def test_metric_denominators_and_missing_recoveries():
    empty = aggregate([])
    assert empty['success_rate'] is None
    assert empty['mean_recovery_seconds'] is None
    base = dict(recoveries=0, recovery_seconds=0, activity_retries=0, rollbacks=0, elapsed_seconds=10)
    stats = aggregate([{'stage': 'completed', 'metrics': base},
                       {'stage': 'stopped', 'metrics': dict(base, rollbacks=1)}])
    assert stats['success_rate'] == .5
    assert stats['rollback_run_frequency'] == .5
