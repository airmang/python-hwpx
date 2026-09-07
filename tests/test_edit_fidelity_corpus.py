# SPDX-License-Identifier: Apache-2.0
"""Bounded editing regression on pinned, externally authored hwpxlib inputs.

Run with pytest --basetemp=<evidence directory> to retain exact output files
and edit-results.json for a separate Hancom observer. This is a structural
regression, never a visual gate or a corpus-wide completion rate.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument, validate_editor_open_safety, validate_package
from hwpx.mutation_report import read_archive_members
from hwpx.plan import apply_edit_plan

ROOT = Path(__file__).resolve().parents[1]
example_spec = importlib.util.spec_from_file_location("edit_example", ROOT / "examples/edit_existing_form.py")
assert example_spec and example_spec.loader
example = importlib.util.module_from_spec(example_spec)
example_spec.loader.exec_module(example)
CORPUS = ROOT / "tests/fixtures/hwpxlib_corpus"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
SECTION = "Contents/section0.xml"

# Fixed before execution: both supported operations and deliberately unsupported
# boundaries. The broad corpus and authoring/oracle probes are separate suites.
CASES = [
    {"id": "mixed-runs", "file": "reader_writer__sample1.hwpx", "kind": "text",
     "search": "수학", "value": "과학", "count": 2, "expected": "completed",
     "reason": "body text with mixed character styles and untouched neighboring runs"},
    {"id": "cross-run-refusal", "file": "reader_writer__sample1.hwpx", "kind": "text",
     "search": "우리는 수학", "value": "교체", "count": 1, "expected": "safe_refusal",
     "refusal": "expected 1 replacements, got 0",
     "reason": "search crosses run boundaries: documented unsupported replacement"},
    {"id": "table-cell", "file": "tool__textextractor__Table.hwpx", "kind": "form",
     "label": "개똥이", "value": "90", "expected": "completed",
     "reason": "external table data; adjacent values and table structure must survive"},
    {"id": "long-cell", "file": "tool__textextractor__Table.hwpx", "kind": "form",
     "label": "개똥이", "value": "긴 검토 문장입니다. " * 60, "expected": "completed",
     "reason": "long cell content; layout and pagination require a separate oracle"},
    {"id": "institution-form", "file": "error__20250523__프로젝트 계획서.hwpx", "kind": "form",
     "label": "작성자", "value": "검토 담당", "expectedValue": "한 글", "expected": "completed",
     "reason": "external project proposal: confirmed author field beside a merged label"},
    {"id": "spacer-target-refusal", "file": "error__20250523__프로젝트 계획서.hwpx", "kind": "form",
     "label": "작성일자", "value": "2026-09-07", "expectedValue": "0000년 00월 00일",
     "expected": "safe_refusal", "refusal": "unexpected current value",
     "reason": "Hancom review exposed a narrow spacer before the date; inspect and select an explicit path instead"},
    {"id": "merged-label", "file": "reader_writer__SimpleTable.hwpx", "kind": "form",
     "label": "1", "value": "새 값", "expectedValue": "2", "expected": "completed",
     "reason": "one merged label was wrongly counted twice; cross its full span to the adjacent cell"},
    {"id": "duplicate-label-refusal", "file": "tool__textextractor__Table.hwpx", "kind": "form",
     "label": "77", "value": "새 값", "expected": "safe_refusal",
     "refusal": "expected one target for '77'; got 2",
     "reason": "distinct physical cells with repeated text remain ambiguous after merged-cell deduplication"},
    {"id": "repeated-rows", "file": "tool__textextractor__Table.hwpx", "kind": "rows",
     "row": 2, "count": 2, "expected": "completed",
     "reason": "clone a data row twice; verify row addresses, styles and untouched content"},
    {"id": "merged-row-refusal", "file": "reader_writer__SimpleTable.hwpx", "kind": "rows",
     "row": 0, "count": 1, "expected": "safe_refusal",
     "refusal": "clone source row must have rowSpan==1 cells",
     "reason": "rowSpan source is outside insert_row_by_clone; block cloning is a separate API"},
]


def _fingerprint(node):
    """Exact XML meaning, including text, tails, attributes, child order, comments.

    Prefix spelling is ignored by Clark names; no arbitrary text/attribute/ID
    normalization is permitted here.
    """
    tag = node.tag if isinstance(node.tag, str) else str(node.tag)
    return (tag, tuple(sorted(node.attrib.items())), node.text, node.tail,
            tuple(_fingerprint(child) for child in node))


def _remove_layout_cache(root) -> int:
    nodes = list(root.iter(HP + "linesegarray"))
    for node in nodes:
        node.getparent().remove(node)
    return len(nodes)


def _compare_modified_section(before: bytes, after: bytes, case: dict) -> dict:
    original = etree.fromstring(before)
    actual = etree.fromstring(after)
    expected = copy.deepcopy(original)
    allowances = {"beforeLayoutCaches": _remove_layout_cache(expected),
                  "afterLayoutCaches": _remove_layout_cache(actual)}
    if case["kind"] == "text":
        changes = 0
        for paragraph in expected.findall(HP + "p"):
            for run in paragraph.findall(HP + "run"):
                for text in run.findall(HP + "t"):
                    if text.text and case["search"] in text.text:
                        changes += text.text.count(case["search"])
                        text.text = text.text.replace(case["search"], case["value"])
        assert changes == case["count"]
    elif case["kind"] == "form":
        candidates = []
        for table in expected.iter(HP + "tbl"):
            for row in table.findall(HP + "tr"):
                cells = row.findall(HP + "tc")
                for i, cell in enumerate(cells[:-1]):
                    if "".join(cell.itertext()) == case["label"]:
                        candidates.append(cells[i + 1])
        assert len(candidates) == 1
        target = candidates[0]
        target.set("dirty", "1")  # set_cell_text marks this edited cell only
        texts = list(target.iter(HP + "t"))
        if not texts:
            runs = list(target.iter(HP + "run"))
            assert len(runs) == 1 and len(runs[0]) == 0
            texts = [etree.SubElement(runs[0], HP + "t")]
        assert len(texts) == 1, "fixture requires an explicit richer-cell expectation"
        texts[0].text = case["value"]
    else:
        old_table = next(expected.iter(HP + "tbl"))
        new_table = next(actual.iter(HP + "tbl"))
        old_rows, new_rows = old_table.findall(HP + "tr"), new_table.findall(HP + "tr")
        row_index, count = case["row"], case["count"]
        assert len(new_rows) == len(old_rows) + count
        reference = old_rows[row_index]
        reference_ids = [p.get("id") for p in reference.iter(HP + "p")]
        for i in range(count):
            clone = new_rows[row_index + 1 + i]
            clone_ids = [p.get("id") for p in clone.iter(HP + "p")]
            assert len(clone_ids) == len(reference_ids)
            assert all(a != b for a, b in zip(clone_ids, reference_ids))
            # Check copied formatting and content; only rowAddr and paragraph id
            # may differ in the inserted row. No object/reference IDs are masked.
            normalized = copy.deepcopy(clone)
            for p, old_id in zip(normalized.iter(HP + "p"), reference_ids):
                p.set("id", old_id)
            for cell_addr in normalized.iter(HP + "cellAddr"):
                assert int(cell_addr.get("rowAddr")) == row_index + i + 1
                cell_addr.set("rowAddr", str(row_index))
            assert _fingerprint(normalized) == _fingerprint(reference)
            new_table.remove(clone)
        # Reverse only the documented count/address changes, then require the
        # rest of the section, including other objects and tables, to match.
        assert int(new_table.get("rowCnt")) == int(old_table.get("rowCnt")) + count
        new_table.set("rowCnt", old_table.get("rowCnt"))
        for row in new_table.findall(HP + "tr")[row_index + 1:]:
            for address in row.iter(HP + "cellAddr"):
                address.set("rowAddr", str(int(address.get("rowAddr")) - count))
    assert _fingerprint(expected) == _fingerprint(actual), "unexpected change inside edited section"
    return {"status": "passed", "comparison": "semantic; only requested edits and layout-cache removal allowed",
            **allowances}


def _run(case, source: Path, output: Path) -> dict:
    if case["kind"] == "form":
        expected = {case["label"]: case["expectedValue"]} if "expectedValue" in case else None
        return example.fill_existing_form(
            source, output, {case["label"]: case["value"]}, expected_values=expected
        )
    if case["kind"] == "text":
        with HwpxDocument.open(source) as document:
            count = document.text.replace(case["search"], case["value"])
            if count != case["count"]:
                raise ValueError(f"expected {case['count']} replacements, got {count}")
            report = document.save_to_path(output, mode="patch", fallback="error", return_report=True)
        with HwpxDocument.open(output) as document:
            assert document.text.plain().count(case["value"]) == case["count"]
        return report.to_dict()
    report = apply_edit_plan({
        "schemaVersion": "hwpx.edit-plan/v1", "source": str(source), "output": str(output),
        "steps": [{"id": "rows", "op": "apply_table_ops", "args": {"ops": [{
            "op": "insert_row_by_clone", "table_index": 0,
            "ref_row": case["row"], "count": case["count"],
        }]}}],
    })
    if not report.ok:
        raise ValueError(str(report.to_dict()))
    return report.to_dict()


def test_external_edit_cases(tmp_path):
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    sources = {sample["file"]: sample for sample in manifest["samples"]}
    results = []
    for case in CASES:
        source = CORPUS / case["file"]
        original = source.read_bytes()
        source_hash = hashlib.sha256(original).hexdigest()
        assert source_hash == sources[case["file"]]["sha256"]
        # Keep an exact copy alongside each output for the independent observer.
        (tmp_path / f"{case['id']}-original.hwpx").write_bytes(original)
        output = tmp_path / f"{case['id']}.hwpx"
        output.write_bytes(b"existing output")
        record = {**case, "sourceSha256": source_hash,
                  "sourcePath": sources[case["file"]]["source_path"],
                  "visual": "not_performed", "outputSha256": None}
        try:
            record["operationReport"] = _run(case, source, output)
            payload = output.read_bytes()
            record["outputSha256"] = hashlib.sha256(payload).hexdigest()
            old, new = read_archive_members(original), read_archive_members(payload)
            assert old.keys() == new.keys()
            changed = [name for name in old if old[name] != new[name]]
            assert changed == [SECTION]
            record["untouchedParts"] = {"verified": len(old) - 1, "changed": 0}
            record["withinModifiedParts"] = _compare_modified_section(old[SECTION], new[SECTION], case)
            assert validate_package(payload).ok
            assert validate_editor_open_safety(payload).ok
            with HwpxDocument.open(payload) as reopened:
                assert reopened.sections
            record["structural"] = "passed"
            record["outcome"] = "completed"
        except Exception as exc:  # noqa: BLE001 -- retain every case's failure, then fail the gate
            intact = output.read_bytes() == b"existing output"
            expected_refusal = (
                isinstance(exc, ValueError) and case["expected"] == "safe_refusal"
                and case["refusal"] in str(exc)
            )
            record["outcome"] = (
                "safe_refusal" if intact and expected_refusal
                else "excessive_refusal" if intact and case["expected"] == "completed"
                else "unexpected_failure" if intact else "incorrect_output"
            )
            record["error"] = f"{type(exc).__name__}: {exc}"
            if not intact:
                record["outputSha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
        record["sourceUnchanged"] = source.read_bytes() == original
        assert record["sourceUnchanged"]
        results.append(record)
    report = {"sourceRepo": manifest["source_repo"], "pinnedRef": manifest["pinned_ref"],
              "selection": "bounded mixed-run, label/merged-cell and row-clone regression; not full corpus coverage",
              "results": results, "outcomes": dict(Counter(r["outcome"] for r in results))}
    (tmp_path / "edit-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    failures = [f"{r['id']}: {r.get('error', r['outcome'])}" for r in results if r["outcome"] != r["expected"]]
    assert not failures, "\n".join(failures)


def test_section_guard_rejects_unrequested_style_changes(tmp_path):
    case = CASES[0]
    source = CORPUS / case["file"]
    output = tmp_path / "out.hwpx"
    _run(case, source, output)
    original = read_archive_members(source.read_bytes())[SECTION]
    edited = read_archive_members(output.read_bytes())[SECTION]
    _compare_modified_section(original, edited, case)
    root = etree.fromstring(edited)
    next(root.iter(HP + "run")).set("charPrIDRef", "99999")
    with pytest.raises(AssertionError, match="unexpected change"):
        _compare_modified_section(original, etree.tostring(root), case)
