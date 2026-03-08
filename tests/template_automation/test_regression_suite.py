from __future__ import annotations

import pytest

from .helpers import assert_run_result, execute_scenario, load_scenario_cases


CASES = load_scenario_cases()


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.pytest_id)
def test_template_automation_regression_suite(case, tmp_path) -> None:
    result = execute_scenario(case, tmp_path)

    assert_run_result(result)
