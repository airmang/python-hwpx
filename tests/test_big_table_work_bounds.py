"""Work that grew with the square of a table's size, bounded by counting it (not by timing).

A 5,277-row table converted by Hancom (rhwp sample ``issue2063_huge_cellbreak_table``) took
87-109 s for one ``insert_rows`` and over 6 minutes for ``to_bytes``:

- the character-shape cache stamped the header's ``hh:charProperties`` element by ``id()`` of an
  lxml proxy it did not keep, so a freed proxy came back with another id and every lookup parsed
  every shape again -- and a table's page estimate looks a shape up for each character run;
- writing a section or header moved every child of the parsed root into a new root carrying the
  compat namespace declarations; lxml rewrites the namespace references of every node it moves,
  which grew with the square of a section holding one big table.
"""

from __future__ import annotations

import gc
import zipfile
from pathlib import Path

from lxml import etree

import hwpx.oxml.run as run_module
from hwpx import HwpxDocument
from hwpx.layout import pages
from hwpx.opc.xml_utils import parse_xml
from hwpx.oxml.namespaces import HWPML_COMPAT_ROOT_NAMESPACES, serialize_compat_root

FIXTURES = Path(__file__).parent / "fixtures"


def _big_table_document(rows: int) -> HwpxDocument:
    doc = HwpxDocument.new()  # no seed: a seeded document installs an id source until closed
    table = doc.add_table(rows, 4)
    bold = doc.styles.ensure_run(bold=True)
    for row in range(rows):
        table.set_cell_text(row, 0, f"행 {row}")
        table.cell(row, 1).paragraphs[0].add_run("굵게", char_pr_id_ref=bold)
    return HwpxDocument.open(doc.to_bytes())


def test_character_shapes_are_parsed_once_however_often_they_are_looked_up(monkeypatch) -> None:
    doc = HwpxDocument.open(FIXTURES / "hancom_saved" / "fill_image_left_top.hwpx")
    calls = []
    original = run_module._char_property_entries
    monkeypatch.setattr(run_module, "_char_property_entries", lambda element: calls.append(1) or original(element))
    ids = list(doc.styles.char_properties)
    for _ in range(50):
        for key in ids:
            gc.collect()  # the old stamp broke when lxml freed the proxy between lookups
            doc.styles.char_property(key)
    assert len(calls) <= 1


def test_a_changed_shape_is_still_read_again(monkeypatch) -> None:
    doc = HwpxDocument.new()
    first = doc.styles.char_property("0")
    assert first is not None
    definition = next(iter(doc.oxml.headers[0].element.iter("{http://www.hancom.co.kr/hwpml/2011/head}charPr")))
    definition.set("height", "2000")
    assert doc.styles.char_property("0").attributes["height"] == "2000"


def test_a_table_estimate_looks_shapes_up_a_fixed_number_of_times(monkeypatch) -> None:
    looked: list[object] = []
    counts = []
    for rows in (40, 160):
        doc = _big_table_document(rows)
        root = doc.oxml
        original = type(root).char_property

        def counting(self, key, _original=original):
            looked.append(key)
            return _original(self, key)

        monkeypatch.setattr(type(root), "char_property", counting)
        looked.clear()
        pages._rows_height(pages._Measure(root), doc.tables.all[0].element)
        counts.append(len(looked))
        monkeypatch.undo()
    assert 0 < counts[0] == counts[1]  # not one per cell: four times the rows, the same lookups


def test_a_table_saved_shorter_than_its_rows_is_measured_once_per_insertion(monkeypatch) -> None:
    # Hancom saves a table split across pages with the height of its first page's part; the row
    # insertion keeps that height, so it need not measure the rows again after the edit.
    doc = _big_table_document(30)
    table = doc.tables.all[0]
    measured = []
    original = type(table)._rows_height
    monkeypatch.setattr(type(table), "_rows_height", lambda self: measured.append(1) or original(self))
    sz = "{http://www.hancom.co.kr/hwpml/2011/paragraph}sz"
    table.element.find(sz).set("height", "100")
    doc.tables.insert_rows(table, 29, 1)
    assert len(measured) == 1 and table.element.find(sz).get("height") == "100"
    measured.clear()
    table.element.find(sz).set("height", "999999")  # taller than its rows: grows by the new row
    doc.tables.insert_rows(table, 30, 1)
    assert len(measured) == 2 and int(table.element.find(sz).get("height")) > 999999


def test_writing_a_part_does_not_move_its_children() -> None:
    data = zipfile.ZipFile(FIXTURES / "hancom_saved" / "fill_image_left_top.hwpx").read("Contents/section0.xml")
    for root in (etree.fromstring(data), parse_xml(data)):  # as read: hp10 bound to 2016, then normalised to 2011
        children = list(root)
        written = serialize_compat_root(root)
        assert list(root) == children  # still there: serialized in place, not moved into a new root
        again = etree.fromstring(written)
        assert dict(again.nsmap) == HWPML_COMPAT_ROOT_NAMESPACES


def _moved(root):
    wrapped = etree.Element(root.tag, nsmap=HWPML_COMPAT_ROOT_NAMESPACES)
    wrapped.attrib.update(root.attrib)
    wrapped.text, wrapped.tail = root.text, root.tail
    for child in root:
        wrapped.append(child)
    return etree.tostring(wrapped, encoding="UTF-8", xml_declaration=True, standalone=True)


def test_writing_in_place_gives_the_bytes_moving_gave() -> None:
    parts = 0
    for path in sorted((FIXTURES / "hancom_saved").glob("*.hwpx"))[::40]:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if name.startswith("Contents/section") or name == "Contents/header.xml":
                    data = archive.read(name)
                    for parse in (etree.fromstring, parse_xml):
                        assert serialize_compat_root(parse(data)) == _moved(parse(data)), (path.name, name)
                        parts += 1
    assert parts > 50
    hp, hs = "http://www.hancom.co.kr/hwpml/2011/paragraph", "http://www.hancom.co.kr/hwpml/2011/section"
    for xml in (
        f'<hs:sec xmlns:hs="{hs}" xmlns:x="urn:x"><x:a/><hs:b>t</hs:b></hs:sec>',  # a prefix outside the set, used
        f'<hs:sec xmlns:hs="{hs}" a="1&gt;2"><hs:b>t</hs:b>tail</hs:sec>',
        f'<hs:sec xmlns:hs="{hs}" xmlns:hp="{hp}" xmlns:hp10="{hp}"><hp10:p/><hp:p a="hp10:x"/></hs:sec>',
        f'<hs:sec xmlns:hs="{hs}" xmlns:hp="{hp}" xmlns:hp10="{hp}"><hp:p/></hs:sec>',  # hp10 rebound, unused
        f'<sec xmlns="urn:d" xmlns:hp="{hp}"><hp:p/></sec>',
        f'<hs:sec xmlns:hs="{hs}"/>',
    ):
        assert serialize_compat_root(etree.fromstring(xml)) == _moved(etree.fromstring(xml)), xml


def test_a_big_table_row_insertion_saves_the_same_bytes_and_reopens() -> None:
    doc = _big_table_document(150)
    table = doc.tables.all[0]
    doc.tables.insert_rows(table, 149, 2)
    data = doc.to_bytes()
    again = HwpxDocument.open(data)
    assert again.tables.all[0].row_count == 152
    assert not again.validate().issues
    assert again.to_bytes() == data
