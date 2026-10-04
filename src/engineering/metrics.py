"""Aggregate exported terminal run states; never manufacture missing observations."""
from collections.abc import Iterable


def aggregate(reports: Iterable[dict]) -> dict:
    reports = list(reports)
    finished = [r for r in reports if r['stage'] in {'completed', 'stopped', 'needs_intervention'}]
    count = len(finished)
    succeeded = sum(r['stage'] == 'completed' for r in finished)
    recovered = sum(r['metrics']['recoveries'] for r in finished)
    seconds = sum(r['metrics']['recovery_seconds'] for r in finished)
    return {
        'terminal_runs': count,
        'success_rate': succeeded / count if count else None,
        'runs_with_observed_activity_retries': sum(r['metrics']['activity_retries'] > 0 for r in finished),
        'retry_run_frequency': sum(r['metrics']['activity_retries'] > 0 for r in finished) / count if count else None,
        'rollback_run_frequency': sum(r['metrics']['rollbacks'] > 0 for r in finished) / count if count else None,
        'mean_recovery_seconds': seconds / recovered if recovered else None,
        'mean_end_to_end_seconds': sum(r['metrics']['elapsed_seconds'] for r in finished) / count if count else None,
        'retry_scope': 'Observed attempts on successful Activity completions; exhausted attempts require Temporal history',
        'recovery_scope': 'First failed validation through successful validation, including approval wait; unrecovered failures excluded',
    }
