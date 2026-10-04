# Brownfield expiration scenario

## Source and initial change

Workflow `claude-brownfield-1` starts from the approved output of `claude-e2e-1`, copied into a separate workspace. Its baseline is a content-addressed bundle; the original workspace is preserved. The input is recorded in `requirement-v1.txt`.

The initial change adds optional TTL expiration with strict input validation, preserves non-expiring existing links, safely migrates SQLite, and adds deterministic tests and setup documentation. Expired redirects initially return HTTP 404.

## Planned requirement change and rollback demonstration

1. Review the initial proposal and approve its apply gate.
2. Wait for validation to pass and the workflow to reach `awaiting_review`. Export that state and preserve the applied files and test results.
3. Before final approval, change the requirement to return HTTP 410 for expired links while keeping HTTP 404 for unknown codes, and allow TTL up to 604800 seconds (seven days).
4. Confirm the workflow restores the original shortener baseline, invalidates old approvals/checks, increments the requirement version, and prepares a new proposal.
5. Compare the restored workspace file hashes with the original snapshot. Preserve the equality result as rollback evidence. The next proposal is still unapplied at this point.
6. Review and approve the new proposal, run tests, and record final approval only after validation passes.

This plan is not evidence that these events have already occurred. Reports and verification notes will identify actual completed steps.

## Dedicated worker

This scenario uses task queue `engineering-brownfield-v1`. A dedicated worker was started from this chat. If it is stopped, start one from the project directory with the same Anthropic and Docker configuration:

```sh
export TEMPORAL_TASK_QUEUE=engineering-brownfield-v1
export ARTIFACT_ROOT="$PWD/artifacts"
export ENGINEERING_TEST_IMAGE=engineering-tests:local
engineering-worker
```

Status, review, and change commands address the workflow ID and do not require a task-queue override. Starting another workflow for this scenario does require the override.

## Brownfield start support

`engineering start --from-workflow <completed-id>` copies a completed passing run's source files into a frozen baseline bundle. Both CLI and worker must use the same `ARTIFACT_ROOT`. The source must be completed and its stored checks must have passed. CLI reads the completed result from Temporal history, avoiding a worker replay merely to export evidence.

The new workflow restores source files with read permissions compatible with the non-root Docker test runner. Baseline copying, tamper detection, idempotency, isolation, rollback and replanning are covered by tests.

## Current checkpoint

Revision 2 was approved and applied. Its Docker validation passed all 34 tests; file integrity and Python syntax checks also passed. See `revision-2-passing.json` and `revision-2-applied/`.

A requirement change to seven-day TTL and HTTP 410 for expired links was submitted before final review approval. The workflow recorded one rollback and advanced to requirement version 3. SHA-256 hashes of every restored workspace file matched the saved baseline, including removal of added files. See `rollback-verification.json` and `post-rollback-status.json`.

This verifies source-file rollback in the isolated workspace; it does not claim rollback of a deployed service or a live database migration.

The replacement proposal received fresh apply approval, passed validation, and received final review approval.

Revision 3 has now been applied and passed validation. See `revision-3-passing.json` for the test output and `revision-3-applied/` for the generated files. The workflow subsequently received final human review approval.

Final human review approval is complete. Temporal reports COMPLETED and application stage completed. The final report is saved as `report.json`; revision 3 passed 36 application tests.
