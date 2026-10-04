import json
import pytest
from engineering.baselines import bundle_baseline, initialize_baseline
from engineering.workspace import Workspace


def test_baseline_copy_is_immutable_isolated_and_retry_safe(tmp_path):
    source = Workspace(tmp_path,'a'*64)
    source.write('workspace/app.py', b'x=1')
    sha = bundle_baseline(tmp_path,'a'*64,'completed-source')
    source.write('workspace/app.py', b'x=2')
    target = Workspace(tmp_path,'b'*64)
    initialize_baseline(tmp_path,target,sha)
    assert target.read('workspace/app.py') == b'x=1'
    initialize_baseline(tmp_path,target,sha)
    target.snapshot(1)
    target.write('workspace/app.py',b'x=3')
    initialize_baseline(tmp_path,target,sha)
    assert target.read('workspace/app.py') == b'x=3'
    target.restore(1)
    assert target.read('workspace/app.py') == b'x=1'
    assert source.read('workspace/app.py') == b'x=2'


def test_changed_baseline_is_rejected_before_writes(tmp_path):
    source = Workspace(tmp_path,'a'*64)
    source.write('workspace/app.py', b'x=1')
    sha = bundle_baseline(tmp_path,'a'*64,'source')
    Workspace(tmp_path,'0'*64).write(f'baselines/{sha}.json',b'{}')
    target = Workspace(tmp_path,'b'*64)
    with pytest.raises(ValueError,match='integrity'):
        initialize_baseline(tmp_path,target,sha)
    assert list(target.directory.iterdir()) == []
