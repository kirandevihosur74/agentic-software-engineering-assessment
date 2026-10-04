"""Run generated tests only in an explicitly provisioned local Docker image."""
import os
import shutil
import subprocess
import threading
import uuid
from engineering.models import CheckResult
from engineering.security import redact
from engineering.workspace import Workspace


def run_tests(store: Workspace) -> CheckResult:
    image = os.getenv('ENGINEERING_TEST_IMAGE')
    if not image or not shutil.which('docker'):
        return CheckResult('tests', False, 'VALIDATION_BLOCKED: configure ENGINEERING_TEST_IMAGE and start Docker')
    name = 'engineering-test-'+uuid.uuid4().hex
    command = ['docker', 'run', '--rm', '--name', name, '--pull=never',
               '--network=none', '--read-only', '--cap-drop=ALL',
               '--security-opt=no-new-privileges', '--pids-limit=128',
               '--memory=512m', '--cpus=1', '--user=65534:65534',
               '--tmpfs=/tmp:rw,nosuid,size=64m,mode=1777',
               '--mount', f'type=bind,source={store.directory},target=/workspace,readonly',
               '--workdir=/workspace', '--env=PYTHONDONTWRITEBYTECODE=1',
               '--env=PYTEST_DISABLE_PLUGIN_AUTOLOAD=1', '--entrypoint=python',
               image, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', 'tests']
    captured = bytearray()
    process = None
    reader = None
    def drain(stream):
        while chunk := stream.read(4096):
            if len(captured) < 8000:
                captured.extend(chunk[:8000-len(captured)])
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        reader = threading.Thread(target=drain, args=(process.stdout,), daemon=True)
        reader.start()
        process.wait(timeout=60)
        reader.join(timeout=2)
        detail = redact(captured.decode(errors='replace'))
        if process.returncode in {125, 126, 127}:
            return CheckResult('tests', False, 'VALIDATION_BLOCKED: Docker runner unavailable or misconfigured')
        return CheckResult('tests', process.returncode == 0, detail or 'No test output')
    except (OSError, subprocess.TimeoutExpired):
        if process is not None:
            process.kill()
            process.wait()
        return CheckResult('tests', False, 'VALIDATION_BLOCKED: Docker failed or test deadline exceeded')
    finally:
        try:
            subprocess.run(['docker','rm','-f',name], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if reader is not None:
            reader.join(timeout=2)
        if process is not None and process.stdout is not None:
            process.stdout.close()
