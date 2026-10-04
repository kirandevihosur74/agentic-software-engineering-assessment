"""Validate Claude file proposals before writing or applying any changes."""
import ast
import json
from pathlib import PurePosixPath
from engineering.claude_agent import Proposal
from engineering.security import validate_text
from engineering.workspace import Workspace, digest


def validate_files(raw: dict) -> dict[str, str]:
    proposal = Proposal.model_validate(raw)
    files = {}
    for change in proposal.files:
        name = change.path
        path = PurePosixPath(name)
        if (not name or path.is_absolute() or str(path) != name or '\\' in name
            or any(part.startswith('.') for part in path.parts)
            or path.suffix not in {'.py', '.md', '.toml', '.txt', '.json'}):
            raise ValueError('Proposal contains a forbidden path')
        if name in files:
            raise ValueError('Duplicate proposal path')
        validate_text(change.content)
        files[name] = change.content
    if len(json.dumps(files).encode()) > 70_000:
        raise ValueError('Proposal exceeds total size limit')
    return files


def current_files(store: Workspace) -> dict[str, str]:
    files = {}
    for path in sorted(store.directory.rglob('*')):
        relative = path.relative_to(store.directory).as_posix()
        store.path('workspace/'+relative)
        if path.is_file():
            files[relative] = store.read('workspace/'+relative).decode()
    return files


def save_proposal(store: Workspace, version: int, revision: int, output: dict) -> tuple[str, str]:
    validate_files(output)
    name = f'proposals/{version}-{revision}.json'
    content = json.dumps(output, sort_keys=True).encode()
    if store.path(name).exists() and store.read(name) != content:
        raise ValueError('Immutable proposal conflict')
    store.write(name, content)
    return name, digest(content)


def apply_proposal(store: Workspace, version: int, revision: int, approved_hash: str) -> str:
    content = store.read(f'proposals/{version}-{revision}.json')
    if digest(content) != approved_hash:
        raise ValueError('Approved artifact changed')
    files = validate_files(json.loads(content))
    for name in files:
        store.path('workspace/'+name)
    for name, text in files.items():
        store.write('workspace/'+name, text.encode())
        store.path('workspace/'+name).chmod(0o644)
    return 'workspace'


def static_check(store: Workspace, version: int, revision: int, approved_hash: str) -> tuple[bool, str]:
    content = store.read(f'proposals/{version}-{revision}.json')
    if digest(content) != approved_hash:
        return False, 'Approved proposal integrity failed'
    for name, text in validate_files(json.loads(content)).items():
        if store.read('workspace/'+name).decode() != text:
            return False, 'Applied files differ from approved proposal'
        if name.endswith('.py'):
            try:
                ast.parse(text)
            except SyntaxError as exc:
                return False, f'Syntax error in {name} at line {exc.lineno}'
    return True, 'Approved file integrity and Python syntax passed'
