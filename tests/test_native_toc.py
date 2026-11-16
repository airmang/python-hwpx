# SPDX-License-Identifier: Apache-2.0
"""차례(``fieldBegin type="TABLEOFCONTENTS"``) 읽기·다시 만들기·지우기·만들기 (``doc.refs``).

The region is read as Hancom saves it (m7_toc_gold A/B, gui_probes/title_mark_*): the title after
the field's start, one entry paragraph per heading (``<number> <text>``, a tab, the page in the tab's
tail; styled 차례 N; a HYPERLINK to ``?#<heading id>``), further blocks ("<표 차례>" …) after a 차례 제목
paragraph. Rebuilding rewrites the heading entries from the outline, leaves the page numbers empty and
sets ``dirty="1"``: Hancom builds a dirty table again -- entries, styles and page numbers -- when it
next opens the document (docs/internals/toc-dirty.md), so no page number python-hwpx cannot know is
written.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxError
from hwpx.objects import TableOfContents, TocEntry
from hwpx.tools.toc_author import toc_command_values

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures"
GOLD_A = FIXTURES / "m7_toc_gold" / "hancom-native-toc-A.hwpx"
GOLD_B = FIXTURES / "m7_toc_gold" / "hancom-native-toc-B.hwpx"
TITLE_MARK = FIXTURES / "gui_probes" / "title_mark_caret_p1_mark.hwpx"


def _reopen(document: HwpxDocument) -> HwpxDocument:
    reopened = HwpxDocument.open(document.to_bytes())
    assert not reopened.validate().issues
    return reopened


def _parts(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _changed_parts(before: bytes, after: bytes) -> set[str]:
    old, new = _parts(before), _parts(after)
    return {name for name in old.keys() | new.keys() if old.get(name) != new.get(name)}


def _headings(document: HwpxDocument):
    return [p for p in document.paragraphs if p.outline_level]


# -- reading -------------------------------------------------------------------------------------


def test_a_hancom_saved_table_of_contents_reads_as_written() -> None:
    (toc,) = HwpxDocument.open(GOLD_A).refs.tables_of_contents
    assert isinstance(toc, TableOfContents)
    assert (toc.title, toc.levels, toc.hyperlink, toc.leader, toc.refresh_on_open) == (
        "<제목 차례>", 2, True, "DASH", False)
    assert [entry.to_dict() for entry in toc.entries] == [
        {"text": "1. 개요 첫 번째", "level": 1, "page": "1", "target": "#56578383"},
        {"text": "2. 개요 두 번째", "level": 1, "page": "2", "target": "#56578352"},
        {"text": "3. 개요 세 번째", "level": 1, "page": "2", "target": "#56578353"},
        {"text": "4. 개요 네 번째", "level": 1, "page": "3", "target": "#56578361"},
    ]
    assert all(isinstance(entry, TocEntry) for entry in toc.entries)
    assert toc.entries[0].paragraph.text.startswith("1. 개요 첫 번째")
    # B is A after its first page grew, saved without 차례 새로 고침: the pages are Hancom's old ones.
    (stale,) = HwpxDocument.open(GOLD_B).refs.tables_of_contents
    assert [entry.page for entry in stale.entries] == ["1", "2", "2", "3"]
    marked = HwpxDocument.open(TITLE_MARK).refs.tables_of_contents[0]
    assert [(e.text, e.page) for e in marked.entries] == [("1. 제목 A", "1"), ("2. 제목 B", "1")]


def test_the_command_items_read_with_their_lengths() -> None:
    values = toc_command_values(
        "TableOfContents:set:140:ContentsMake:uint:31 ContentsStyles:wstring:0: ContentsLevel:int:2 "
        "ContentsAutoTabRight:int:0 ContentsLeader:int:3 ContentsHyperlink:bool:1  "
    )
    assert values == {"ContentsMake": "31", "ContentsStyles": "", "ContentsLevel": "2",
                      "ContentsAutoTabRight": "0", "ContentsLeader": "3", "ContentsHyperlink": "1"}


def test_reading_writes_nothing() -> None:
    document = HwpxDocument.open(GOLD_A)
    before = document.to_bytes()
    for toc in document.refs.tables_of_contents:
        toc.to_dict()
    assert document.to_bytes() == before


# -- rebuilding ----------------------------------------------------------------------------------


def test_rebuild_follows_the_outline_and_leaves_pages_for_hancom() -> None:
    document = HwpxDocument.open(GOLD_A)
    before = document.to_bytes()
    headings = _headings(document)
    headings[1].text = "바뀐 두 번째 개요"
    headings[3].outline_level = 0  # no longer a heading
    (toc,) = document.refs.tables_of_contents
    blocks_before = [p.text for p in document.paragraphs[5:12]]
    toc.rebuild()
    assert [(e.text, e.level, e.page, e.target) for e in toc.entries] == [
        ("1. 개요 첫 번째", 1, "", "#56578383"),
        ("2. 바뀐 두 번째 개요", 1, "", "#56578352"),
        ("3. 개요 세 번째", 1, "", "#56578353"),
    ]
    assert toc.refresh_on_open and toc.element.get("dirty") == "1"
    for entry in toc.entries:
        element = entry.paragraph.element
        assert element.find(f"{HP}linesegarray") is None
        assert (element.get("styleIDRef"), element.get("paraPrIDRef")) == ("19", "13")  # 차례 1
    # the empty line and the "<표 차례>" … blocks after the heading entries stay
    assert [p.text for p in document.paragraphs[4:11]] == blocks_before
    reopened = _reopen(document)
    assert [e.text for e in reopened.refs.tables_of_contents[0].entries][1] == "2. 바뀐 두 번째 개요"
    # the header changes only by the test's own outline-level edit (a derived paragraph shape)
    assert _changed_parts(before, document.to_bytes()) == {"Contents/section0.xml", "Contents/header.xml"}
    only_text = HwpxDocument.open(GOLD_A)
    original = only_text.to_bytes()
    _headings(only_text)[0].text = "다른 첫 번째"
    only_text.refs.tables_of_contents[0].rebuild()
    assert _changed_parts(original, only_text.to_bytes()) == {"Contents/section0.xml"}


def test_rebuild_keeps_level_two_and_leaves_hidden_headings_out() -> None:
    document = HwpxDocument.new()
    document.add_heading("장", level=1)
    document.add_heading("절", level=2)
    document.add_heading("항", level=3)
    hidden = document.add_heading("숨긴 장", level=1)
    hidden.add_title_mark(in_toc=False)  # 차례 숨기기
    toc = document.refs.add_table_of_contents(levels=2)
    assert [(e.text, e.level) for e in toc.entries] == [("1. 장", 1), ("가. 절", 2)]
    styles = {e.level: e.paragraph.element.get("styleIDRef") for e in toc.entries}
    assert styles == {1: "19", 2: "20"}  # 차례 1, 차례 2
    deeper = document.refs.add_table_of_contents(index=0, levels=3, hyperlink=False)
    assert [(e.text, e.target) for e in deeper.entries] == [("1. 장", ""), ("가. 절", ""), ("1) 항", "")]
    assert all(e.paragraph.element.find(f".//{HP}fieldBegin") is None for e in deeper.entries)
    _reopen(document)


def test_refresh_on_open_is_the_dirty_mark() -> None:
    document = HwpxDocument.open(GOLD_A)
    (toc,) = document.refs.tables_of_contents
    toc.refresh_on_open = True
    assert toc.element.get("dirty") == "1"
    toc.refresh_on_open = False
    assert toc.element.get("dirty") == "0"
    with pytest.raises(HwpxError) as excinfo:
        toc.refresh_on_open = "yes"
    assert excinfo.value.code == "toc-refresh-value"


def test_a_table_beginning_and_ending_in_one_paragraph_is_not_rebuilt() -> None:
    document = HwpxDocument.open(GOLD_A)
    (toc,) = document.refs.tables_of_contents
    first = document.paragraphs[0].element
    end = next(e for e in document.sections[0].element.iter(f"{HP}fieldEnd") if e.get("beginIDRef") == toc.element.get("id"))
    run = first.findall(f"{HP}run")[-1]
    run.append(end.getparent())  # move the end into the first paragraph
    with pytest.raises(HwpxError) as excinfo:
        toc.rebuild()
    assert excinfo.value.code == "toc-region-unsupported"


# -- removing ------------------------------------------------------------------------------------


def test_remove_takes_the_whole_region_out_and_keeps_the_section_setup() -> None:
    document = HwpxDocument.open(GOLD_A)
    texts = [p.text for p in document.paragraphs]
    first = document.paragraphs[0].element
    (toc,) = document.refs.tables_of_contents
    toc.remove()
    assert document.refs.tables_of_contents == ()
    assert document.refs.cross_references == ()  # the one cross reference sat inside the region
    assert first.find(f"{HP}run/{HP}secPr") is not None and first.find(f"{HP}linesegarray") is None
    remaining = [p.text for p in document.paragraphs]
    assert remaining[0] == "" and remaining[1:] == texts[texts.index("개요 첫 번째"):]
    reopened = _reopen(document)
    assert [p.text for p in _headings(reopened)] == ["개요 첫 번째", "개요 두 번째", "개요 세 번째", "개요 네 번째"]


# -- making --------------------------------------------------------------------------------------


def test_add_table_of_contents_writes_hancoms_region() -> None:
    document = HwpxDocument.new()
    document.add_heading("첫째 장", level=1)
    document.add_paragraph("본문", style="본문")
    document.add_heading("둘째 장", level=1)
    toc = document.refs.add_table_of_contents(title="차례", leader="DOT")
    assert (toc.title, toc.levels, toc.leader, toc.hyperlink, toc.refresh_on_open) == ("차례", 2, "DOT", True, True)
    assert [e.text for e in toc.entries] == ["1. 첫째 장", "2. 둘째 장"]
    assert all(e.target.startswith("#") and e.target[1:].isdigit() and e.target != "#0" for e in toc.entries)
    assert document.paragraphs[0].element.find(f"{HP}run/{HP}secPr") is not None  # the setup stays first
    reopened = _reopen(document)
    assert [e.text for e in reopened.refs.tables_of_contents[0].entries] == ["1. 첫째 장", "2. 둘째 장"]


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"levels": 0}, "toc-levels-value"),
        ({"levels": True}, "toc-levels-value"),
        ({"leader": "dotted"}, "toc-leader-value"),
    ],
)
def test_bad_arguments_are_refused(kwargs, code) -> None:
    document = HwpxDocument.new()
    document.add_heading("장", level=1)
    with pytest.raises(HwpxError) as excinfo:
        document.refs.add_table_of_contents(**kwargs)
    assert excinfo.value.code == code


def test_a_document_without_headings_gets_no_table() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("본문")
    before = document.to_bytes()
    with pytest.raises(HwpxError) as excinfo:
        document.refs.add_table_of_contents()
    assert excinfo.value.code == "toc-no-headings" and excinfo.value.suggestion
    assert document.to_bytes() == before
