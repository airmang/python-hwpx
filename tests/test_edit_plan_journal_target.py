# SPDX-License-Identifier: Apache-2.0
"""An edit plan's journal is not written into a document.

The journal is JSON lines appended to ``journalPath`` as the plan runs, a dry run included. A plan
whose journal named its own source or output used to be accepted: the lines were appended to the
document, which then no longer opened (finding W12 of the 2026-11 write-path audit, issue 834).
Validation now refuses it, and ``validate_edit_plan``, a dry run and a real run give the same
judgement. The documents here are built in the test.
"""

from __future__ import annotations

import json
import os
import warnings
from pathlib import Path
from typing import Any, Callable

import pytest

from hwpx import HwpxDocument
from hwpx.errors import Hwp5Error
from hwpx.plan import PlanValidationError, apply_edit_plan, validate_edit_plan


def _document_bytes() -> bytes:
    document = HwpxDocument.new()
    document.add_paragraph("alpha one")
    document.add_paragraph("beta two")
    return document.to_bytes()


def _hwp_file(path: Path) -> bytes:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        HwpxDocument.open(_document_bytes()).save(path)
    data = path.read_bytes()
    assert data[:8] == bytes.fromhex("d0cf11e0a1b11ae1")
    return data


def _plan(source: Path, output: Path, **extra: Any) -> dict[str, Any]:
    return {
        "schemaVersion": "hwpx.edit-plan/v1",
        "source": str(source),
        "output": str(output),
        "steps": [{"id": "s", "op": "paragraph_patch", "args": {"patches": [{"paragraph_index": 1, "text": "N"}]}}],
        **extra,
    }


def _tree(root: Path) -> dict[str, bytes | None]:
    return {
        path.relative_to(root).as_posix(): (path.read_bytes() if path.is_file() else None)
        for path in sorted(root.rglob("*"))
    }


#: The three ways a plan is judged. Each must refuse the same plans with the same error.
_JUDGES: dict[str, Callable[[dict[str, Any]], Any]] = {
    "validate_edit_plan": lambda plan: validate_edit_plan(plan),
    "apply_edit_plan dry_run": lambda plan: apply_edit_plan(plan, dry_run=True),
    "apply_edit_plan": lambda plan: apply_edit_plan(plan),
}


def _case(tmp_path: Path, name: str) -> tuple[Path, Path, str, str]:
    """source, output, the journal path of the case, and which of the two the journal names."""

    source = tmp_path / "in.hwpx"
    source.write_bytes(_document_bytes())
    (tmp_path / "sub").mkdir()
    output = tmp_path / "out.hwpx"
    if name == "the source":
        return source, output, str(source), "source"
    if name == "the output, not yet written":
        return source, output, str(output), "output"
    if name == "the output, already there":
        output.write_bytes(_document_bytes())
        return source, output, str(output), "output"
    if name == "the source edited in place":
        return source, source, str(source), "source"
    if name == "the source through a folder and back":
        return source, output, str(tmp_path / "sub" / ".." / "in.hwpx"), "source"
    if name == "the output in upper case":
        return source, output, str(tmp_path / "OUT.HWPX"), "output"
    if name == "a hard link to the source":
        link = tmp_path / "journal.jsonl"
        os.link(source, link)
        return source, output, str(link), "source"
    raise AssertionError(name)


_CASES = [
    "the source",
    "the output, not yet written",
    "the output, already there",
    "the source edited in place",
    "the source through a folder and back",
    pytest.param(
        "the output in upper case",
        marks=pytest.mark.skipif(os.name != "nt", reason="a spelling Windows resolves to the same file"),
    ),
    "a hard link to the source",
]


@pytest.mark.parametrize("judge", list(_JUDGES))
@pytest.mark.parametrize("case", _CASES)
def test_a_journal_that_names_the_source_or_the_output_is_refused(case: str, judge: str, tmp_path: Path) -> None:
    source, output, journal, same_as = _case(tmp_path, case)
    before = _tree(tmp_path)

    with pytest.raises(PlanValidationError) as refused:
        _JUDGES[judge](_plan(source, output, journalPath=journal))

    error = refused.value
    assert error.code == "plan-invalid"
    assert "journalPath" in error.message
    assert error.context["journalPath"] == journal and error.context["sameAs"] == same_as
    assert "journal" in (error.suggestion or "")
    assert _tree(tmp_path) == before


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("target", ["source", "output"])
def test_the_journal_path_argument_is_judged_like_the_plan_field(target: str, dry_run: bool, tmp_path: Path) -> None:
    """``apply_edit_plan(journal_path=...)`` replaces the plan's field; the plan alone would pass."""

    source = tmp_path / "in.hwpx"
    source.write_bytes(_document_bytes())
    output = tmp_path / "out.hwpx"
    plan = _plan(source, output)
    validate_edit_plan(plan)
    before = _tree(tmp_path)

    with pytest.raises(PlanValidationError) as refused:
        apply_edit_plan(plan, dry_run=dry_run, journal_path={"source": source, "output": output}[target])

    assert refused.value.code == "plan-invalid" and refused.value.context["sameAs"] == target
    assert _tree(tmp_path) == before


@pytest.mark.parametrize("judge", list(_JUDGES))
def test_a_journal_is_not_appended_to_an_hwp_file_that_is_already_there(judge: str, tmp_path: Path) -> None:
    source = tmp_path / "in.hwpx"
    source.write_bytes(_document_bytes())
    _hwp_file(tmp_path / "other.hwp")
    before = _tree(tmp_path)

    with pytest.raises(Hwp5Error) as refused:
        _JUDGES[judge](_plan(source, tmp_path / "out.hwpx", journalPath=str(tmp_path / "other.hwp")))

    assert refused.value.code == "hwp5-overwrite-existing"
    assert _tree(tmp_path) == before


def test_a_journal_beside_the_documents_is_still_written(tmp_path: Path) -> None:
    source = tmp_path / "in.hwpx"
    original = _document_bytes()
    source.write_bytes(original)
    output = tmp_path / "out.hwpx"
    journal = tmp_path / "out.hwpx.journal.jsonl"
    plan = _plan(source, output, journalPath=str(journal))

    assert validate_edit_plan(plan).plan.journal_path == str(journal)
    report = apply_edit_plan(plan, dry_run=True)
    assert report.ok and not report.executed and not output.exists()
    report = apply_edit_plan(plan)

    assert report.ok and report.executed and report.journal_path == str(journal)
    events = [json.loads(line)["event"] for line in journal.read_text(encoding="utf-8").splitlines()]
    assert events == ["plan-start", "step", "plan-end"] * 2  # the dry run's lines, then the run's
    assert source.read_bytes() == original
    HwpxDocument.open(output).close()
