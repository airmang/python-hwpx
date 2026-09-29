"""``doc.shapes.remove_unused_charts()`` drops the chart parts no chart points at, as Hancom does on save.

``unused_chart_saved.hwpx``: Hancom saved a document with two pie charts after the first chart's paragraph
had been removed, so that chart's part (``Chart/chart1.xml``) was pointed at by nothing. Hancom kept the
other chart (its part renumbered ``Chart/chart1.xml``, with an OLE copy in ``BinData``) and dropped the
unused part.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from hwpx import HwpxDocument

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HANCOM_SAVED = Path(__file__).parent / "fixtures" / "hancom_saved" / "unused_chart_saved.hwpx"
CHART_HEAD = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
    '<c:chartSpace xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart">'
    "<c:chart><c:plotArea><c:layout/>"
)


def _pie(first: str, second: str) -> str:
    return (
        CHART_HEAD + '<c:pieChart><c:varyColors val="1"/><c:ser><c:idx val="0"/><c:order val="0"/>'
        '<c:cat><c:strRef><c:f>Sheet1!$A$2:$A$3</c:f><c:strCache><c:ptCount val="2"/>'
        f'<c:pt idx="0"><c:v>{first}</c:v></c:pt><c:pt idx="1"><c:v>{second}</c:v></c:pt></c:strCache></c:strRef></c:cat>'
        '<c:val><c:numRef><c:f>Sheet1!$B$2:$B$3</c:f><c:numCache><c:formatCode>General</c:formatCode>'
        '<c:ptCount val="2"/><c:pt idx="0"><c:v>60</c:v></c:pt><c:pt idx="1"><c:v>40</c:v></c:pt>'
        "</c:numCache></c:numRef></c:val></c:ser></c:pieChart>"
        "</c:plotArea></c:chart></c:chartSpace>"
    )


def _document() -> HwpxDocument:
    """The document Hancom saved as ``unused_chart_saved.hwpx``."""
    document = HwpxDocument.new()
    document.add_paragraph("차트 앞")
    removed = document.add_paragraph("")
    document.shapes.add_chart(_pie("RemovedA", "RemovedB"), paragraph=removed, size=(12000, 9000))
    kept = document.add_paragraph("")
    document.shapes.add_chart(_pie("KeptA", "KeptB"), paragraph=kept, size=(12000, 9000))
    document.add_paragraph("차트 뒤")
    removed.remove()
    return document


def _chart_labels(data: bytes) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return [
            re.findall(r"<c:v>([A-Za-z]+)</c:v>", archive.read(name).decode("utf-8"))
            for name in sorted(archive.namelist())
            if name.startswith("Chart/")
        ]


def test_a_chart_part_nothing_points_at_is_removed_and_a_used_one_kept() -> None:
    document = _document()
    assert _chart_labels(document.to_bytes()) == [["RemovedA", "RemovedB"], ["KeptA", "KeptB"]]

    assert document.shapes.remove_unused_charts() == ("Chart/chart1.xml",)
    assert _chart_labels(document.to_bytes()) == [["KeptA", "KeptB"]]


def test_it_leaves_the_charts_hancom_keeps() -> None:
    document = _document()
    document.shapes.remove_unused_charts()

    assert _chart_labels(document.to_bytes()) == _chart_labels(HANCOM_SAVED.read_bytes()) == [["KeptA", "KeptB"]]


def test_the_part_of_a_chart_cleared_from_the_body_goes() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("차트 앞")
    document.shapes.add_chart(_pie("A", "B"), paragraph=document.add_paragraph(""), size=(12000, 9000))
    document.sections[0].clear_body()

    assert document.shapes.remove_unused_charts() == ("Chart/chart1.xml",)
    assert _chart_labels(document.to_bytes()) == []


def test_a_document_whose_charts_are_all_used_is_left_alone() -> None:
    document = HwpxDocument.open(HANCOM_SAVED)
    before = document.to_bytes()

    assert document.shapes.remove_unused_charts() == ()
    assert document.to_bytes() == before


def test_a_hancom_chart_goes_with_its_ole_copy() -> None:
    document = HwpxDocument.open(HANCOM_SAVED)
    holder = next(paragraph for paragraph in document.paragraphs if paragraph.element.find(f".//{HP}chart") is not None)
    holder.remove()

    assert document.shapes.remove_unused_charts() == ("Chart/chart1.xml",)
    assert [str(item) for item in document.media.remove_unused_images()] == ["ole1"]
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as saved:
        assert not [name for name in saved.namelist() if name.startswith(("Chart/", "BinData/"))]
