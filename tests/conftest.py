from dataclasses import replace
import base64
import json
import time
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from engineering.approval_auth import sign_decision, verify_approval
from engineering.models import ApprovalVerification, ReviewDecision, RunState


@pytest.fixture
def signing(tmp_path, monkeypatch):
    key = Ed25519PrivateKey.generate()
    private = tmp_path/'reviewer.pem'
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    private.chmod(0o600)
    trusted = tmp_path/'trusted.json'
    trusted.write_text(json.dumps({'test': {'public_key': base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode(), 'gates': ['apply','review']}}))
    monkeypatch.setenv('ENGINEERING_APPROVAL_KEYS', str(trusted))
    monkeypatch.setenv('ENGINEERING_APPROVAL_PRIVATE_KEY', str(private))
    state = RunState(workspace_id='a'*64, requirement_version=2, revision=3, candidate_hash='b'*64)
    return state, private

