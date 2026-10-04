# Workflow controls

These examples use the free demo adapter to exercise workflow controls. For real code generation, see [Claude setup](claude.md) and [signed approvals](security-and-approvals.md).

## Scope

Both providers use Temporal control flow and isolated file operations. In this demo mode, the model adapter and validation results are simulated. Claude mode separately generates and validates real applications; see the completed evidence in the submission overview.

The demo writes a JSON change artifact under an isolated run directory. It does not modify the scaffold source or deploy anything. A workflow run gets a separate directory derived from its workflow and run identifiers.

## Start and approve

Start the local Temporal server and worker as described in the README. Export `ARTIFACT_ROOT` to a stable absolute directory before starting the worker. Every worker processing the same task queue must see the same artifact storage.

```sh
engineering start --id controls-1 --requirement 'Build a shortener' --demo-failures 1
engineering status --id controls-1
```

The first pause is `awaiting_apply`. Inspect the proposal at `ARTIFACT_ROOT/<workspace_id>/<candidate_artifact>`, and its SHA256 in the status response. Approval binds the current revision to that prepared artifact.

```sh
engineering review --id controls-1 --revision 1 --gate apply --reviewer local-user --decision approve
```

With one simulated test failure, the next proposal is revision 2 and needs another apply approval. After checks pass, approve the separate final review gate using the current revision:

```sh
engineering review --id controls-1 --revision 2 --gate apply --reviewer local-user --decision approve
engineering review --id controls-1 --revision 2 --gate review --reviewer local-user --decision approve
engineering result --id controls-1
```

Run status between decisions and wait for the matching gate. Early, duplicate, wrong-gate, or stale decisions are rejected. Demo approvals use a reviewer label; Claude approvals require a verified signature.

## Clarification and requirement changes

```sh
engineering start --id privacy-1 --requirement 'Privacy friendly analytics' --question 'What data can be retained?'
engineering clarify --id privacy-1 --version 1 --answer 'Only aggregate click counts'
engineering change --id privacy-1 --version 1 --requirement 'Aggregate counts and expiring links' --reason 'Scope expanded'
```

Clarification is explicitly requested by the input; the demo agent does not automatically detect ambiguity. Only one answer is accepted for each pending question. Requirement updates use the expected current version, reject concurrent pending updates, and allow at most five replans.

Accepted changes immediately invalidate approval and check eligibility. Active Activities finish, including all parallel validation branches, before restoration begins. The workflow restores the prior baseline if anything was applied, advances the requirement version, clears obsolete checks and proposal references, and replans. Proposal and decision history remain available. Revision numbers never repeat during a run.

## Recovery and safe stopping

```sh
engineering stop --id privacy-1 --reason 'Pause this work for manual review'
```

The stop command ends the run after active Activities finish and applied files are restored. It does not provide a resumable pause. Use a new run to continue after a terminal stop.

- Apply and final-review gates default to a 24-hour deadline; `--approval-timeout` configures 1 through 86400 seconds for demonstrations.
- Demo Activity failures have at most three attempts and a 100-second overall deadline. Claude Activities use one attempt and a 310-second overall deadline.
- Validation failure allows at most two repair cycles per requirement version. Every repaired proposal needs fresh apply approval.
- Rejection, timeout, exhausted repair budget, or explicit stop restores any applied changes to that version's baseline.
- Snapshot creation, proposal creation, file replacement, and restoration tolerate Activity retries. Restoration is per file, not a multi-file filesystem transaction.
- Failed restoration ends in `needs_intervention`, preserves available evidence, and reports that manual recovery is needed.
- Fallback is a human handoff with retained proposal files and decision records. There is no automatic fallback to a second model provider.
- Temporal worker restart recovery uses the same server history and artifact directory. The local dev server is in-memory by default; stopping it loses that history.
- Use the `stop` Update for governed cleanup. Direct Temporal cancellation or termination does not guarantee restoration in this version.

## Tool policy and security boundaries

The dispatcher accepts only named operations implemented in code. Files are confined to the configured run directory, with traversal and symlinks rejected and bounded artifact sizes. Proposals are immutable and checked against the approved hash before application; validation checks the applied file against the same hash.

The command helper allows only `python_syntax`, using a fixed isolated Python process that parses input with `ast.parse`; it never executes supplied code or arbitrary shell commands. It has a maximum five-second deadline and a minimal environment. Generated tests use a separate restricted Docker runner; see [Claude setup](claude.md).

Credential-shaped text is rejected at the CLI before submission and checked again in workflow handlers. Audit details are redacted. Pattern matching is incomplete and cannot guarantee secret detection. Direct SDK callers can put inputs in Temporal history before workflow validation; never submit credentials as workflow data. Production use requires authenticated callers, authorization, restricted Temporal access, payload encryption/redaction policy, and a proper sandbox for generated code.

Artifact storage must be worker-owned and inaccessible to untrusted local writers. Path validation does not defend against hostile concurrent filesystem mutation. The local policy is not a financial compliance certification or a tamper-proof audit system.

## Observability and metrics

Each run records sequenced, timestamped events with requirement version, revision, approvals, artifact hashes, Activity outcomes, replans, recovery, and stop reasons. Status exposes completed stage durations and elapsed time as of the last stage transition; it does not include the continuously growing duration of a current wait.

```sh
engineering export --id controls-1 --output controls-1.json
engineering metrics controls-1.json
```

Export each run once for aggregation. Duplicate files count as duplicate observations.

- Success rate: completed runs divided by terminal runs (completed, stopped, or needs intervention).
- Retry frequency: terminal runs with observed Activity retries divided by terminal runs. Successful Activity results report their attempt counts. Exhausted failures require inspection of Temporal history; the summary is not a complete retry count.
- Rollback frequency: terminal runs with a successful restoration divided by terminal runs. Restoration failures are separately counted.
- Mean recovery time: total time from first failed validation to subsequent passing validation divided by recovered validation episodes. Includes approval waits; excludes unrecovered failures.
- End-to-end latency: start to terminal state, including human waits. Empty populations and no observed recovery yield null rather than fabricated zeros.

## Scope beyond the local prototype

The Claude provider, context transfer, Docker test execution, and generated shortener examples are implemented and demonstrated. Production endpoint authorization, broader security assurance, shared durable artifact storage, and worker versioning remain future work.

Use fresh workflow IDs when trying these examples. Workflow-code changes may not replay old histories; retain compatible workers for unfinished runs.
