# SPDX-License-Identifier: Apache-2.0
"""asks10h: a section's first paragraph without its column definition, and the caret Hangul opens a document at.

- Hangul 2024 opens a section whose first paragraph holds ``hp:secPr`` but no ``hp:ctrl/hp:colPr`` with
  default paper and margins, and saves a one-column definition right after ``hp:secPr``
  (``out/preview9/colpr``). Every one of the 1,271 sections of ``tests/fixtures/hancom_saved`` has one. The
  package check reports it (``section-columns-missing``) without refusing the save; ``hwpx-repair`` writes
  Hangul's definition.
- ``settings.xml``'s ``ha:CaretPosition``: Hangul opens a caret pointing at a list or paragraph that is not
  there at the body's first paragraph's text start (``0/0/16``: the section's settings and columns count 8
  each) and keeps one in a cell that is there (``out/exec7/asks10h/caret/EVIDENCE.md``)."""

from __future__ import annotations

import io
import zipfile

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxError
from hwpx.tools.package_validator import validate_editor_open_safety, validate_package
from hwpx.tools.repair import repair_repack

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _without_columns(tmp_path) -> "tuple[bytes, object]":
    with HwpxDocument.new() as doc:
        doc.add_paragraph("첫 문단")
        doc.sections[0].properties.set_page_margins(left=5669, right=5669)
        good = doc.to_bytes()
    with zipfile.ZipFile(io.BytesIO(good)) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
        infos = {info.filename: info for info in archive.infolist()}
    root = etree.fromstring(parts["Contents/section0.xml"])
    for control in list(root.iter(f"{HP}ctrl")):
        if control.find(f"{HP}colPr") is not None:
            control.getparent().remove(control)
    parts["Contents/section0.xml"] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    bad = tmp_path / "no-columns.hwpx"
    with zipfile.ZipFile(bad, "w") as archive:
        for name, payload in parts.items():
            archive.writestr(infos[name], payload)
    return good, bad


def test_the_package_check_reports_a_missing_column_definition_without_refusing_the_save(tmp_path) -> None:
    good, bad = _without_columns(tmp_path)
    assert not any("section-columns-missing" in issue.message for issue in validate_package(io.BytesIO(good)).issues)
    report = validate_package(bad)
    assert any("section-columns-missing" in issue.message for issue in report.errors)
    assert validate_editor_open_safety(bad).ok  # reported, not blocking: such a file read and saved still saves
    with HwpxDocument.open(bad) as doc:
        doc.add_paragraph("더한 문단")
        doc.to_bytes()


def test_repair_writes_hancoms_one_column_definition_after_the_settings(tmp_path) -> None:
    _good, bad = _without_columns(tmp_path)
    fixed = tmp_path / "fixed.hwpx"
    result = repair_repack(bad, fixed)
    assert result.open_safety["ok"]
    assert not any("section-columns-missing" in issue.message for issue in validate_package(fixed).issues)
    with HwpxDocument.open(fixed) as doc:
        run = doc.sections[0].element.find(f"{HP}p/{HP}run")
        names = [etree.QName(child).localname for child in run]
        assert names[:2] == ["secPr", "ctrl"]
        assert dict(run[1][0].attrib) == {"id": "", "type": "NEWSPAPER", "layout": "LEFT", "colCount": "1",
                                          "sameSz": "1", "sameGap": "0"}
        assert doc.sections[0].properties.page_margins.left == 5669


def _settings(data: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.read("settings.xml")


def test_a_new_document_s_caret_is_the_body_start_and_its_bytes_stay() -> None:
    with HwpxDocument.new() as doc:
        caret = doc.caret
        assert (caret.list_id_ref, caret.para_id_ref, caret.pos) == (0, 0, 16)
        before = _settings(doc.to_bytes())
        doc.reset_caret()
        assert _settings(doc.to_bytes()) == before
        assert b'<ha:CaretPosition listIDRef="0" paraIDRef="0" pos="16"/>' in before


def test_set_caret_counts_as_hangul_counts() -> None:
    with HwpxDocument.new() as doc:
        doc.add_paragraph("가나다")
        second = doc.add_paragraph("둘째\t문단")
        caret = doc.set_caret(second, 3)  # after the tab: Hangul counts it 8
        assert (caret.list_id_ref, caret.para_id_ref, caret.pos) == (0, 1, 2 + 8)
        assert doc.set_caret(doc.paragraphs[0], 1).pos == 16 + 1
        settings = _settings(doc.to_bytes())
        assert b'<ha:CaretPosition listIDRef="0" paraIDRef="0" pos="17"/>' in settings
        assert b"xmlns:config=" in settings  # the rest of the part stays as it was


def test_the_caret_is_set_in_the_body_only() -> None:
    with HwpxDocument.new() as doc:
        table = doc.add_paragraph("표").add_table(1, 1)
        with pytest.raises(HwpxError) as caught:
            doc.set_caret(table.rows[0].cells[0].paragraphs[0])
        assert caught.value.code == "document-caret-place-unsupported"
        with pytest.raises(HwpxError) as caught:
            doc.set_caret(doc.paragraphs[0], 99)
        assert caught.value.code == "paragraph-range-invalid"


def test_a_caret_pointing_at_a_paragraph_that_is_gone_goes_to_the_body_start_on_saving() -> None:
    with HwpxDocument.new() as doc:
        doc.add_paragraph("하나")
        doc.add_paragraph("둘")
        doc.add_paragraph("셋")
        doc.set_caret(doc.paragraphs[2], 1)
        doc.paragraphs[2].remove()
        reopened = HwpxDocument.open(doc.to_bytes())
        caret = reopened.caret
        assert (caret.list_id_ref, caret.para_id_ref, caret.pos) == (0, 0, 16)


def test_a_caret_in_a_cell_that_is_there_stays() -> None:
    # Hangul keeps a caret in a cell that is still there; the engine leaves a caret outside the body as it is.
    path = "tests/fixtures/hancom_saved/cell_border_2x3_base.hwpx"
    with HwpxDocument.open(path) as doc:
        before = doc.caret
        assert before.list_id_ref == 1
        reopened = HwpxDocument.open(doc.to_bytes())
        assert reopened.caret == before
