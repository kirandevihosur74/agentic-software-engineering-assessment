"""Ed25519 approval signatures. Private keys never enter Temporal payloads."""
import base64
import json
import os
from pathlib import Path
import time
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from temporalio import activity
from temporalio.exceptions import ApplicationError
from engineering.models import ApprovalVerification, ReviewDecision


def approval_payload(workspace_id: str, version: int, candidate_hash: str, decision: ReviewDecision) -> bytes:
    return json.dumps({'purpose': 'engineering-approval-v1', 'workspace_id': workspace_id,
        'version': version, 'candidate_hash': candidate_hash, 'revision': decision.revision,
        'gate': decision.gate, 'approved': decision.approved, 'reviewer': decision.reviewer,
        'expires_at': decision.expires_at}, sort_keys=True, separators=(',', ':')).encode()


def sign_decision(state, decision: ReviewDecision, key_path: str) -> ReviewDecision:
    path = Path(key_path)
    if path.stat().st_mode & 0o077:
        raise ValueError('Approval private key must have permissions 0600')
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('Expected an Ed25519 private key')
    decision.expires_at = int(time.time()) + 300
    decision.signature = base64.b64encode(key.sign(approval_payload(
        state.workspace_id, state.requirement_version, state.candidate_hash, decision))).decode()
    return decision


def verify_approval(request: ApprovalVerification) -> str:
    decision = request.decision
    if not int(time.time()) <= decision.expires_at <= int(time.time()) + 600:
        raise ValueError('Approval expired or expiry is too far in the future')
    config = os.environ.get('ENGINEERING_APPROVAL_KEYS')
    if not config:
        raise ValueError('Trusted approval keys are not configured')
    keys = json.loads(Path(config).read_text())
    entry = keys.get(decision.reviewer)
    if not entry or decision.gate not in entry.get('gates', []):
        raise ValueError('Reviewer is not authorized for this gate')
    key = Ed25519PublicKey.from_public_bytes(base64.b64decode(entry['public_key'], validate=True))
    key.verify(base64.b64decode(decision.signature, validate=True), approval_payload(
        request.workspace_id, request.version, request.candidate_hash, decision))
    return decision.reviewer


@activity.defn
async def authenticate_approval(request: ApprovalVerification) -> str:
    try:
        return verify_approval(request)
    except Exception:
        raise ApplicationError('Approval authentication failed', non_retryable=True) from None
