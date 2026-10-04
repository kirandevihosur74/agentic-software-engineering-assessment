from dataclasses import replace
import base64
import json
import time
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from engineering.approval_auth import sign_decision, verify_approval
from engineering.models import ApprovalVerification, ReviewDecision, RunState




def test_verified_signature_and_private_key_permissions(signing):
    state, private = signing
    decision = sign_decision(state, ReviewDecision(3, True, 'test', 'apply'), str(private))
    request = ApprovalVerification(state.workspace_id, 2, state.candidate_hash, decision)
    assert verify_approval(request) == 'test'
    private.chmod(0o644)
    with pytest.raises(ValueError, match='0600'):
        sign_decision(state, decision, str(private))


@pytest.mark.parametrize('field,value', [('revision',4),('approved',False),('gate','review'),('reviewer','other'),('expires_at',1),('signature','invalid')])
def test_signature_rejects_tampering(signing, field, value):
    state, private = signing
    decision = sign_decision(state, ReviewDecision(3, True, 'test', 'apply'), str(private))
    with pytest.raises(Exception):
        verify_approval(ApprovalVerification(state.workspace_id,2,state.candidate_hash,replace(decision, **{field:value})))


@pytest.mark.parametrize('field,value', [('workspace_id','c'*64),('version',3),('candidate_hash','d'*64)])
def test_signature_cannot_replay_across_run_version_or_proposal(signing, field, value):
    state, private = signing
    decision=sign_decision(state,ReviewDecision(3,True,'test','apply'),str(private))
    with pytest.raises(Exception):
        verify_approval(replace(ApprovalVerification(state.workspace_id,2,state.candidate_hash,decision), **{field:value}))


def test_missing_trust_and_unauthorized_gate_fail_closed(signing, monkeypatch):
    state, private=signing
    decision=sign_decision(state,ReviewDecision(3,True,'test','apply'),str(private))
    request=ApprovalVerification(state.workspace_id,2,state.candidate_hash,decision)
    from pathlib import Path
    import os
    path=Path(os.environ['ENGINEERING_APPROVAL_KEYS']); config=json.loads(path.read_text());config['test']['gates']=['review'];path.write_text(json.dumps(config))
    with pytest.raises(ValueError):verify_approval(request)
    monkeypatch.delenv('ENGINEERING_APPROVAL_KEYS')
    with pytest.raises(ValueError):verify_approval(request)
