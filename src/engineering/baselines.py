"""Content-addressed source bundles for isolated brownfield workflow runs."""
import json
import re
from pathlib import Path
from engineering.proposals import current_files, validate_files
from engineering.workspace import Workspace, digest


def validate_hash(value: str) -> None:
    if value and not re.fullmatch(r'[a-f0-9]{64}', value):
        raise ValueError('Invalid baseline hash')


def bundle_baseline(root: Path, workspace_id: str, source_workflow: str) -> str:
    source = Workspace(root, workspace_id)
    files = current_files(source)
    if not files:
        raise ValueError('Source workspace is empty')
    validate_files({'summary':'Baseline', 'files':[{'path':p, 'content':c} for p,c in files.items()]})
    payload = json.dumps({'source_workflow':source_workflow, 'source_workspace':workspace_id,
                          'files':files}, sort_keys=True).encode()
    sha = digest(payload)
    # Dedicated storage namespace, inaccessible to generated file paths.
    catalog = Workspace(root, '0'*64)
    name = f'baselines/{sha}.json'
    if catalog.path(name).exists() and catalog.read(name) != payload:
        raise ValueError('Baseline content conflict')
    catalog.write(name, payload)
    return sha


def initialize_baseline(root: Path, target: Workspace, sha: str) -> None:
    validate_hash(sha)
    if not sha or target.path('snapshots/1.json').exists():
        return
    payload = Workspace(root, '0'*64).read(f'baselines/{sha}.json')
    if digest(payload) != sha:
        raise ValueError('Baseline integrity check failed')
    raw = json.loads(payload)
    files = validate_files({'summary':'Baseline', 'files':[{'path':p,'content':c} for p,c in raw['files'].items()]})
    # Repeated initialization is safe until the first snapshot is committed.
    for name in files:
        target.path('workspace/'+name)
    for name, content in files.items():
        target.write('workspace/'+name, content.encode())
        target.path('workspace/'+name).chmod(0o644)
    target.write('baseline.json', payload)
