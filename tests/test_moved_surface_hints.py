# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import ast

import pytest

import hwpx

EXPECTED_RETIRED_SURFACES = {
    "analyze_template_formfit",
    "apply_template_formfit",
    "TEMPLATE_FORMFIT_BASELINE_SCHEMA_VERSION",
    "TEMPLATE_FORMFIT_PLAN_SCHEMA_VERSION",
}


def test_all_47_moved_surfaces_have_parseable_executable_imports() -> None:
    assert len(hwpx._MOVED_TO_COMPANION) == 47
    assert {surface.kind for surface in hwpx._MOVED_TO_COMPANION.values()} == {
        "module",
        "renamed",
        "symbol",
    }

    for legacy_name, surface in hwpx._MOVED_TO_COMPANION.items():
        statement = surface.import_statement(legacy_name)
        assert statement is not None
        ast.parse(statement)
        with pytest.raises(hwpx.MovedToCompanion) as raised:
            getattr(hwpx, legacy_name)
        assert statement in str(raised.value)


def test_module_and_renamed_hints_bind_the_old_local_name() -> None:
    assert (
        hwpx._MOVED_TO_COMPANION["agent"].import_statement("agent")
        == "import hwpx_automation.office.agent as agent"
    )
    assert (
        hwpx._MOVED_TO_COMPANION["formfill_quality"].import_statement(
            "formfill_quality"
        )
        == "import hwpx_automation.office.form_fill.quality as formfill_quality"
    )
    assert (
        hwpx._MOVED_TO_COMPANION["mail_merge"].import_statement("mail_merge")
        == (
            "from hwpx_automation.office.document_ops import "
            "build_mail_merge as mail_merge"
        )
    )


@pytest.mark.parametrize("name", sorted(hwpx._RETIRED_SURFACES))
def test_retired_surfaces_give_a_non_import_replacement(name: str) -> None:
    surface = hwpx._RETIRED_SURFACES[name]
    assert surface.kind == "retired"
    assert surface.import_statement(name) is None
    assert surface.replacement
    with pytest.raises(hwpx.RetiredSurface, match="제거"):
        getattr(hwpx, name)


def test_retired_surface_set_is_exact() -> None:
    assert set(hwpx._RETIRED_SURFACES) == EXPECTED_RETIRED_SURFACES
