# Separate ambiguous-requirement scenario

Workflow `claude-ambiguous-1` runs on task queue `engineering-secure-v1` with signed approvals and security scans enabled.

Input: build a simple privacy-friendly shortener with analytics. Claude identified questions about authentication, expiry, redirects, analytics detail, duplicates, aliases, retention, bots, URL policy, and base URL. The answers in `answer.txt` use the V1 decisions previously agreed with the user.

Final status: completed. `report.json` records both signed human approvals, 15 passing application tests, zero medium/high Bandit findings, and zero known vulnerabilities across 21 test-image dependencies. The 18 low Bandit findings are test assertions. `security-scan.json` contains the scan details, and `generated-shortener/` contains the applied code.

An unsigned approval was rejected without advancing the workflow; see `unsigned-rejection.json`. `proposal.json` retains the candidate, while earlier pending/status files show intermediate checkpoints, not the final state.

Earlier `clarification-evidence.json` records the clarification embedded in the greenfield run and is retained as supporting history, not as the result of this separate run.
