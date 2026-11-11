"""An edit drops the line cache of the paragraph it changed, and the save drops
a cache an edit left on content it changed.

Hancom trusts the line count of a cached ``hp:linesegarray`` and presses the
text into it, so a cache must not outlive the content it was computed for
(2026-11 audit ENG-06: ``paragraph.apply_model``, ``add_index_mark``,
``add_title_mark`` and ``add_drop_cap`` kept it, and the save-time sweep only
caught a cache short by more than a line's worth of text).
"""

from __future__ import annotations

import io
import zipfile

import pytest

from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
SECTION = "Contents/section0.xml"
# 10 pt text on a 42520-wide line: 42 Hangul letters fill it.
FITS = "가" * 30  # 0.7 of the line
OVER = "나" * 50  # about 1.2 lines: more than the cached line, less than the sweep's 2x proof
OTHER = "다른 문단"
ONE_LINE = (
    '<hp:linesegarray><hp:lineseg textpos="0" vertpos="0" vertsize="1000" textheight="1000" '
    'baseline="850" spacing="600" horzpos="0" horzsize="42520" flags="393216"/></hp:linesegarray>'
)


def _with_one_line_caches(data: bytes, texts: tuple[str, ...]) -> bytes:
    """Give the paragraph holding each of *texts* a one-line cache, as a file could carry."""

    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == SECTION:
                xml = payload.decode("utf-8")
                for text in texts:
                    marker = f"<hp:t>{text}</hp:t></hp:run>"
                    assert xml.count(marker) == 1, text
                    xml = xml.replace(marker, marker + ONE_LINE)
                payload = xml.encode("utf-8")
            method = zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED
            target.writestr(zipfile.ZipInfo(info.filename, info.date_time), payload, compress_type=method)
    return out.getvalue()


def _source(*texts: str) -> bytes:
    """A document whose paragraphs *texts* each carry a one-line cache."""

    doc = HwpxDocument.new()
    for text in texts:
        doc.add_paragraph(text)
    return _with_one_line_caches(doc.to_bytes(), texts)


