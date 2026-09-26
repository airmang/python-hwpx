"""Saving keeps a paragraph's layout cache when its hp:t holds inline elements.

Hancom's ``hp:lineseg@textpos`` counts the inline elements of ``hp:t`` (a tab 8, a
line break or a fixed space 1), so a cache whose lines start after them is not
stale, and saving a section (after an edit elsewhere in it) must not drop it.
"""

from __future__ import annotations

import io
from zipfile import ZipFile

from lxml import etree

from hwpx.document import HwpxDocument

_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_SECTION = "Contents/section0.xml"


def _with_cached_paragraph(text_xml: str, textpos: list[int]) -> bytes:
    """A new document plus one paragraph that carries *text_xml* and a cache."""
    base = ZipFile(io.BytesIO(HwpxDocument.new().to_bytes()))
    section = etree.fromstring(base.read(_SECTION))
    segments = "".join(
        f'<hp:lineseg textpos="{pos}" vertpos="{index * 1600}" vertsize="1000" textheight="1000" '
        f'baseline="850" spacing="600" horzpos="0" horzsize="42520" flags="393216"/>'
        for index, pos in enumerate(textpos)
    )
    section.append(etree.fromstring(
        f'<hp:p xmlns:hp="{_HP}" id="0" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
        f'<hp:run charPrIDRef="0"><hp:t>{text_xml}</hp:t></hp:run>'
        f"<hp:linesegarray>{segments}</hp:linesegarray></hp:p>"
    ))
    out = io.BytesIO()
    with ZipFile(out, "w") as archive:
        for info in base.infolist():
            data = base.read(info.filename)
            if info.filename == _SECTION:
                data = etree.tostring(section, xml_declaration=True, encoding="UTF-8", standalone=True)
            archive.writestr(info, data)
    return out.getvalue()


def _cached_textpos_after_save(data: bytes) -> list[str]:
    """Edit elsewhere in the section (so it is written again), save, read the cache back."""
    doc = HwpxDocument.open(io.BytesIO(data))
    doc.add_paragraph("an edit elsewhere in the section")
    section = etree.fromstring(ZipFile(io.BytesIO(doc.to_bytes())).read(_SECTION))
    cached = section.findall(f"{{{_HP}}}p")[-2]
    return [segment.get("textpos") for segment in cached.iter(f"{{{_HP}}}lineseg")]


def test_fixed_spaces_inside_the_text_count_in_the_cache() -> None:
    # "ab", two fixed spaces, "cd": Hancom positions 0..6, second line at 5
    data = _with_cached_paragraph("ab<hp:fwSpace/><hp:fwSpace/>cd", [0, 5])

    assert _cached_textpos_after_save(data) == ["0", "5"]


def test_a_tab_inside_the_text_counts_eight() -> None:
    # "a", a tab (8), "b": Hancom positions 0..10, second line at 9
    data = _with_cached_paragraph("a<hp:tab/>b", [0, 9])

    assert _cached_textpos_after_save(data) == ["0", "9"]


def test_line_breaks_inside_the_text_count_one() -> None:
    # "a", break, "b", break, "c": Hancom positions 0..5, lines at 0, 2 and 4
    data = _with_cached_paragraph("a<hp:lineBreak/>b<hp:lineBreak/>c", [0, 2, 4])

    assert _cached_textpos_after_save(data) == ["0", "2", "4"]


def test_a_cache_past_the_text_is_still_dropped() -> None:
    data = _with_cached_paragraph("ab", [0, 5])

    assert _cached_textpos_after_save(data) == []
