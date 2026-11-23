# SPDX-License-Identifier: Apache-2.0
"""A section's settings (``hp:secPr``) stay in its first paragraph.

Hancom reads them only from the first paragraph: Hangul 2024 opened a section whose ``hp:secPr`` was
in its second paragraph with default paper and margins, and saved a default ``hp:secPr`` in the first
one. So the open-safety check reports that shape (``section-properties-not-first``), the save refuses
it, ``hwpx-repair`` moves the settings back, and every public path that puts something in front of a
section or moves its first paragraph keeps them there.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxError
from hwpx.tools.document_merge import append_document, insert_document
from hwpx.tools.package_validator import validate_editor_open_safety, validate_package
from hwpx.tools.repair import repair_repack

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
LEFT, TOP = 11339, 8504  # 40 mm, 30 mm: not the defaults (8504, 5668)


def _doc() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.add_paragraph("하나")
    doc.page.set_margins(left=LEFT, top=TOP)
    doc.page.set_columns(2)
    doc.add_paragraph("둘")
    doc.add_paragraph("셋")
    return doc


def _settings_in_first_run(doc: HwpxDocument) -> None:
    for section in doc.sections:
        first = section.element.find(f"{_HP}p")
        assert first is not None
        first_run = first.find(f"{_HP}run")
        holders = [p for p in section.element.findall(f"{_HP}p") if p.find(f"{_HP}run/{_HP}secPr") is not None]
        assert holders == [first]
        assert first_run is not None and first_run.find(f"{_HP}secPr") is not None
        # the columns go with it (Hancom writes hp:ctrl/hp:colPr in the first paragraph too)
        top_columns = [c for p in section.element.findall(f"{_HP}p") for c in p.iter(f"{_HP}colPr")
                       if p.find(f"{_HP}run/{_HP}secPr") is not None or p is first]
        assert all(any(c is x for x in first.iter(f"{_HP}colPr")) for c in top_columns)


def _roundtrip(doc: HwpxDocument) -> HwpxDocument:
    data = doc.to_bytes()
    assert validate_package(data).ok
    again = HwpxDocument.open(data)
    _settings_in_first_run(again)
    assert again.sections[0].properties.page_margins.left == LEFT
    assert again.sections[0].properties.page_margins.top == TOP
    return again


PATHS = {
    "insert_before text": lambda d: d.paragraphs[0].insert_before("앞"),
    "insert_before copy": lambda d: d.paragraphs[0].insert_before(),
    "insert_after copy of first": lambda d: d.paragraphs[0].insert_after(),
    "move_before first": lambda d: d.paragraphs[2].move_before(d.paragraphs[0]),
    "first move_after last": lambda d: d.paragraphs[0].move_after(d.paragraphs[-1]),
    "first remove": lambda d: d.paragraphs[0].remove(),
    "first text set": lambda d: setattr(d.paragraphs[0], "text", "바뀐 첫 글"),
    "section.insert_paragraphs(0)": lambda d: d.sections[0].insert_paragraphs(0, [d.paragraphs[2]]),
    "oxml.insert_paragraphs(0)": lambda d: d.oxml.insert_paragraphs(0, [d.paragraphs[2]], section=0),
    "insert_paragraphs(0, copy of a first paragraph)": lambda d: d.sections[0].insert_paragraphs(
        0, d.sections[0].copy_paragraph_range(0, 1)),
    "insert_paragraphs(2, copy of a first paragraph)": lambda d: d.sections[0].insert_paragraphs(
        2, d.sections[0].copy_paragraph_range(0, 0)),
    "clear_body": lambda d: d.sections[0].clear_body(),
    "insert_document before the first": lambda d: insert_document(d, _doc(), after_paragraph_index=-1),
    "append_document": lambda d: append_document(d, _doc()),
    "table move_to first offset 0": lambda d: d.add_table(2, 2).move_to(d.paragraphs[0], offset=0),
    "table copy_to first offset 0": lambda d: d.add_table(2, 2).copy_to(d.paragraphs[0], offset=0),
    "first add_table": lambda d: d.paragraphs[0].add_table(2, 2),
    "shape move_to first offset 0": lambda d: d.paragraphs[1].add_rectangle(width=2000, height=1000).move_to(
        d.paragraphs[0], offset=0),
    "add_section": lambda d: d.add_section(),
    "remove first of two sections": lambda d: (d.add_section(), d.remove_section(0)),
}


@pytest.mark.parametrize("name", list(PATHS))
def test_every_path_keeps_the_settings_in_the_first_paragraph(name: str) -> None:
    doc = _doc()
    PATHS[name](doc)
    _roundtrip(doc)


def test_insert_paragraphs_at_the_front_hands_the_settings_to_the_first_copy() -> None:
    doc = _doc()
    old_first = doc.paragraphs[0]
    inserted = doc.sections[0].insert_paragraphs(0, [doc.paragraphs[2], doc.paragraphs[1]])
    assert inserted[0].element.find(f"{_HP}run/{_HP}secPr") is not None
    assert old_first.element.find(f"{_HP}run/{_HP}secPr") is None
    assert [p.text for p in doc.sections[0].paragraphs][:3] == ["셋", "둘", old_first.text]
    # both lose their line cache: the controls in front shift every text position
    assert inserted[0].element.find(f"{_HP}linesegarray") is None


def test_a_column_layout_sharing_its_ctrl_moves_alone() -> None:
    """Some Hancom files put other controls in the hp:ctrl holding hp:colPr; the column layout goes
    to the new first paragraph in a ctrl of its own, the others stay (as insert_document did)."""

    doc = _doc()
    first = doc.paragraphs[0].element
    ctrl = next(c for c in first.iter(f"{_HP}ctrl") if c.find(f"{_HP}colPr") is not None)
    ctrl.append(ctrl.makeelement(f"{_HP}bookmark", {"name": "곁"}))
    doc.paragraphs[0].insert_before("앞")
    new_first = doc.paragraphs[0].element
    (moved,) = [c for c in new_first.iter(f"{_HP}ctrl") if c.find(f"{_HP}colPr") is not None]
    assert [c.tag for c in moved] == [f"{_HP}colPr"]
    assert first.find(f".//{_HP}bookmark") is not None and first.find(f".//{_HP}colPr") is None
    assert new_first.find(f"{_HP}run/{_HP}secPr") is not None


def _second_paragraph_shape() -> bytes:
    """The shape Hancom rejects: the settings in the section's second paragraph (made through .element)."""

    doc = _doc()
    first, second = doc.paragraphs[0].element, doc.paragraphs[1].element
    from hwpx.oxml._paragraph_text_edit import move_section_settings

    move_section_settings(first, second)
    doc.sections[0].mark_dirty()
    doc.validate_on_save = False
    return doc


