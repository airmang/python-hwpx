# SPDX-License-Identifier: Apache-2.0
"""Caller-selected table-wrapper text removal stays inside its byte boundary."""
from __future__ import annotations

import io
from importlib import import_module
from pathlib import Path
from zipfile import ZipFile

import pytest
from lxml import etree

from hwpx.document import HwpxDocument

patch = import_module("hwpx.table_patch")
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _package(text=" A & B ", *, prefix="hp", cache=True, same_run=False, extra=False, next_paragraph=False):
    document = HwpxDocument.new()
    table = document.add_table(1, 1)
    table.cell(0, 0).text = "cell text"
    wrapper = table.element.getparent().getparent()
    if next_paragraph:
        wrapper = document.add_paragraph().element
    run = table.element.getparent() if same_run else etree.SubElement(wrapper, HP + "run", charPrIDRef="0")
    etree.SubElement(run, HP + "t").text = text
    if extra:
        etree.SubElement(run, HP + "fieldEnd", beginIDRef="123")
    if cache:
        etree.SubElement(wrapper, HP + "linesegarray")
    data = document.to_bytes()
    if prefix == "hp":
        return data
    output = io.BytesIO()
    with ZipFile(io.BytesIO(data)) as source, ZipFile(output, "w") as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename.endswith((".xml", ".hpf")):
                payload = payload.replace(b"hp:", prefix.encode() + b":").replace(b"xmlns:hp=", b"xmlns:" + prefix.encode() + b"=")
            target.writestr(info, payload)
    return output.getvalue()


def _members(data):
    with ZipFile(io.BytesIO(data)) as package:
        return {name: package.read(name) for name in package.namelist()}


def _section_variant(source, before, after):
    output = io.BytesIO()
    with ZipFile(io.BytesIO(source)) as package, ZipFile(output, "w") as target:
        for info in package.infolist():
            data = package.read(info.filename)
            if info.filename == "Contents/section0.xml":
                assert before in data
                data = data.replace(before, after)
            target.writestr(info, data)
    return output.getvalue()


@pytest.mark.parametrize("prefix", ["hp", "q"])
@pytest.mark.parametrize("same_run", [False, True])
def test_selector_removes_only_matching_wrapper_text(prefix, same_run):
    source = _package(prefix=prefix, same_run=same_run)
    seen = []

    def select(text):
        seen.append(text)
        return text == "A & B"

    result = patch.strip_trailing_table_text(source, predicate=select)
    assert seen == ["A & B"] and len(result.applied) == 1
    before, after = _members(source), _members(result.data)
    assert {name for name in before if before[name] != after[name]} == {"Contents/section0.xml"}
    assert b"cell text" in after["Contents/section0.xml"] and b"A &amp; B" not in after["Contents/section0.xml"]
    etree.fromstring(after["Contents/section0.xml"])
    with HwpxDocument.open(result.data) as reopened:
        assert reopened.tables[0].cell(0, 0).text == "cell text"


@pytest.mark.parametrize("kwargs", [{"cache": False}, {"extra": True}, {"next_paragraph": True}])
def test_ambiguous_controls_missing_cache_and_other_paragraphs_are_preserved(kwargs):
    source = _package(**kwargs)
    result = patch.strip_trailing_table_text(source, predicate=lambda _: True)
    assert result.data == source and not result.applied


def test_declined_selection_and_external_noop_are_byte_identical():
    path = Path(__file__).parent / "fixtures" / "m2_corpus" / "public_official_table.hwpx"
    for source in [_package(), path.read_bytes()]:
        result = patch.strip_trailing_table_text(source, predicate=lambda _: False)
        assert result.data == source and not result.applied


@pytest.mark.parametrize("before,after", [
    (b"<hp:t> A &amp; B </hp:t>", b'<x:t xmlns:x="urn:opaque"> A &amp; B </x:t>'),
    (b"<hp:linesegarray/>", b"<hp:linesegarrayOpaque/>"),
    (b"<hp:linesegarray/>", b'<x:linesegarray xmlns:x="urn:opaque"/>'),
])
def test_foreign_text_and_cache_lookalikes_are_preserved(before, after):
    source = _section_variant(_package(), before, after)
    result = patch.strip_trailing_table_text(source, predicate=lambda _: True)
    assert result.data == source and not result.applied


def test_non_whitespace_outside_runs_is_preserved():
    source = _section_variant(_package(), b"</hp:tbl></hp:run><hp:run",
                              b"</hp:tbl></hp:run>raw tail<hp:run")
    result = patch.strip_trailing_table_text(source, predicate=lambda _: True)
    assert result.data == source and not result.applied


@pytest.mark.parametrize("uri", [b"http://www.hancom.co.kr/hwpml/2016/paragraph",
                                 b"http://www.owpml.org/owpml/2024/paragraph"])
def test_supported_namespace_versions_keep_original_bytes(uri):
    source = _section_variant(_package(prefix="q"), HP[1:-1].encode(), uri)
    result = patch.strip_trailing_table_text(source, predicate=lambda text: text == "A & B")
    assert len(result.applied) == 1
    assert uri in _members(result.data)["Contents/section0.xml"]
    assert b"A &amp; B" not in _members(result.data)["Contents/section0.xml"]


def test_cdata_that_looks_like_markup_remains_text_for_selection():
    source = _section_variant(_package(), b"<hp:t> A &amp; B </hp:t>",
                              b"<hp:t><![CDATA[ A <hp:tbl> B & C ]]></hp:t>")
    result = patch.strip_trailing_table_text(source, predicate=lambda text: text == "A <hp:tbl> B & C")
    assert len(result.applied) == 1
    etree.fromstring(_members(result.data)["Contents/section0.xml"])


def test_predicate_failure_keeps_existing_output(tmp_path):
    destination = tmp_path / "output.hwpx"
    destination.write_bytes(b"existing output")

    def fail(text):
        raise RuntimeError("selection failed")

    with pytest.raises(RuntimeError, match="selection failed"):
        patch.strip_trailing_table_text(_package(), predicate=fail, output_path=destination)
    assert destination.read_bytes() == b"existing output"


def test_legacy_caption_rule_keeps_its_byte_output_and_report():
    source = _package("(1) alpha")
    result = patch.strip_trailing_table_captions(source)
    original = _members(source)
    expected = original["Contents/section0.xml"].replace(
        b'</hp:tbl></hp:run><hp:run charPrIDRef="0"><hp:t>(1) alpha</hp:t></hp:run>',
        b'</hp:tbl></hp:run>')
    assert expected != original["Contents/section0.xml"]
    assert _members(result.data)["Contents/section0.xml"] == expected
    assert len(result.applied) == 1 and result.applied[0].original_text == "(1) alpha"
