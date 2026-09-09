# SPDX-License-Identifier: Apache-2.0
"""Exercise the published example, including failures before publication."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx._document.ns.tables import TablesNamespace
from hwpx.mutation_report import PreservationDowngradeError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "safe_edit_example", ROOT / "examples/edit_existing_form.py"
)
assert spec and spec.loader
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)


def _form(path: Path, labels=("성명", "소속")) -> bytes:
    with HwpxDocument.new() as document:
        table = document.add_table(rows=len(labels), cols=2)
        for row, label in enumerate(labels):
            table.cell(row, 0).text = label
            table.cell(row, 1).text = "원래 값"
        document.save_to_path(path)
    return path.read_bytes()


@pytest.mark.parametrize("value", ["홍길동", "검토할 긴 문장입니다. " * 100, ""])
def test_example_verifies_values_without_claiming_visuals(tmp_path, value):
    source, output = tmp_path / "input.hwpx", tmp_path / "out.hwpx"
    original = _form(source)
    report = example.fill_existing_form(source, output, {"성명": value})
    assert source.read_bytes() == original
    assert report["content"] == {"requested": 1, "verified": 1}
    assert report["mutation"]["actualMode"] == "patch"
    assert report["mutation"]["path"] == str(output)
    assert report["visual"] == report["withinModifiedParts"] == "not_performed"
    with HwpxDocument.open(output) as document:
        assert document.tables.find_cell_by_label("성명")["matches"][0]["target_cell"]["text"] == value


@pytest.mark.parametrize("labels,values", [
    (("성명", "성명"), {"성명": "새 값"}),
    (("성명", "소속"), {"성명": "새 값", "없는 라벨": "값"}),
    (("성명", "소속"), {}),
])
def test_ambiguous_missing_or_empty_requests_preserve_both_files(tmp_path, labels, values):
    source, output = tmp_path / "input.hwpx", tmp_path / "out.hwpx"
    original = _form(source, labels)
    output.write_bytes(b"existing output")
    with pytest.raises(ValueError):
        example.fill_existing_form(source, output, values)
    assert source.read_bytes() == original
    assert output.read_bytes() == b"existing output"


@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink"])
def test_output_aliases_cannot_replace_source(tmp_path, alias):
    source, output = tmp_path / "input.hwpx", tmp_path / "out.hwpx"
    original = _form(source)
    if alias == "same":
        output = source
    elif alias == "symlink":
        output.symlink_to(source)
    else:
        output.hardlink_to(source)
    with pytest.raises(ValueError, match="different files"):
        example.fill_existing_form(source, output, {"성명": "새 값"})
    assert source.read_bytes() == original


def test_reopen_detects_a_success_report_without_the_requested_change(tmp_path, monkeypatch):
    source, output = tmp_path / "input.hwpx", tmp_path / "out.hwpx"
    original = _form(source)
    output.write_bytes(b"existing output")
    # A lying applied_count must not be enough to publish an unchanged result.
    monkeypatch.setattr(TablesNamespace, "fill_by_path", lambda self, mappings: {
        "applied": [], "failed": [], "applied_count": len(mappings), "failed_count": 0,
    })
    with pytest.raises(ValueError, match="content verification"):
        example.fill_existing_form(source, output, {"성명": "새 값"})
    assert source.read_bytes() == original
    assert output.read_bytes() == b"existing output"


def test_patch_downgrade_never_publishes(tmp_path, monkeypatch):
    source, output = tmp_path / "input.hwpx", tmp_path / "out.hwpx"
    original = _form(source)
    output.write_bytes(b"existing output")

    def refuse(self, path, **kwargs):
        assert kwargs["mode"] == "patch" and kwargs["fallback"] == "error"
        raise PreservationDowngradeError(
            requested_mode="patch", achieved_grade="rebuild", offending_parts=("unexpected.xml",),
            suggestion="Use a supported patch operation.",
        )

    monkeypatch.setattr(HwpxDocument, "save_to_path", refuse)
    with pytest.raises(PreservationDowngradeError):
        example.fill_existing_form(source, output, {"성명": "새 값"})
    assert source.read_bytes() == original
    assert output.read_bytes() == b"existing output"


def test_split_run_replacement_is_not_silently_counted_as_a_completed_edit(tmp_path):
    source = tmp_path / "input.hwpx"
    with HwpxDocument.new() as document:
        paragraph = document.add_paragraph("앞")
        paragraph.add_run("뒤")
        document.save_to_path(source)
    with HwpxDocument.open(source) as document:
        assert document.text.replace("앞뒤", "교체") == 0
        assert "앞뒤" in document.text.plain()


def test_wrong_prior_value_refuses_before_mutation(tmp_path):
    source, output = tmp_path / "input.hwpx", tmp_path / "out.hwpx"
    original = _form(source)
    output.write_bytes(b"existing output")
    with pytest.raises(ValueError, match="unexpected current value"):
        example.fill_existing_form(source, output, {"성명": "새 값"}, expected_values={"성명": "다른 값"})
    assert source.read_bytes() == original
    assert output.read_bytes() == b"existing output"
