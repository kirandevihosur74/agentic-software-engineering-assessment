# Agentic Software Engineering Assessment

A Python prototype that uses Temporal to coordinate Claude-generated code changes, human approvals, independent validation, and source rollback.

**Start with [the submission overview](SUBMISSION.md)** for the design, setup commands, demonstrated scenarios, results, and limitations.

## Verified demonstrations

- Greenfield URL shortener: completed; 15 application tests passed.
- Brownfield expiration enhancement: completed; final revision passed 36 application tests.
- Separate ambiguity run: completed after clarification; 15 tests passed, with signed approvals and source/dependency scans.
- Requirement changes: two replans and one verified source rollback in the brownfield run.

[Evidence and verification](docs/verification.md) distinguishes application tests from orchestration tests. New Claude runs include Bandit and dependency vulnerability scanning. See [security and signed approvals](docs/security-and-approvals.md) for setup and policy; historical reports retain their original check scope.

## Evidence screenshots

[View the Temporal screenshots and captions](evidence/screenshots/README.md) for the workflow overview, requirement-change timeline, and completed demo execution.

## Install

Requires Python 3.11+, the Temporal CLI, running Docker, and Anthropic API access for Claude mode. The tested dependency snapshot was verified with Python 3.13 on macOS.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-tested.txt '.[dev,claude,security]'
```

`requirements-tested.txt` pins the tested Python dependencies; it is not a cross-platform hash lock. The Docker image has its own dependencies. The base image and model alias are not immutable pins.

Follow [SUBMISSION.md](SUBMISSION.md#run-locally) to build the test image, start Temporal and the worker, and submit a requirement. Environment settings are shown in `.env.example`; this file is not loaded automatically. Keep API keys outside the submission.

## Find the code

| Location | Purpose |
| --- | --- |
| `src/engineering/` | Workflow, Claude adapter, approvals, artifacts, rollback, and test runner |
| `tests/` | Orchestration and integration tests |
| `evidence/greenfield/generated-shortener/` | Completed original generated application |
| `evidence/brownfield/revision-3-applied/` | Completed application with expiration |
| `evidence/ambiguous/generated-shortener/` | Separate ambiguity demonstration |
| `src/shortener/` | Early API scaffold retained for its tests; not the generated application |
| `evidence/` | Completed reports, proposal diffs, and rollback verification |

## Run the generated application

From the project root with the environment active:

```sh
cd evidence/brownfield/revision-3-applied
uvicorn app.main:create_app --factory
```

The application uses `SHORTENER_DB` for the SQLite path and defaults to `shortener.db`. Its local README describes the API. Generated tests should run through the Docker runner described in [Claude setup](docs/claude.md).

## Workflow modes

`--provider claude` generates real code proposals. The default `demo` adapter exercises control flow without paid model calls and writes a demo JSON artifact. [Control examples](docs/workflow-controls.md) cover that mode.

To extend an approved completed run in a separate workspace:

```sh
engineering start --id brownfield-new --provider claude --from-workflow COMPLETED_ID --requirement 'Describe the requested change'
```

Use a fresh workflow ID. CLI and worker must share the same `ARTIFACT_ROOT`; the source run must exist in Temporal and its files must still exist there. Exported evidence alone is not an importable Temporal history.

## Tests and documentation

```sh
TEMPORAL_TEST_ADDRESS=localhost:7233 pytest -q
```

Without `TEMPORAL_TEST_ADDRESS`, integration tests are skipped. See [architecture](docs/architecture.md), [Claude setup](docs/claude.md), and [verification](docs/verification.md). Claude approvals now require enrolled signing keys. Comprehensive security assurance, production artifact storage, and deployment remain outside this prototype.
