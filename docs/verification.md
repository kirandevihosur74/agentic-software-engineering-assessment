# Final verification with security and signed approvals

The separate `claude-ambiguous-1` run completed. Both apply and final-review approvals were cryptographically verified. Its 15 generated application tests passed; Bandit reported no medium/high findings, and the dependency audit reported no known vulnerabilities in 21 packages. The completed report and code are under `evidence/ambiguous/`.

A fresh virtual environment installed a clean copy of the updated source with the tested dependency snapshot and all extras. `pip check` passed; both CLI entry points worked. All 56 orchestration tests passed in 12.63 seconds, including the Temporal integration cases. The existing local Temporal server was used; no new paid model run was needed for this installation check. The added tests cover signature tampering and replay, unauthorized gates, unsigned approval rejection, unsafe-source detection, known dependency findings, and incomplete scan failures. The cryptography dependency was upgraded to 50.0.2 following an audit finding; the updated orchestrator dependency audit is clean.

Earlier verification checkpoints follow for historical context. Their narrower control descriptions apply to those earlier runs.

# Verification

## Fresh installation — October 3, 2026

The source was copied into a separate directory without virtual environments, generated package metadata, or caches. A new Python 3.13 virtual environment installed the copied project as a regular package using `requirements-tested.txt` and the `dev,claude` extras.

- Installation completed successfully; `pip check` reported no broken requirements.
- The installed `engineering --help` command worked.
- All 39 orchestration tests passed in 13.09 seconds, including eleven integration cases using the existing local Temporal development server.
- A new Docker image was built from the supplied Dockerfile. Generated application tests were rerun using the installed production test runner; see [results](../evidence/clean-setup-tests.json).

This verifies a clean Python installation on this Mac and a rebuilt Docker image. It does not claim verification on another OS, a fresh Temporal installation, or another paid model run.

## Completed live Claude runs

| Run | Result |
| --- | --- |
| `claude-e2e-1` | Completed; 15 application tests passed. Clarification decisions are recorded. |
| `claude-brownfield-1` | Completed; revision 2 passed 34 tests, final revision 3 passed 36 tests. |

The brownfield run recorded two replans, one successful source rollback, and zero rollback failures. Every restored file matched its saved baseline by SHA-256. Source snapshots, generated files, reports, and diffs are under `evidence/`.

## What the orchestration tests cover

Approval and rejection gates; stale decisions; clarification; bounded repairs and replanning; worker restart; timeouts and stop; changes during parallel validation; failed restoration; path and proposal checks; Claude structured-output handling; blocked Docker validation; baseline import, tamper detection, and source isolation.

Tests that stub Claude establish control behavior; they are distinct from the live model evidence. The earlier `day2-demo-report.json` and `claude-smoke.json` are historical supporting records.

## Limits

The security check covers file integrity and Python syntax. Reviewer names are unauthenticated labels. Rollback covers source files, not a deployed database, and restoration is per file rather than a filesystem transaction. Model billing is not exactly-once. See the submission overview for further tradeoffs.
