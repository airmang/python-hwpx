"""TextExtractor writes each paragraph once when notes, controls or objects are inlined."""

from __future__ import annotations

import io
from zipfile import ZipFile

from hwpx.document import HwpxDocument
from hwpx.tools.text_extractor import AnnotationOptions, TextExtractor

_SEC_OPEN = (
    "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
    "<hs:sec xmlns:hp='http://www.hancom.co.kr/hwpml/2011/paragraph'"
    " xmlns:hs='http://www.hancom.co.kr/hwpml/2011/section'>"
)


def _archive(body: str) -> io.BytesIO:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("Contents/section0.xml", _SEC_OPEN + body + "</hs:sec>")
    buffer.seek(0)
    return buffer


def _p(*items: str) -> str:
    return "<hp:p><hp:run>" + "".join(items) + "</hp:run></hp:p>"


def _t(text: str) -> str:
    return f"<hp:t>{text}</hp:t>"


def _table(*cells: str) -> str:
    return "<hp:tbl><hp:tr>" + "".join(
        "<hp:tc><hp:subList>" + cell + "</hp:subList></hp:tc>" for cell in cells
    ) + "</hp:tr></hp:tbl>"


def _extract(body: str, **kwargs: object) -> str:
    with TextExtractor(_archive(body)) as extractor:
        return extractor.extract_text(**kwargs)  # type: ignore[arg-type]


_NESTED_TABLE = _p(_t("before"), _table(_p(_t("outer")), _p(_table(_p(_t("inner")))))) + _p(_t("after"))


def test_nested_objects_are_written_once() -> None:
    text = _extract(_NESTED_TABLE, object_behavior="nested")

    assert text.count("outer") == 1
    assert text.count("inner") == 1
    assert text.startswith("before")
    assert text.endswith("after")


def test_nested_objects_in_one_paragraph_are_written_once() -> None:
    with TextExtractor(_archive(_NESTED_TABLE)) as extractor:
        first = next(iter(extractor.iter_document_paragraphs(include_nested=False)))
        text = first.text(object_behavior="nested")

    assert text.count("outer") == 1
    assert text.count("inner") == 1


def test_skipped_objects_still_list_their_paragraphs() -> None:
    text = _extract(_NESTED_TABLE)

    assert text.split("\n") == ["before", "outer", "inner", "after"]


def test_inline_notes_are_written_once() -> None:
    body = _p(_t("body"), "<hp:ctrl><hp:footNote instId='1'><hp:subList>" + _p(_t("note")) + "</hp:subList></hp:footNote></hp:ctrl>")

    inline = _extract(body, annotations=AnnotationOptions(footnote="inline"))
    ignored = _extract(body)

    assert inline == "body[footnote:note]"
    assert ignored == "body\nnote"


def test_nested_controls_are_written_once() -> None:
    header = "<hp:ctrl><hp:header id='1'><hp:subList>" + _p(_t("head")) + "</hp:subList></hp:header></hp:ctrl>"
    body = _p(header, _t("body"))

    text = _extract(body, annotations=AnnotationOptions(control="nested"))

    assert text.count("head") == 1


def test_a_document_made_with_the_api_is_written_once() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(1, 2)
    table.cell(0, 0).text = "outer"
    table.cell(0, 1).add_table(1, 1).cell(0, 0).text = "inner"
    paragraph = doc.add_paragraph("body")
    doc.notes.add_footnote("NOTE BODY", paragraph=paragraph)

    with TextExtractor(io.BytesIO(doc.to_bytes())) as extractor:
        text = extractor.extract_text(
            object_behavior="nested",
            annotations=AnnotationOptions(footnote="inline"),
        )

    assert text.count("inner") == 1
    assert text.count("outer") == 1
    assert text.count("NOTE BODY") == 1
