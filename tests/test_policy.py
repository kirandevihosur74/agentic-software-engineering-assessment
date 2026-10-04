import pytest
from engineering.models import ReviewDecision, RunRequest, RunState
from engineering.policy import lifecycle_graph, validate_request, validate_review


def test_rejects_stale_and_duplicate_approval():
    state = RunState(stage="awaiting_review", revision=2)
    with pytest.raises(ValueError, match="Stale"):
        validate_review(state, ReviewDecision(1, True, "reviewer"), False)
    with pytest.raises(ValueError, match="No review"):
        validate_review(state, ReviewDecision(2, True, "reviewer"), True)
    validate_review(state, ReviewDecision(2, True, "reviewer"), False)


@pytest.mark.parametrize("run_request", [RunRequest(""), RunRequest("build", max_repairs=3)])
def test_invalid_request(run_request):
    with pytest.raises(ValueError):
        validate_request(run_request)


def test_graph_dependencies_exist_and_are_acyclic():
    completed = set()
    for task in lifecycle_graph():
        assert set(task.depends_on) <= completed
        completed.add(task.name)
    assert next(t for t in lifecycle_graph() if t.name == "review").depends_on == ["tests", "security"]
