from __future__ import annotations

from bff_control.api.problems.registry import PROBLEM_SPECS, validate_problem_registry
from bff_control.api.problems.schemas import ProblemCode


def test_problem_registry_has_one_spec_per_public_code() -> None:
    validate_problem_registry()
    assert set(PROBLEM_SPECS) == set(ProblemCode)
    assert len({spec.type_uri for spec in PROBLEM_SPECS.values()}) == len(PROBLEM_SPECS)
