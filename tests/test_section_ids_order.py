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


def test_the_order_survives_saving_and_reopening() -> None:
    reopened = HwpxDocument.open(_three_sections().to_bytes())
    reopened.add_paragraph("라", section=reopened.add_section(after=2))

    assert _section_ids_and_texts(reopened.to_bytes()) == [
        ("section0", "가"),
        ("section1", "나"),
        ("section2", "다"),
        ("section3", "라"),
    ]
