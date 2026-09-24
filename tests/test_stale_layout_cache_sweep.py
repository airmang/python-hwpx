"""A document whose own layout cache lacks lines for a paragraph still saves.

The editor-open-safety check refuses a cache whose last line cannot hold the
text after it: Hancom would draw the tail over itself. The save-time sweep
drops such a cache from a paragraph python-hwpx did not edit as well, so Hancom
lays that paragraph out again, instead of the whole save being refused.
"""

from __future__ import annotations

import io
import re
import zipfile

from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety

LONG = "가나다라마바사아자차 " * 12
SHORT = "짧은 문단"
ONE_LINE = (
    '<hp:linesegarray><hp:lineseg textpos="0" vertpos="0" vertsize="1000" textheight="1000" '
    'baseline="850" spacing="600" horzpos="0" horzsize="42520" flags="393216"/></hp:linesegarray>'
)


def _with_one_line_caches(data: bytes) -> bytes:
    """Give the long and the short paragraph a one-line cache, as a file could carry."""

    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "Contents/section0.xml":
                xml = payload.decode("utf-8")
                for text in (LONG, SHORT):
                    xml = re.sub(
                        rf"(<hp:t>{re.escape(text)}</hp:t></hp:run>)", rf"\1{ONE_LINE}", xml, count=1
                    )
                payload = xml.encode("utf-8")
            method = zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED
            target.writestr(zipfile.ZipInfo(info.filename, info.date_time), payload, compress_type=method)
    return out.getvalue()


def _source() -> bytes:
    doc = HwpxDocument.new()
    doc.add_paragraph(LONG)
    doc.add_paragraph(SHORT)
    return _with_one_line_caches(doc.to_bytes())


def _paragraph_with(root, text: str):
    for paragraph in root.iter("{http://www.hancom.co.kr/hwpml/2011/paragraph}p"):
        if text in "".join(paragraph.itertext()):
            return paragraph
    raise AssertionError(text)


def test_the_open_safety_check_refuses_a_cache_that_lacks_lines() -> None:
    report = validate_editor_open_safety(_source())

    assert not report.ok
    assert "lacks lines for its tail" in report.summary


def test_a_document_carrying_such_a_cache_still_saves() -> None:
    doc = HwpxDocument.open(_source())
    saved = doc.to_bytes()  # no edit

    assert validate_editor_open_safety(saved).ok
    with zipfile.ZipFile(io.BytesIO(saved)) as archive:
        xml = archive.read("Contents/section0.xml").decode("utf-8")
    assert xml.count("<hp:linesegarray>") == xml.count("</hp:linesegarray>")
    long_start = xml.index(LONG.split(" ")[0])
    long_end = xml.index("</hp:p>", long_start)
    assert "linesegarray" not in xml[long_start:long_end]  # dropped: Hancom lays it out again
    short_start = xml.index(SHORT)
    assert "linesegarray" in xml[short_start: xml.index("</hp:p>", short_start)]  # fits: kept


def test_the_sweep_leaves_a_cache_that_fits() -> None:
    doc = HwpxDocument.open(_source())
    section = doc.sections[0]

    assert section.remove_stale_layout_caches() == 1
    short = _paragraph_with(section.element, SHORT)
    assert short.find("{http://www.hancom.co.kr/hwpml/2011/paragraph}linesegarray") is not None
