# SPDX-License-Identifier: Apache-2.0
"""Sections keep the manifest ids section0, section1, ... in document order.

Hancom finds a package's sections by these ids, in number order, and does not open a
document that lacks one of them, so adding a section in the middle or removing one
renumbers the ids of the sections after it. The part names stay.
"""
from __future__ import annotations

import io
import re
import zipfile

from hwpx.document import HwpxDocument


def _section_ids_and_texts(data: bytes) -> list[tuple[str, str]]:
    """(manifest id, first text) of each section, in spine order."""
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        hpf = package.read("Contents/content.hpf").decode("utf-8")
        hrefs = dict(re.findall(r'<opf:item [^>]*\bid="([^"]+)"[^>]*\bhref="([^"]+)"', hpf))
        found = []
        for ident in re.findall(r'<opf:itemref [^>]*\bidref="([^"]+)"', hpf):
            href = hrefs.get(ident, "")
            if re.search(r"section\d+\.xml$", href):
                section = package.read(href if href.startswith("Contents/") else f"Contents/{href}").decode("utf-8")
                texts = re.findall(r"<hp:t>([^<]*)</hp:t>", section)
                found.append((ident, texts[0] if texts else ""))
        return found


def _three_sections() -> HwpxDocument:
    document = HwpxDocument.new()
    document.add_paragraph("가")
    document.add_paragraph("다", section=document.add_section())
    document.add_paragraph("나", section=document.add_section(after=0))
    return document


def test_a_section_added_in_the_middle_takes_the_id_of_its_place() -> None:
    assert _section_ids_and_texts(_three_sections().to_bytes()) == [
        ("section0", "가"),
        ("section1", "나"),
        ("section2", "다"),
    ]


def test_removing_a_middle_section_leaves_no_gap_in_the_ids() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("가")
    for text in ("지울 구역", "나", "다"):
        document.add_paragraph(text, section=document.add_section())

    document.remove_section(1)
    data = document.to_bytes()

    assert _section_ids_and_texts(data) == [("section0", "가"), ("section1", "나"), ("section2", "다")]
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        assert 'secCnt="3"' in package.read("Contents/header.xml").decode("utf-8")


def _rewritten(data: bytes, rename: dict[str, str], replace: dict[bytes, bytes]) -> bytes:
    """*data* with parts renamed and ``content.hpf`` edited, as another writer could have saved it."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "Contents/content.hpf":
                for old, new in replace.items():
                    payload = payload.replace(old, new)
            renamed = zipfile.ZipInfo(rename.get(info.filename, info.filename), info.date_time)
            renamed.compress_type = info.compress_type
            target.writestr(renamed, payload)
    return out.getvalue()


def _spine(data: bytes) -> list[tuple[str, str]]:
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        hpf = package.read("Contents/content.hpf").decode("utf-8")
    hrefs = dict(re.findall(r'<opf:item [^>]*\bid="([^"]+)"[^>]*\bhref="([^"]+)"', hpf))
    return [(ident, hrefs[ident]) for ident in re.findall(r'<opf:itemref [^>]*\bidref="([^"]+)"', hpf)
            if "section" in hrefs.get(ident, "")]


def _last_texts(document: HwpxDocument) -> list[str]:
    return [section.paragraphs[-1].text for section in document.oxml.sections]


def test_a_new_section_does_not_take_an_id_already_in_use() -> None:
    # a package whose one section part has no number keeps the id section0 for it
    document = HwpxDocument.new()
    document.add_paragraph("원래 구역")
    data = _rewritten(document.to_bytes(), {"Contents/section0.xml": "Contents/section.xml"},
                      {b'href="Contents/section0.xml"': b'href="Contents/section.xml"'})
    document = HwpxDocument.open(data)

    document.add_paragraph("새 구역", section=document.add_section())
    saved = document.to_bytes()

    assert _spine(saved) == [("section0", "Contents/section.xml"), ("section1", "Contents/section1.xml")]
    assert _last_texts(HwpxDocument.open(saved)) == ["원래 구역", "새 구역"]
    assert _last_texts(HwpxDocument.open(document.to_bytes(format="hwp"))) == ["원래 구역", "새 구역"]


def test_a_file_saved_with_ids_out_of_order_is_put_right_when_saved_again() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("가")
    document.add_paragraph("나", section=document.add_section())
    # what removing the first of three sections used to leave: section1, section2
    data = _rewritten(document.to_bytes(), {}, {b'"section1"': b'"section2"', b'"section0"': b'"section1"'})
    assert [ident for ident, _ in _spine(data)] == ["section1", "section2"]

    saved = HwpxDocument.open(data).to_bytes()

    assert _section_ids_and_texts(saved) == [("section0", "가"), ("section1", "나")]


def test_ids_already_in_order_leave_the_manifest_untouched() -> None:
    data = _three_sections().to_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        before = package.read("Contents/content.hpf")

    with zipfile.ZipFile(io.BytesIO(HwpxDocument.open(data).to_bytes())) as package:
        assert package.read("Contents/content.hpf") == before


def test_the_order_survives_saving_and_reopening() -> None:
    reopened = HwpxDocument.open(_three_sections().to_bytes())
    reopened.add_paragraph("라", section=reopened.add_section(after=2))

    assert _section_ids_and_texts(reopened.to_bytes()) == [
        ("section0", "가"),
        ("section1", "나"),
        ("section2", "다"),
        ("section3", "라"),
    ]
