# SPDX-License-Identifier: Apache-2.0
"""A document carrying an XML comment or processing instruction still saves.

2026-11 audit ENG-04: such a document opened and passed the open-safety check,
but every save -- one with no edit too -- ended in ``TypeError: argument of
type 'cython_function_or_method' is not iterable`` when the node sat in
``header.xml`` or in a paragraph that has a line cache. The save-time checks
read a comment's ``tag`` (a function, not a string) as an element name.
"""

from __future__ import annotations

import io
import zipfile
from typing import Callable

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.tools.document_merge import append_document
from hwpx.tools.package_validator import validate_editor_open_safety, validate_package

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
SECTION = "Contents/section0.xml"
HEADER = "Contents/header.xml"
TEXT = "줄 배치 캐시가 있는 문단"
ONE_LINE = (
    '<hp:linesegarray><hp:lineseg textpos="0" vertpos="0" vertsize="1000" textheight="1000" '
    'baseline="850" spacing="600" horzpos="0" horzsize="42520" flags="393216"/></hp:linesegarray>'
)


def _comment() -> etree._Comment:
    return etree.Comment("c")


def _pi() -> etree._ProcessingInstruction:
    return etree.ProcessingInstruction("x", "y")


def _cached(tree: etree._Element) -> etree._Element:
    return next(p for p in tree.iter(f"{HP}p") if p.find(f"{HP}linesegarray") is not None)


CASES: dict[str, tuple[str, Callable[[etree._Element], None]]] = {
    "comment in a run of a cached paragraph": (SECTION, lambda t: _cached(t).find(f"{HP}run").append(_comment())),
    "comment under a cached paragraph": (SECTION, lambda t: _cached(t).insert(0, _comment())),
    "PI in a run of a cached paragraph": (SECTION, lambda t: _cached(t).find(f"{HP}run").append(_pi())),
    "comment between paragraphs": (SECTION, lambda t: _cached(t).addprevious(_comment())),
    "comment between cells": (SECTION, lambda t: t.find(f".//{HP}tr").insert(0, _comment())),
    "comment between rows": (SECTION, lambda t: t.find(f".//{HP}tr").addprevious(_comment())),
    "comment in a cell": (SECTION, lambda t: t.find(f".//{HP}tc/{HP}subList").insert(0, _comment())),
    "comment in hp:t": (SECTION, lambda t: _cached(t).find(f".//{HP}t").append(_comment())),
    "comment under hh:refList": (HEADER, lambda t: t.find(f"{HH}refList").append(_comment())),
    "comment in hh:paraPr": (HEADER, lambda t: t.find(f".//{HH}paraPr").append(_comment())),
    "comment in hh:charPr": (HEADER, lambda t: t.find(f".//{HH}charPr").append(_comment())),
    "PI under hh:head": (HEADER, lambda t: t.append(_pi())),
}


def _base() -> bytes:
    doc = HwpxDocument.new()
    doc.add_paragraph(TEXT)
    doc.add_table(2, 2).cell(0, 0).text = "칸"
    return doc.to_bytes()


def _source(part: str, mutate: Callable[[etree._Element], None]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(_base())) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == SECTION:
                marker = f"<hp:t>{TEXT}</hp:t></hp:run>".encode()
                assert payload.count(marker) == 1
                payload = payload.replace(marker, marker + ONE_LINE.encode())
            if info.filename == part:
                tree = etree.fromstring(payload)
                mutate(tree)
                payload = etree.tostring(tree, xml_declaration=True, encoding="UTF-8", standalone=True)
                assert b"<!--c-->" in payload or b"<?x y?>" in payload
            method = zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED
            target.writestr(zipfile.ZipInfo(info.filename, info.date_time), payload, compress_type=method)
    return out.getvalue()


@pytest.mark.parametrize("case", list(CASES))
def test_a_document_with_a_comment_or_pi_saves_unchanged_and_after_an_edit(case: str) -> None:
    source = _source(*CASES[case])
    assert validate_editor_open_safety(source).ok

    unchanged = HwpxDocument.open(source).to_bytes()
    # nothing was edited, so the part and its comment are as they were
    part = CASES[case][0]
    with zipfile.ZipFile(io.BytesIO(source)) as before, zipfile.ZipFile(io.BytesIO(unchanged)) as after:
        assert before.read(part) == after.read(part)

    doc = HwpxDocument.open(source)
    doc.add_paragraph("더한 문단")
    edited = doc.to_bytes()
    assert validate_editor_open_safety(edited).ok
    assert "더한 문단" in HwpxDocument.open(edited).paragraphs[-1].text


@pytest.mark.parametrize("case", list(CASES))
def test_the_validators_read_a_document_with_a_comment_or_pi(case: str) -> None:
    source = _source(*CASES[case])

    assert validate_package(source).ok
    assert validate_editor_open_safety(source).ok


def test_appending_a_document_with_comments_to_another() -> None:
    target = HwpxDocument.new()
    target.add_paragraph("받는 문서")
    source = HwpxDocument.open(_source(*CASES["comment under hh:refList"]))

    append_document(target, source)

    assert TEXT in "\n".join(paragraph.text for paragraph in HwpxDocument.open(target.to_bytes()).paragraphs)
