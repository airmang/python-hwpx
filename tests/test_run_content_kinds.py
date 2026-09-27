# SPDX-License-Identifier: Apache-2.0
"""``Run.content_kinds()`` — what a run holds, in a closed vocabulary."""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.oxml.namespaces import HP
from hwpx.oxml.run import RUN_CONTENT_KINDS, HwpxOxmlRun

FIXTURES = Path(__file__).resolve().parent / "fixtures"
_HP_URI = HP[1:-1]


def _run(xml_children: str) -> HwpxOxmlRun:
    document = HwpxDocument.new()
    paragraph = document.sections[0].paragraphs[0]
    element = etree.fromstring(f'<hp:run xmlns:hp="{_HP_URI}" charPrIDRef="0">{xml_children}</hp:run>')
    paragraph.element.append(element)
    return HwpxOxmlRun(element, paragraph)


@pytest.mark.parametrize(
    "children,expected",
    [
        ("", set()),
        ("<hp:t/>", set()),
        ("<hp:t></hp:t><hp:t/>", set()),
        ("<hp:t>글</hp:t>", {"text"}),
        ("<hp:t><hp:tab/></hp:t>", {"text"}),
        ("<hp:t><hp:lineBreak/></hp:t>", {"text"}),
        ("<hp:t><hp:hyphen/></hp:t>", {"text"}),
        ("<hp:t><hp:nbSpace/></hp:t>", {"text"}),
        ("<hp:t><hp:fwSpace/></hp:t>", {"text"}),
        ("<hp:t><hp:markpenBegin/>글<hp:markpenEnd/></hp:t>", {"text"}),
        ("<hp:t><hp:markpenBegin/><hp:markpenEnd/></hp:t>", set()),
        ("<hp:compose/>", {"text"}),
        ("<hp:dutmal/>", {"text"}),
        ("<hp:tbl/>", {"table"}),
        ("<hp:pic/>", {"picture"}),
        ("<hp:picture/>", {"picture"}),
        ("<hp:line/><hp:rect/><hp:ellipse/><hp:arc/>", {"shape"}),
        ("<hp:polyline/><hp:polygon/><hp:curve/><hp:connectLine/>", {"shape"}),
        ("<hp:container/><hp:drawingObject/><hp:shape/><hp:textart/>", {"shape"}),
        ("<hp:equation/>", {"equation"}),
        ("<hp:ole/>", {"ole"}),
        ("<hp:chart/>", {"chart"}),
        ("<hp:video/>", {"video"}),
        ("<hp:btn/><hp:radioBtn/><hp:checkBtn/>", {"form"}),
        ("<hp:comboBox/><hp:listBox/><hp:edit/><hp:scrollBar/>", {"form"}),
        ("<hp:ctrl/>", {"control"}),
        ("<hp:secPr/>", {"section_properties"}),
        ("<hp:audio/>", {"other"}),
        ("<hp:somethingNew/>", {"other"}),
        ("<!-- note --><hp:t>글</hp:t>", {"text"}),
        (
            "<hp:secPr/><hp:ctrl/><hp:t>글</hp:t><hp:tbl/><hp:pic/>",
            {"section_properties", "control", "text", "table", "picture"},
        ),
    ],
)
def test_content_kinds_classifies_the_direct_children(children: str, expected: set[str]) -> None:
    kinds = _run(children).content_kinds()

    assert isinstance(kinds, frozenset)
    assert kinds == expected
    assert kinds <= RUN_CONTENT_KINDS


def test_content_kinds_only_looks_at_direct_children() -> None:
    run = _run("<hp:ctrl><hp:header><hp:subList><hp:p><hp:run><hp:t>글</hp:t></hp:run></hp:p></hp:subList></hp:header></hp:ctrl>")
    assert run.content_kinds() == {"control"}


def test_the_vocabulary_is_closed() -> None:
    assert RUN_CONTENT_KINDS == frozenset(
        {
            "text",
            "table",
            "picture",
            "shape",
            "equation",
            "ole",
            "chart",
            "video",
            "form",
            "control",
            "section_properties",
            "other",
        }
    )


@pytest.mark.parametrize(
    "fixture,expected",
    [
        ("reader_writer__SimpleTable.hwpx", {"section_properties", "control", "table"}),
        ("reader_writer__SimplePicture.hwpx", {"section_properties", "control", "picture"}),
        ("reader_writer__SimpleEquation.hwpx", {"section_properties", "control", "equation"}),
        ("reader_writer__SimpleOLE.hwpx", {"section_properties", "control", "ole"}),
        ("reader_writer__SimpleVideo.hwpx", {"section_properties", "control", "video", "shape"}),
        ("reader_writer__SimpleTextArt.hwpx", {"section_properties", "control", "shape"}),
        ("reader_writer__SimpleButtons.hwpx", {"section_properties", "control", "form"}),
        ("reader_writer__SimpleEdit.hwpx", {"section_properties", "control", "form"}),
        ("reader_writer__SimpleDutmal.hwpx", {"section_properties", "control", "text"}),
        ("reader_writer__SimpleCompose.hwpx", {"section_properties", "control", "text"}),
    ],
)
def test_content_kinds_on_real_corpus_first_runs(fixture: str, expected: set[str]) -> None:
    document = HwpxDocument.open(FIXTURES / "hwpxlib_corpus" / fixture)
    run = document.sections[0].paragraphs[0].runs[0]

    assert run.content_kinds() == expected
