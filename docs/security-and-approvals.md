# Security scanning and authenticated approvals

## Approval authentication

New Claude workflows require an Ed25519 signature at both approval gates. The CLI signs the decision locally; the worker verifies it against an operator-managed reviewer allowlist. The private key is never sent to Temporal. The public signature can be retained in workflow history.

The signed payload binds the reviewer, approve/reject decision, gate, revision, requirement version, candidate hash, run-specific workspace identity, and expiry. Signatures expire after five minutes. After verification, the workflow checks the gate again to reject concurrent changes or already-recorded decisions. The allowlist controls which gates each reviewer can approve. Missing configuration, invalid signatures, unknown reviewers, and expired or altered decisions fail closed.

Create keys outside the project and submission archive:

```sh
engineering-keygen --directory /absolute/private/reviewer-keys --reviewer local-user
```

Configure the worker with the trust file:

```sh
export ENGINEERING_APPROVAL_KEYS=/absolute/private/reviewer-keys/trusted-reviewers.json
```

Configure the reviewing terminal with the private key:

```sh
export ENGINEERING_APPROVAL_PRIVATE_KEY=/absolute/private/reviewer-keys/reviewer.pem
```

The normal `engineering review` command signs automatically for Claude runs. Keep the private key readable only by its owner (0600). Protect the worker's trust file from unauthorized changes. Remove a reviewer from the trust file to revoke subsequent verification requests. Already accepted decisions remain in history.

This authenticates possession of an enrolled key, not a person's legal identity. Demo mode remains explicitly unsigned for free control-flow exercises. The Temporal development endpoint and requirement-change/stop operations do not gain access control from this feature; production use still requires Temporal authentication, authorization, and TLS. An operator able to replace worker code or its trust file is inside the trust boundary.

## Security gate

Install `.[dev,claude,security]` with the tested requirements. The worker runs three checks:

1. Approved-file integrity and Python syntax.
2. Bandit static analysis of all generated Python, ignoring inline `nosec` suppressions. Medium/high findings block completion. Low findings remain visible in the report; test assertions commonly produce low findings.
3. `pip-audit` against the actual package inventory of the configured test image. Every reported known vulnerability blocks completion. Advisory failures, skipped packages, unavailable scanners, or missing Docker block validation rather than passing it.

The dependency inventory is read from a trusted prebuilt image without networking. Advisory lookup runs outside the generated-code container, against package metadata only (`--disable-pip --no-deps`); generated code is not installed or executed by the audit. Generated dependency manifests are rejected by this gate because the fixed test image does not install them.

Detailed reports are saved under `ARTIFACT_ROOT/<workspace_id>/security/<version>-<revision>.json`. Test execution remains in Docker with no network and restricted filesystem/resource access. Bandit reads source without importing it.

These are real source and known-vulnerability checks, not a guarantee of complete security. They do not cover all business-logic flaws, OS image vulnerabilities, penetration testing, malicious local operators, or vulnerabilities absent from the advisory database. The image and model are trusted operator configuration.

## Verification and historical evidence

The updated suite passed 56 tests, including signature tampering/replay rejection, unauthorized gates, unsigned Claude review rejection through Temporal, real Bandit detection of unsafe `eval`, and fail-closed dependency-audit cases.

A new scan of the final brownfield application found zero medium/high Bandit findings and zero known vulnerabilities in 21 test-image packages. Its 46 low findings are pytest assertions. Original completed greenfield/brownfield reports remain unchanged: their approvals and security checks predate these controls.

The separate `claude-ambiguous-1` run uses task queue `engineering-secure-v1` and these controls. It completed both signed human approval gates, passed 15 application tests, and passed the source and dependency scans. Its completed report is under `evidence/ambiguous/`. Start fresh workflows after this workflow-code change; do not move old unfinished runs to the new worker.

References: [Bandit](https://bandit.readthedocs.io/en/latest/man/bandit.html), [pip-audit](https://pypi.org/project/pip-audit/).
