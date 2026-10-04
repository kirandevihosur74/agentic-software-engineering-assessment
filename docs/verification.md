# Verification results

## Completed scenarios

| Scenario | Evidence | Result |
| --- | --- | --- |
| Greenfield | [Completed report](../evidence/greenfield/report.json) | 15 application tests passed. |
| Brownfield | [Completed report](../evidence/brownfield/report.json) | Final revision passed 36 application tests; two replans and one successful rollback. |
| Ambiguous | [Completed report](../evidence/ambiguous/report.json) | 15 application tests passed; both signed approvals verified; source and dependency scans passed. |

The brownfield [rollback verification](../evidence/brownfield/rollback-verification.json) confirms that every restored file matched the baseline by SHA-256. Its intermediate revision passed 34 tests before the requirement changed.

## Fresh installation

A clean source copy was installed as a regular package in a new Python 3.13 virtual environment on macOS using `requirements-tested.txt` and the `dev,claude,security` extras.

- `pip check` found no broken requirements.
- Both `engineering` and `engineering-keygen` command-line entry points worked.
- **56 orchestration tests passed in 12.63 seconds**, including Temporal integration cases.

See the [installation record](../evidence/final-install-verification.json). Verification used the existing local Temporal server; it does not establish compatibility with every OS or represent a new paid model run.

## Test coverage

The orchestration suite covers approval gates, rejection, stale decisions, signature tampering and replay, unauthorized reviewers, clarification, bounded repairs, replanning, worker restart, timeouts, safe stopping, parallel checks, failed restoration, source isolation, proposal integrity, and scanner failures.

Tests using a stubbed model verify control behavior. The completed scenario reports separately document actual Claude-generated applications. Generated application tests run in the restricted Docker runner.

## Security evidence

The ambiguity run passed Bandit with no medium/high findings and a dependency audit with no known vulnerabilities in 21 image packages. Its low findings are test assertions. See the [scan report](../evidence/ambiguous/security-scan.json).

The orchestrator's [dependency audit](../evidence/security/orchestrator-dependencies.json) is also clean after upgrading cryptography to 50.0.2. Additional results are summarized in the [security evidence](../evidence/security/README.md).

The earlier greenfield and brownfield workflow reports predate signed approvals and expanded security scanning. They retain their original evidence; the brownfield source was also scanned separately after those controls were added.

## Limits

Scans do not guarantee complete security. Signed decisions authenticate possession of an enrolled reviewer key; production Temporal endpoint access controls remain separate. Rollback restores source files, not a deployed database, and restoration is per file. See [security and approvals](security-and-approvals.md) and the [submission overview](../SUBMISSION.md) for the full scope.
