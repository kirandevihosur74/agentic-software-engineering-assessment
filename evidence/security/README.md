# Security verification

- Updated orchestration suite: 56 passed in 12.00 seconds, including authentication and scanner tests.
- Orchestrator Bandit scan: no medium/high findings; full report in `orchestrator-bandit.json`.
- Dependency audit: no known vulnerabilities in 71 packages; full report in `orchestrator-dependencies.json`.
- The audit found an advisory affecting cryptography 49.0.0. Upgraded to 50.0.2, regenerated the dependency snapshot, and reran the audit and tests.
- Final brownfield source scanned separately: no medium/high findings and no known vulnerabilities in 21 image packages. Its 46 low findings are test assertions. See `brownfield-scan.json`.
- The new live ambiguity workflow rejected an unsigned approval. Evidence: `../ambiguous/unsigned-rejection.json`.

These scans do not retroactively change the original workflow reports. Scanning does not guarantee absence of all vulnerabilities. The separate ambiguity run completed with both signed approvals verified, 15 passing application tests, and passing security scans.