def _section(data: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.read(SECTION)


def _cached(data: bytes) -> dict[str, bool]:
    """Whether each top-level paragraph, by its first letters, still has a cache."""

    from lxml import etree

    root = etree.fromstring(_section(data))
    return {
        "".join("".join(text.itertext()) for text in paragraph.findall(f"{HP}run/{HP}t"))[:5]:
            paragraph.find(f"{HP}linesegarray") is not None
        for paragraph in root.findall(f"{HP}p")
    }


def _model_text(paragraph) -> None:
    model = paragraph.model
    model.runs[0].text_spans[0].text = FITS + "라"
    paragraph.apply_model(model)


@pytest.mark.parametrize(
    "edit",
    [
        _model_text,
        lambda paragraph: paragraph.add_index_mark("색인"),
        lambda paragraph: paragraph.add_title_mark(in_toc=True),
        lambda paragraph: paragraph.add_drop_cap("가", width=2000, height=2000),
    ],
    ids=["apply_model", "add_index_mark", "add_title_mark", "add_drop_cap"],
)
def test_the_edit_drops_the_cache_of_its_paragraph_only(edit) -> None:
    doc = HwpxDocument.open(_source(FITS, OTHER))
    paragraph = doc.paragraphs[1]
    edit(paragraph)

    # at the edit, not only at the save
    assert doc.paragraphs[1].element.find(f"{HP}linesegarray") is None
    saved = doc.to_bytes()
    cached = _cached(saved)
    assert cached[FITS[:5]] is False
    assert cached[OTHER[:5]] is True
    assert validate_editor_open_safety(saved).ok


def test_apply_model_keeps_the_cache_when_the_model_changed_nothing() -> None:
    doc = HwpxDocument.open(_source(FITS, OTHER))
    paragraph = doc.paragraphs[1]
    paragraph.apply_model(paragraph.model)

    # A model may be used to edit the cache itself (tests/test_coverage_promotion.py), so
    # apply_model drops it only when the content changed under an unchanged cache.
    assert paragraph.element.find(f"{HP}linesegarray") is not None


def test_a_drop_cap_keeps_its_own_empty_line_array() -> None:
    doc = HwpxDocument.open(_source(FITS))
    doc.paragraphs[1].add_drop_cap("가", width=2000, height=2000)

    # Hancom writes an empty hp:linesegarray inside a drop cap; it is not a cache.
    assert _section(doc.to_bytes()).count(b"<hp:linesegarray/>") == 1


def _grow_behind_the_api(doc: HwpxDocument, index: int, extra: str) -> None:
    """Change a paragraph's text without clearing its cache, as an API that forgot to would."""

    paragraph = doc.paragraphs[index]
    text = paragraph.element.find(f"{HP}run/{HP}t")
    text.text = (text.text or "") + extra
    paragraph.section.mark_dirty()


def test_an_unedited_section_is_saved_as_it_was() -> None:
    source = _source(OVER, FITS)
    saved = HwpxDocument.open(source).to_bytes()

    assert _section(saved) == _section(source)


def test_an_edited_section_keeps_the_caches_of_the_paragraphs_left_alone() -> None:
    doc = HwpxDocument.open(_source(OVER, FITS, OTHER))
    doc.paragraphs[3].text = "다른 문단을 고쳤다"

    cached = _cached(doc.to_bytes())
    assert cached[OVER[:5]] is True  # as the file had it: not judged by an estimate of its width
    assert cached[FITS[:5]] is True
    assert cached["다른 문단"] is False


@pytest.mark.parametrize("extra", ["마", "마" * 20], ids=["one-letter", "a-line-more"])
def test_text_changed_behind_the_api_does_not_keep_its_cache(extra: str) -> None:
    doc = HwpxDocument.open(_source(FITS, OTHER))
    _grow_behind_the_api(doc, 1, extra)

    saved = doc.to_bytes()
    cached = _cached(saved)
    assert cached[FITS[:5]] is False
    assert cached[OTHER[:5]] is True
    assert validate_editor_open_safety(saved).ok


def test_the_next_save_judges_against_the_document_as_last_saved() -> None:
    doc = HwpxDocument.open(_source(FITS, OTHER))
    doc.add_paragraph("새 문단")
    first = _cached(doc.to_bytes())
    assert first[FITS[:5]] is True and first[OTHER[:5]] is True

    _grow_behind_the_api(doc, 2, " 더 길게")
    second = _cached(doc.to_bytes())
    assert second[FITS[:5]] is True
    assert second[OTHER[:5]] is False


def test_a_cache_written_after_the_edit_stays() -> None:
    doc = HwpxDocument.open(_source(FITS, OTHER))
    _grow_behind_the_api(doc, 1, "마")
    seg = doc.paragraphs[1].element.find(f"{HP}linesegarray/{HP}lineseg")
    seg.set("horzsize", "42000")  # a cache computed for the new text, not the one the file carried

    assert _cached(doc.to_bytes())[FITS[:5]] is True


def test_a_cell_edit_drops_the_cache_left_on_the_cell_paragraph() -> None:
    doc = HwpxDocument.new()
    doc.add_table(1, 1).cell(0, 0).text = FITS
    doc.add_paragraph(OTHER)
    doc = HwpxDocument.open(_with_one_line_caches(doc.to_bytes(), (FITS, OTHER)))
    cell = doc.tables.all[0].cell(0, 0)
    text = next(cell.element.iter(f"{HP}t"))
    text.text = FITS + "마"
    doc.sections[0].mark_dirty()

    xml = _section(doc.to_bytes()).decode("utf-8")
    cell_paragraph = xml[xml.index("<hp:subList") : xml.index("</hp:subList>")]
    assert "linesegarray" not in cell_paragraph
    assert _cached(doc.to_bytes())[OTHER[:5]] is True