def test_the_save_moves_settings_from_a_later_paragraph_and_warns() -> None:
    doc = _second_paragraph_shape()
    with pytest.warns(UserWarning, match="section-properties-not-first"):
        data = doc.to_bytes()
    again = HwpxDocument.open(data)
    _settings_in_first_run(again)
    assert again.sections[0].properties.page_margins.left == LEFT
    assert again.sections[0].properties.page_margins.top == TOP
    assert again.sections[0].element.find(f".//{_HP}linesegarray") is None
    assert [paragraph.text for paragraph in again.paragraphs[:3]] == ["하나", "둘", "셋"]


def test_a_file_6x_made_with_insert_paragraphs_at_the_front_saves_again(tmp_path) -> None:
    """6.x's ``insert_paragraphs(0, ...)`` left the settings in the old first paragraph; 7.0.0
    refused to save such a file even unchanged."""

    from lxml import etree

    good = _doc().to_bytes()
    with zipfile.ZipFile(io.BytesIO(good)) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
        infos = {info.filename: info for info in archive.infolist()}
    root = etree.fromstring(parts["Contents/section0.xml"])
    first = root.find(f"{_HP}p")
    copy = etree.fromstring(etree.tostring(first))
    for run in copy.findall(f"{_HP}run"):
        for child in list(run):
            if etree.QName(child).localname in {"secPr", "ctrl"}:
                run.remove(child)
    copy.set("id", "123")
    root.insert(0, copy)
    parts["Contents/section0.xml"] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    made = tmp_path / "made-by-6x.hwpx"
    with zipfile.ZipFile(made, "w") as archive:
        for name, payload in parts.items():
            archive.writestr(infos[name], payload)

    doc = HwpxDocument.open(made)
    out = tmp_path / "saved.hwpx"
    with pytest.warns(UserWarning, match="section-properties-not-first"):
        doc.save(out)
    assert validate_editor_open_safety(out).ok
    again = HwpxDocument.open(out)
    _settings_in_first_run(again)
    assert again.sections[0].properties.page_margins.left == LEFT


def test_the_open_safety_check_reports_the_shape(tmp_path) -> None:
    from hwpx.oxml.namespaces import HP

    good = _doc().to_bytes()
    with zipfile.ZipFile(io.BytesIO(good)) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
        infos = {info.filename: info for info in archive.infolist()}
    from lxml import etree

    root = etree.fromstring(parts["Contents/section0.xml"])
    paragraphs = root.findall(f"{HP}p")
    from hwpx.oxml._paragraph_text_edit import move_section_settings

    move_section_settings(paragraphs[0], paragraphs[1])
    parts["Contents/section0.xml"] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    bad = tmp_path / "second.hwpx"
    with zipfile.ZipFile(bad, "w") as archive:
        for name, payload in parts.items():
            archive.writestr(infos[name], payload)

    report = validate_package(bad)
    assert not report.ok
    assert any("section-properties-not-first" in issue.message for issue in report.errors)
    assert not validate_editor_open_safety(bad).ok

    fixed = tmp_path / "fixed.hwpx"
    result = repair_repack(bad, fixed)
    assert result.open_safety["ok"]
    again = HwpxDocument.open(fixed)
    _settings_in_first_run(again)
    assert again.sections[0].properties.page_margins.left == LEFT
    first = again.sections[0].element.find(f"{_HP}p")
    assert [c.get("colCount") for c in first.iter(f"{_HP}colPr")] == ["2"]
    assert [p.text for p in again.paragraphs] == [p.text for p in HwpxDocument.open(good).paragraphs]


def test_settings_in_the_first_paragraphs_later_run_stay_a_warning() -> None:
    """Hancom's own files always put hp:secPr in the first run; another run of the first paragraph has
    no Hancom evidence either way, so it stays the warning it was."""

    doc = _doc()
    first = doc.paragraphs[0].element
    runs = first.findall(f"{_HP}run")
    text_run = first.makeelement(f"{_HP}run", {"charPrIDRef": "0"})
    first.insert(list(first).index(runs[0]), text_run)
    from hwpx.tools.package_validator import _check_section_properties_location

    issues: list = []
    _check_section_properties_location(issues, "Contents/section0.xml", doc.sections[0].element)
    assert issues and all(not issue.is_error for issue in issues)
