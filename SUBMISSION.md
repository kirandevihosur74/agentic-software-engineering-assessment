# Agentic Software Engineering — Assessment Submission

## Overview

This Python prototype takes a software requirement, asks for clarification when needed, proposes code changes, and validates the approved code. Temporal manages the workflow and its state. The Claude Agent SDK handles requirement analysis, design, and code proposals.

A FastAPI URL shortener backed by SQLite demonstrates the system on both new and existing code. Human approval is required before applying changes and again before completing the run. Completion does not deploy the application.

## How it works

1. Save the starting code as a baseline.
2. Analyze the requirement and resolve unclear decisions with the user.
3. Create a plan and a versioned code proposal.
4. Wait for approval of that proposal and its file hash.
5. Apply the approved files to an isolated workspace.
6. Run application tests and source/dependency security checks in parallel; wait for both results.
7. Request approval for any repair proposal, or stop when the repair limit is reached.
8. Obtain final review approval and record the result.

If requirements change, the workflow invalidates previous approvals and checks. It waits for active work to finish, restores applied files to the baseline, and prepares a new proposal. The lifecycle graph is fixed; the agent supplies the design and implementation within those stages.

## Demonstrations and results

| Scenario | Demonstration | Verified result |
| --- | --- | --- |
| New application | Generate a URL shortener with unique codes, HTTP 302 redirects, SQLite persistence, and aggregate click counts. | Completed; 15 application tests passed. |
| Existing application | Extend the generated shortener with optional expiration, strict input validation, and migration of existing databases. | Completed; final revision passed 36 application tests. |
| Ambiguous requirements | Pause to clarify custom aliases, duplicate URLs, allowed schemes, code format, and analytics scope. | Separate run `claude-ambiguous-1` completed after clarification; 15 tests passed, both approvals were signature-verified, and source/dependency scans passed. |
| Changed requirements and rollback | After the first expiration implementation passed 34 tests, change expired redirects from HTTP 404 to 410 and increase maximum TTL to seven days. | Previous approval invalidated; source restored and replanned. Restored file hashes matched the baseline. The replacement passed 36 tests and received final approval. |

The completed brownfield run recorded two replans, one successful rollback, and zero rollback failures. The latest orchestration test run passed 56 tests, including eleven Temporal integration cases. These are separate from the generated application's tests.

## Controls and design choices

- **Durable coordination:** Temporal keeps workflow history, approval decisions, and progress. Worker-restart behavior is covered by integration tests.
- **Human control:** Approvals identify a specific revision. Changed requirements invalidate earlier decisions.
- **Restricted agent access:** Claude returns structured file proposals. It has no shell, file-editing, web, or MCP tools in this integration.
- **Independent validation:** Generated tests run in Docker with networking disabled, read-only mounts, a non-root user, and resource limits. API credentials are not passed to the test container.
- **Bounded work:** Model calls have time and budget limits; repairs and replans are capped. Claude Activities use one attempt to avoid automatic duplicate paid calls.
- **Traceable evidence:** Reports retain requirements, decisions, proposal hashes, check results, events, and metrics. Model context includes the current files and relevant prior results.

## Run locally

Prerequisites: Python 3.11+, Temporal CLI, running Docker, and an Anthropic API key supplied through the worker environment.

From the project directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-tested.txt '.[dev,claude,security]'
docker build -f containers/Dockerfile.tests -t engineering-tests:local .
```

Start Temporal in one terminal:

```sh
temporal server start-dev
```

Before starting Claude runs, create and configure reviewer keys as described in [security setup](docs/security-and-approvals.md). In a second terminal, activate the environment, configure `ANTHROPIC_API_KEY` securely, and start the worker:

```sh
export ARTIFACT_ROOT="$PWD/artifacts"
export ENGINEERING_TEST_IMAGE=engineering-tests:local
export CLAUDE_MODEL=sonnet
export CLAUDE_MAX_BUDGET_USD=1.00
export CLAUDE_TIMEOUT_SECONDS=180
engineering-worker
```

In another activated terminal, start a fresh run:

```sh
engineering start --id submission-demo-1 --provider claude --requirement 'Build a Python FastAPI URL shortener with SQLite, unique shortcodes, HTTP 302 redirects, aggregate click counts, and pytest tests under tests/.'
engineering status --id submission-demo-1
```

Answer any clarification with `engineering clarify`. At `awaiting_apply`, inspect the proposal and approve its current revision. At `awaiting_review`, inspect the checks and approve the final review. Replace `N` below with the revision shown by status, and run each approval only at its corresponding gate:

```sh
engineering review --id submission-demo-1 --revision N --gate apply --reviewer local-user --decision approve
engineering review --id submission-demo-1 --revision N --gate review --reviewer local-user --decision approve
engineering result --id submission-demo-1
```

Run the orchestration tests with the local Temporal server available:

```sh
TEMPORAL_TEST_ADDRESS=localhost:7233 pytest -q
```

## Evidence and source guide

- [Greenfield report](evidence/greenfield/report.json) and [generated code](evidence/greenfield/generated-shortener/).
- [Brownfield final report](evidence/brownfield/report.json) and [final generated code](evidence/brownfield/revision-3-applied/).
- [Separate ambiguity report](evidence/ambiguous/report.json), [generated code](evidence/ambiguous/generated-shortener/), and [security scan](evidence/ambiguous/security-scan.json).
- [Rollback hash verification](evidence/brownfield/rollback-verification.json) and [scenario history](evidence/brownfield/README.md).
- [Workflow implementation](src/engineering/workflow.py), [Claude integration](src/engineering/claude_agent.py), and [Docker test runner](src/engineering/test_runner.py).

The runnable generated applications are in the evidence directories above. `src/shortener/` is an early API scaffold, not the completed generated application.

## Limitations and next improvements

This is a local prototype. New Claude runs verify Ed25519-signed approval decisions against an enrolled reviewer allowlist and run Bandit plus dependency vulnerability checks. Earlier completed run reports retain their original unsigned approval and limited-check evidence. See [security setup](docs/security-and-approvals.md). These checks do not guarantee complete security, and the Temporal endpoint still requires production access controls. Artifact storage is local and must be shared by workers handling the same run.

Rollback restores source files; it does not reverse a deployed database migration. Restoration is repeatable per file, not an atomic filesystem transaction. The workflow uses a fixed graph and reruns affected stages broadly rather than selectively scheduling a generated task graph.

Production work would add endpoint authentication and authorization, broader security analysis, shared durable artifact storage, stronger execution isolation, and cross-platform dependency locks with artifact hashes. A tested Python dependency snapshot is included in `requirements-tested.txt`. The `sonnet` alias and per-call budget also do not guarantee a fixed model version or a total workflow cost.
