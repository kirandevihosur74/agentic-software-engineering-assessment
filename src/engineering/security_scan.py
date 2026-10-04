"""Static source and known dependency vulnerability checks; never import generated code."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from engineering.models import CheckResult
from engineering.workspace import Workspace


def run_security_scan(store: Workspace, version: int, revision: int) -> CheckResult:
    """Fail closed on missing tools, failed advisory lookup, or unscanned dependencies."""
    image = os.environ.get('ENGINEERING_TEST_IMAGE')
    if not image:
        return CheckResult('security', False, 'VALIDATION_BLOCKED: configure the audited test image')
    env = {'PATH': os.defpath, 'HOME': tempfile.gettempdir(), 'PYTHONNOUSERSITE': '1'}
    try:
        # Do not accept repository suppression directives or repository scanner config.
        source = subprocess.run([sys.executable, '-I', '-m', 'bandit', '-r',
            str(store.directory), '--ignore-nosec', '-f', 'json'],
            cwd=tempfile.gettempdir(), env=env, capture_output=True, text=True, timeout=45)
        if source.returncode not in (0, 1):
            raise ValueError('Source scanner unavailable')
        bandit = json.loads(source.stdout)
        if bandit.get('errors'):
            raise ValueError('Source scanner could not parse all files')
        findings = bandit.get('results', [])
        blocking = [f for f in findings if f.get('issue_severity') in ('MEDIUM', 'HIGH')]
        # The trusted, prebuilt image supplies the actual installed package inventory.
        inventory = subprocess.run(['docker', 'run', '--rm', '--pull=never', '--network=none',
            '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges',
            '--pids-limit=64', '--memory=256m', '--cpus=1', '--user=65534:65534',
            '--entrypoint=python', image, '-I', '-c',
            'import importlib.metadata as m; print("\\n".join(sorted(d.metadata["Name"]+"=="+d.version for d in m.distributions())))'],
            capture_output=True, text=True, timeout=30)
        if inventory.returncode:
            raise ValueError('Cannot inventory dependency image')
        packages = inventory.stdout.strip().splitlines()
        if not packages or any(not re.fullmatch(r'[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+', s) for s in packages):
            raise ValueError('Invalid dependency inventory')
        with tempfile.TemporaryDirectory(prefix='engineering-audit-') as temp:
            requirements = Path(temp)/'requirements.txt'
            requirements.write_text('\n'.join(packages)+'\n')
            audit = subprocess.run([sys.executable, '-I', '-m', 'pip_audit', '--disable-pip',
                '--no-deps', '-r', str(requirements), '--format', 'json', '--progress-spinner', 'off'],
                cwd=temp, env=env, capture_output=True, text=True, timeout=90)
        if audit.returncode not in (0, 1):
            raise ValueError('Dependency advisory lookup failed')
        dependencies = json.loads(audit.stdout)
        deps = dependencies.get('dependencies', [])
        if not deps or any('skip_reason' in d for d in deps):
            raise ValueError('Dependency audit incomplete')
        vulnerabilities = [dict(package=d['name'], version=d['version'], **v)
            for d in deps for v in d.get('vulns', [])]
        # Dependency files in generated proposals are not installed by the runner.
        # Report that scope explicitly rather than claiming they were audited.
        manifests = [str(p.relative_to(store.directory)) for p in store.directory.rglob('*')
            if p.is_file() and (p.name.startswith('requirements') or p.name in {'pyproject.toml', 'Pipfile', 'poetry.lock'})]
        report = {'bandit': bandit, 'dependency_audit': dependencies,
            'image': image, 'inventory': packages, 'unsupported_manifests': manifests,
            'policy': 'Block medium/high Bandit findings, all known dependency vulnerabilities, and unaudited manifests.'}
        name = f'security/{version}-{revision}.json'
        store.write(name, json.dumps(report, sort_keys=True).encode())
        detail = f'Bandit: {len(blocking)} medium/high findings ({len(findings)} total); dependency audit: {len(vulnerabilities)} known vulnerabilities in {len(deps)} packages. Report: {name}'
        if blocking:
            detail += '; ' + '; '.join(f"{f['test_id']} {Path(f['filename']).name}:{f['line_number']} {f['issue_text']}" for f in blocking)[:2000]
        if vulnerabilities:
            detail += '; ' + '; '.join(f"{v['package']} {v['id']}" for v in vulnerabilities)[:2000]
        if manifests:
            detail += '; unaudited dependency manifests: ' + ', '.join(manifests)
        return CheckResult('security', not (blocking or vulnerabilities or manifests), detail)
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        return CheckResult('security', False, 'VALIDATION_BLOCKED: security scan incomplete; check scanner installation, Docker, advisory access, and report limits')
