"""Confined demo workspace with immutable proposals and repeatable restoration.

The worker must own ARTIFACT_ROOT. Do not share its writable files with untrusted
processes. Path validation is defense in depth, not a filesystem sandbox.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from engineering.security import validate_text

MAX_BYTES = 100_000


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class Workspace:
    def __init__(self, root: Path, run_id: str):
        if not re.fullmatch(r"[a-f0-9]{64}", run_id):
            raise ValueError("Invalid workspace identity")
        # This root is operator configuration, never agent supplied.
        self.root = root.resolve() / run_id
        if self.root.is_symlink():
            raise ValueError("Symlink workspace is forbidden")
        self.root.mkdir(parents=True, exist_ok=True)
        self.directory = self.path("workspace")
        self.directory.mkdir(exist_ok=True)

    def path(self, relative: str) -> Path:
        path = Path(relative)
        if path.is_absolute() or not path.parts or any(x in {"..", "."} for x in path.parts):
            raise ValueError("Path escapes workspace")
        current = self.root
        for part in path.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Symlinks are forbidden")
        if not current.resolve().is_relative_to(self.root):
            raise ValueError("Path escapes workspace")
        return current

    def write(self, relative: str, content: bytes) -> None:
        if len(content) > MAX_BYTES:
            raise ValueError("Artifact exceeds policy limit")
        target = self.path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            name = stream.name
        try:
            os.replace(name, target)
        finally:
            Path(name).unlink(missing_ok=True)

    def read(self, relative: str) -> bytes:
        path = self.path(relative)
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("Artifact exceeds policy limit")
        return path.read_bytes()

    def snapshot(self, version: int) -> str:
        name = f"snapshots/{version}.json"
        if self.path(name).exists():
            return name  # Activity retry must not overwrite the baseline.
        files = {}
        for path in sorted(self.directory.rglob("*")):
            rel = path.relative_to(self.root).as_posix()
            self.path(rel)
            if path.is_file():
                files[path.relative_to(self.directory).as_posix()] = self.read(rel).decode()
        self.write(name, json.dumps(files, sort_keys=True).encode())
        return name

    def prepare(self, version: int, revision: int, requirement: str, attempt: int) -> tuple[str, str]:
        validate_text(requirement)
        name = f"proposals/{version}-{revision}.json"
        content = json.dumps({"mode": "demo", "requirement": requirement,
                              "version": version, "attempt": attempt}, sort_keys=True).encode()
        if self.path(name).exists() and self.read(name) != content:
            raise ValueError("Immutable proposal conflict")
        self.write(name, content)
        return name, digest(content)

    def apply(self, version: int, revision: int, expected_hash: str) -> str:
        content = self.read(f"proposals/{version}-{revision}.json")
        if digest(content) != expected_hash:
            raise ValueError("Approved artifact changed")
        self.write("workspace/change.json", content)
        return "workspace/change.json"

    def restore(self, version: int) -> None:
        files = json.loads(self.read(f"snapshots/{version}.json"))
        # Validate all paths before beginning a restoration.
        for rel, text in files.items():
            self.path("workspace/" + rel)
            if not isinstance(text, str):
                raise ValueError("Invalid snapshot")
        for path in sorted(self.directory.rglob("*")):
            rel = path.relative_to(self.root).as_posix()
            self.path(rel)
            if path.is_file() and path.relative_to(self.directory).as_posix() not in files:
                path.unlink()
        for rel, text in files.items():
            self.write("workspace/" + rel, text.encode())
            self.path("workspace/" + rel).chmod(0o644)


def run_allowed_check(command: str, content: str, timeout: float = 5) -> bool:
    """Only parse supplied Python syntax. Never execute supplied Python or shell."""
    if command != "python_syntax":
        raise ValueError("Command is not allowed")
    validate_text(content)
    result = subprocess.run(
        [sys.executable, "-I", "-c", "import ast,sys; ast.parse(sys.stdin.read())"],
        input=content, text=True, capture_output=True, timeout=min(timeout, 5),
        env={"PATH": os.defpath},
    )
    return result.returncode == 0
