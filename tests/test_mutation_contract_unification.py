# SPDX-License-Identifier: Apache-2.0
"""S-091 P2 — mutation return-type unification contract.

S-089 shipped ``as_mutation_report()`` on four write-result models. P2 fixes the
*unification*: the public mutation-write surface is a closed set, and every path
in it projects onto ``hwpx.mutation-report/v1``. This locks two things:

1. The native save path (``save_to_path``/``save_to_stream`` with
   ``return_report=True``) returns a :class:`MutationReport` directly.
2. Every byte-write result model (carrying ``data``/``changed_parts``/
   ``open_safety``) exposes ``as_mutation_report``. A future 5th byte-write model
   added without a projection breaks this test on purpose — the survey found no
   projection-incapable public mutation path today.

Per-model projection *fidelity* is covered by ``test_mutation_report_projections``;
this file only freezes the closed set + the presence of the projection.
"""

from __future__ import annotations

import dataclasses
import importlib
from io import BytesIO
from pathlib import Path

from hwpx import HwpxDocument
from hwpx.agent.model import AgentBatchResult
from hwpx.body_patch import BodyOpsResult
from hwpx.mutation_report import MUTATION_REPORT_SCHEMA, MutationReport
from hwpx.patch import BytePreservingPatchResult
from hwpx.table_patch import CellFillResult


# The closed set of public mutation-write result models that project onto v1.
FROZEN_PROJECTION_MODELS = {
    BytePreservingPatchResult,
    CellFillResult,
    BodyOpsResult,
    AgentBatchResult,
}

# Modules whose byte-write result models must all carry a projection. The agent
# transaction result (AgentBatchResult) has a different shape (verification
# report, not raw open_safety) and is asserted separately.
_BYTE_WRITE_MODULES = ("hwpx.patch", "hwpx.table_patch", "hwpx.body_patch")


def _is_byte_write_result(obj: object) -> bool:
    """A frozen result model that carries a written archive + change list."""

    if not (isinstance(obj, type) and dataclasses.is_dataclass(obj)):
        return False
    fields = {f.name for f in dataclasses.fields(obj)}
    return {"data", "changed_parts", "open_safety"} <= fields


def test_all_projection_models_expose_as_mutation_report() -> None:
    for model in FROZEN_PROJECTION_MODELS:
        assert callable(getattr(model, "as_mutation_report", None)), model


def test_every_byte_write_result_model_has_a_projection() -> None:
    """Structural guard: any dataclass shaped like a byte-write result across the
    three byte-splice modules must expose ``as_mutation_report``. Freezing the
    discovered set catches a new mutation model added without a projection."""

    discovered: set[type] = set()
    for module_name in _BYTE_WRITE_MODULES:
        module = importlib.import_module(module_name)
        for value in vars(module).values():
            if _is_byte_write_result(value):
                discovered.add(value)
                assert callable(
                    getattr(value, "as_mutation_report", None)
                ), f"{module_name}.{value.__name__} lacks as_mutation_report()"

    assert discovered == {
        BytePreservingPatchResult,
        CellFillResult,
        BodyOpsResult,
    }


def test_agent_batch_result_exposes_projection() -> None:
    assert callable(getattr(AgentBatchResult, "as_mutation_report", None))


def test_save_to_path_return_report_is_mutation_report(tmp_path: Path) -> None:
    document = HwpxDocument.new()

    report = document.save_to_path(tmp_path / "unified.hwpx", return_report=True)

    assert isinstance(report, MutationReport)
    assert report.to_dict()["schemaVersion"] == MUTATION_REPORT_SCHEMA


def test_save_to_stream_return_report_is_mutation_report() -> None:
    document = HwpxDocument.new()
    stream = BytesIO()

    report = document.save_to_stream(stream, return_report=True)

    assert isinstance(report, MutationReport)
    assert report.to_dict()["schemaVersion"] == MUTATION_REPORT_SCHEMA
