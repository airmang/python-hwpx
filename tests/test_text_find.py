# SPDX-License-Identifier: Apache-2.0
"""``doc.text.find()`` and regular-expression ``doc.text.replace(..., regex=True)``.

``find`` looks where ``doc.text.paragraphs()`` walks (cells, nested cells, text boxes, captions,
headers, footers, notes, memos, master pages) and returns ``TextMatch`` values whose ``start``/``end``
are positions in ``paragraph.text``. It joins text across runs the way ``replace(everywhere=True)``
does: not across a tab, a line break, a special space, a control or an object.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxTypeError, HwpxValueError
from hwpx.model import Paragraph
from hwpx.objects import TextMatch

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
CAPTIONS_IN_CELLS = FIXTURES / "hancom_saved" / "pages_captioned_tables_in_cells.hwpx"


def _document() -> HwpxDocument:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    paragraph.add_run("전화 010-", bold=True)
    paragraph.add_run("1234-5678, 02-555-0000")
    doc.add_paragraph("탭\t뒤 2026년 11월")
    doc.add_table(1, 1).cell(0, 0).text = "칸 안 2025년"
    doc.page.set_header(text="머리말 2024년")
    doc.notes.add_footnote("각주 2023년", paragraph=1)
    doc.notes.add_memo("메모 2022년", paragraph=1)
    return doc


def _phone(doc: HwpxDocument) -> Paragraph:
    return next(paragraph for paragraph in doc.paragraphs if paragraph.text.startswith("전화"))


def _parts(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_find_returns_matches_with_their_paragraph_positions_and_places() -> None:
    doc = _document()

    matches = doc.text.find(r"(\d{4})년", regex=True)

    assert isinstance(matches, tuple) and all(isinstance(m, TextMatch) for m in matches)
    assert all(isinstance(m.paragraph, Paragraph) for m in matches)
    assert {(m.where, m.text, m.groups) for m in matches} == {
        ("header", "2024년", ("2024",)),
        ("body", "2026년", ("2026",)),
        ("footnote", "2023년", ("2023",)),
        ("memo", "2022년", ("2022",)),
        ("cell", "2025년", ("2025",)),
    }
    for match in matches:
        assert match.paragraph.text[match.start:match.end] == match.text
    body = next(m for m in matches if m.where == "body")
    assert (body.start, body.end) == (4, 9)  # the tab before counts as one character
    assert body.section is doc.sections[0] and body.to_dict()["section"] == 0  # 7.0: the section object (N9)
    cell = next(m for m in matches if m.where == "cell")
    assert (cell.row, cell.col, cell.depth) == (0, 0, 1) and cell.table is not None


def test_a_plain_search_crosses_runs_but_not_tabs() -> None:
    doc = _document()

    (match,) = doc.text.find("010-1234")
    assert (match.where, match.start, match.end, match.groups) == ("body", 3, 11, ())
    assert doc.text.find("탭\t뒤") == ()  # a tab is no part of a word
    assert [m.text for m in doc.text.find("탭\t뒤", regex=True)] == []
    assert [m.text for m in doc.text.find(r".+", regex=True, where="body") if "\t" in m.text] == []


def test_where_chooses_the_places_and_the_search_changes_nothing() -> None:
    doc = HwpxDocument.open(_document().to_bytes())
    before = doc.to_bytes()

    assert [m.where for m in doc.text.find("20", where="body")] == ["body"]
    assert sorted(m.where for m in doc.text.find("20", where={"cell", "header"})) == ["cell", "header"]
    with pytest.raises(HwpxValueError) as caught:
        doc.text.find("20", where="cells")
    assert caught.value.code == "text-place-invalid"
    assert doc.to_bytes() == before


def test_a_regular_expression_finds_groups_and_skips_empty_matches() -> None:
    doc = _document()

    numbers = doc.text.find(re.compile(r"(?P<area>\d{2,3})-(\d{3,4})-(\d{4})"))
    assert [(m.text, m.groups) for m in numbers] == [
        ("010-1234-5678", ("010", "1234", "5678")),
        ("02-555-0000", ("02", "555", "0000")),
    ]
    assert doc.text.find(r"x*", regex=True) == ()  # matches nothing but the space between characters
    starts = [m.text for m in doc.text.find(r"^\S+", regex=True, where="body")]
    assert starts == ["전화", "탭", "뒤"]  # ^ is the start of each stretch a word may cover
    assert [m.text for m in doc.text.find(r"(?i)a|B", regex=True)] == []


def test_a_match_feeds_format_range() -> None:
    doc = _document()
    (match,) = doc.text.find("11월")

    runs = match.paragraph.format_range(match.start, match.end, bold=True)

    assert [run.text for run in runs] == ["11월"] and runs[0].bold is True


@pytest.mark.parametrize(
    ("pattern", "regex", "code", "error"),
    [
        ("", False, "text-search-empty", HwpxValueError),
        ("", True, "text-search-empty", HwpxValueError),
        ("(", True, "text-pattern-invalid", HwpxValueError),
        (3, False, "hwpx-type-error", HwpxTypeError),
    ],
)
def test_a_bad_pattern_is_refused(pattern: object, regex: bool, code: str, error: type) -> None:
    doc = _document()
    with pytest.raises(error) as caught:
        doc.text.find(pattern, regex=regex)  # type: ignore[arg-type]
    assert caught.value.code == code
    assert isinstance(caught.value, (ValueError, TypeError))


def test_regex_replace_fills_groups_everywhere() -> None:
    doc = _document()

    count = doc.text.replace(r"(\d{4})년", r"\1 년도", regex=True, everywhere=True)

    assert count == 4  # memo bodies are left alone, as Hancom's replace-all does
    texts = {place.paragraph.text for place in doc.text.iter_paragraphs() if place.paragraph.text}
    assert {"머리말 2024 년도", "탭\t뒤 2026 년도 11월", "각주 2023 년도", "칸 안 2025 년도", "메모 2022년"} <= texts
    reopened = HwpxDocument.open(doc.to_bytes())
    assert reopened.validate().ok
    assert [m.text for m in reopened.text.find("년도")] == ["년도"] * 4


def test_regex_replace_keeps_each_character_in_its_run() -> None:
    doc = _document()
    paragraph = _phone(doc)
    first, second = (run for run in paragraph.runs if run.text)

    count = doc.text.replace(r"(\d{3})-(\d{4})-(\d{4})", r"\1.\2.\3", regex=True, everywhere=True)

    assert count == 1
    assert paragraph.text == "전화 010.1234.5678, 02-555-0000"
    assert first.text == "전화 010." and first.bold is True  # the match began in the bold run
    assert second.text.startswith("1234.5678")


def test_regex_replace_in_the_default_scope_looks_inside_one_run() -> None:
    doc = _document()

    count = doc.text.replace(r"(\d+)-(\d+)-(\d+)", r"\3-\2-\1", regex=True)

    # the default scope: body runs, one at a time: 010-1234-5678 spans two runs and stays
    assert count == 1
    assert _phone(doc).text == "전화 010-1234-5678, 0000-555-02"


def test_limit_counts_regex_replacements() -> None:
    doc = _document()
    assert doc.text.replace(r"\d{4}년", "연도", regex=True, everywhere=True, limit=2) == 2
    assert len(doc.text.find("연도")) == 2


def test_a_compiled_pattern_and_named_groups() -> None:
    doc = _document()
    pattern = re.compile(r"(?P<year>\d{4})년 (?P<month>\d+)월")
    assert doc.text.replace(pattern, r"\g<month>/\g<year>", everywhere=True) == 1
    assert doc.text.find("11/2026")[0].where == "body"


def test_plain_replace_takes_regex_characters_as_they_are() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("가격(원): 1.5")
    assert doc.text.replace("(원)", "[원]") == 1
    assert doc.text.replace("1.5", r"\1") == 1
    assert doc.paragraphs[-1].text == r"가격[원]: \1"


@pytest.mark.parametrize("replacement", [r"\2", r"\g<missing>", "\\"])
def test_a_bad_replacement_is_refused_before_anything_changes(replacement: str) -> None:
    doc = HwpxDocument.open(_document().to_bytes())
    before = doc.to_bytes()

    with pytest.raises(HwpxValueError) as caught:
        doc.text.replace(r"(\d{4})년", replacement, regex=True, everywhere=True)

    assert caught.value.code == "text-replacement-invalid"
    assert doc.to_bytes() == before


def test_hangul_saved_captions_and_cells_lose_their_line_cache_and_nothing_else_changes() -> None:
    doc = HwpxDocument.open(CAPTIONS_IN_CELLS)
    before = _parts(CAPTIONS_IN_CELLS.read_bytes())
    found = doc.text.find(r"캡션 (\d)", regex=True)
    assert found and {m.where for m in found} == {"caption"}

    count = doc.text.replace(r"캡션 (\d)", r"설명 \1", regex=True, everywhere=True)

    assert count == len(found)
    for match in found:
        paragraph = match.paragraph.element
        assert match.paragraph.text.startswith("설명")
        assert paragraph.find(f"{HP}linesegarray") is None
        holders = [node for node in paragraph.iterancestors(f"{HP}p")]
        assert len(holders) == 2  # the paragraph holding the captioned table and the one holding its table
        assert all(holder.find(f"{HP}linesegarray") is None for holder in holders)
    untouched = [place.paragraph.element for place in doc.text.iter_paragraphs(where="body") if place.paragraph.text == "끝"]
    assert untouched and all(p.find(f"{HP}linesegarray") is not None for p in untouched)
    data = doc.to_bytes()
    reopened = HwpxDocument.open(data)
    assert reopened.validate().ok
    assert len(reopened.text.find("설명")) == count
    after = _parts(data)
    changed = {name for name in before if before[name] != after.get(name)}
    assert changed == {"Contents/section0.xml"}
