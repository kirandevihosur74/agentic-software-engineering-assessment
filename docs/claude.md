# Claude Agent SDK integration

## What is connected

The `claude` provider calls the Python Claude Agent SDK for requirement analysis, design, and file-change proposals. It passes current workspace files, accepted requirements, previous design artifacts, and validation failures between stages. Structured output is schema-checked before it becomes a proposal.

Claude has no built-in file, shell, web, or MCP tools in this integration. The worker supplies repository context; Claude returns changed file contents. Application code applies those changes only after the existing Temporal approval gate. This gives us actual model-generated code while preserving the controls already implemented. It is not a general-purpose interactive Claude Code session.

The default remains `demo`, so existing examples and tests do not silently incur API usage.

## Configuration

Install the optional SDK dependency in the project virtual environment:

```sh
python -m pip install -e '.[dev,claude,security]'
```

Set `ANTHROPIC_API_KEY` securely in the worker environment. Do not put the key in a workflow request, commit it, or paste it into chat. The environment used during integration already had this variable configured.

Optional worker settings:

```sh
export CLAUDE_MODEL=sonnet
export CLAUDE_MAX_BUDGET_USD=1.00
export CLAUDE_TIMEOUT_SECONDS=180
export ARTIFACT_ROOT=/absolute/path/to/engineering-artifacts
export ENGINEERING_TEST_IMAGE=engineering-tests:local
```

`sonnet` is a model alias; set a full model ID if reproducible model selection is required. SDK version 0.2.163 is pinned in the Claude extra. The per-call budget is the SDK's estimated spend limit, not a guaranteed total run bill. Up to two repair proposals and up to five requirement replans can add calls. Each SDK call has a turn limit and deadline. Claude-mode Activities use one attempt to avoid automatic duplicate paid calls after ambiguous failures.

The worker does not automatically load `.env`. Session data uses a temporary configuration directory; user/project settings, plugins, skills, and external MCP configuration are disabled. Credentials remain in the worker environment and are not included in saved request context.

## Prepare the isolated test runner

Start Docker, then build the controlled image from the project root:

```sh
docker build -f containers/Dockerfile.tests -t engineering-tests:local .
```

The worker executes `pytest` in that image with network disabled, a read-only root and workspace mount, a non-root user, dropped capabilities, and CPU, memory, process, and time limits. It does not mount the Docker socket into the test container or forward API credentials. Test output retained in the worker is capped at 8000 bytes. The image has fixed dependencies; model-supplied dependency installation commands are not run.

The Docker runner was exercised in the completed greenfield and brownfield runs; the final generated application passed 36 tests. Without a configured working image, validation fails closed, the workflow restores applied changes, and the run stops without spending repair calls on missing infrastructure. This container configuration needs further hardening before running arbitrary hostile code in production.

## Run through Temporal

Configure the worker trust file and reviewer signing key using [security setup](security-and-approvals.md). Start the local Temporal server and a worker with the settings above. Use a fresh workflow ID:

```sh
engineering start --id claude-shortener-1 --provider claude --requirement 'Build a Python FastAPI URL shortener with SQLite, unique short codes, redirects, aggregate click counts, and pytest tests under tests. Store no visitor identifiers.'
engineering status --id claude-shortener-1
```

If Claude identifies questions, status shows `awaiting_clarification` and the questions. Answer against the current requirement version:

```sh
engineering clarify --id claude-shortener-1 --version 1 --answer 'Use HTTP 302 redirects and store only the total click count per link.'
```

At `awaiting_apply`, inspect the proposal JSON, file contents, and hash returned by status. Then approve that specific revision:

```sh
engineering review --id claude-shortener-1 --revision 1 --gate apply --reviewer local-user --decision approve
```

The worker applies the files and runs validation. A repaired proposal gets a new revision and needs another apply approval. At `awaiting_review`, inspect the test evidence before final approval:

```sh
engineering review --id claude-shortener-1 --revision 1 --gate review --reviewer local-user --decision approve
engineering result --id claude-shortener-1
```

Use the actual revision shown by status. Claude approvals now require an enrolled signing key; see [security and approvals](security-and-approvals.md). Final approval does not deploy the application.

## Artifacts and recovery

- `claude/`: complete validated response receipts with session ID, model alias, usage, and estimated cost.
- `context/`: requirement analysis, design, proposals, and check evidence for each requirement version.
- `proposals/`: immutable file-change proposals hashed for approval.
- `workspace/`: applied files.
- `snapshots/`: per-version restoration baselines.

Completed responses are reused using a stage and input-context hash. Proposals are reused by version and revision. An interruption before a response receipt is saved can still lose a paid response; this does not provide exactly-once model billing. Network errors and budget/schema failures stop safely and do not become accepted proposals.

Proposals allow only bounded relative paths with approved extensions. Hidden files, traversal, shell scripts, duplicate paths, and oversized proposals are rejected. Current proposals support file creation and replacement, not deletion. Existing file context is bounded by the prototype's artifact-size limits.

## Validation scope

Tests run independently of Claude's claims. The security gate verifies proposal integrity, scans Python with Bandit, and audits test-image dependencies with pip-audit. Claude review decisions require signatures. See [security and approvals](security-and-approvals.md). Production endpoint authorization, artifact storage, and broader security assurance remain outstanding. Actual generated-code results are recorded under `evidence/`.

Tests that stub the SDK prove integration behavior without paid calls. They are separate from the completed live Claude runs under `evidence/` and the earlier SDK smoke test recorded in `claude-smoke.json`.

## References

- https://code.claude.com/docs/en/agent-sdk/python
- https://code.claude.com/docs/en/agent-sdk/structured-outputs
