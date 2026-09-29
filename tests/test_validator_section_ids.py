# SPDX-License-Identifier: Apache-2.0
"""The package validator checks the sections' manifest ids the way Hancom looks them up.

Hancom finds the sections by the ids section0, section1, ... in number order and does not
open a document that lacks one of them; it reads the sections in that order, not the spine's.
"""
from __future__ import annotations

import io
import re
import zipfile

from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety, validate_package
from hwpx.tools.repair import repair_repack

HPF = "Contents/content.hpf"


def _three_sections() -> bytes:
    document = HwpxDocument.new()
    document.add_paragraph("가")
    for text in ("나", "다"):
        document.add_paragraph(text, section=document.add_section())
    return document.to_bytes()


def _edit_manifest(data: bytes, edit) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == HPF:
                payload = edit(payload.decode("utf-8")).encode("utf-8")
            method = zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED
            target.writestr(info, payload, compress_type=method)
    return out.getvalue()


def _rename(old: str, new: str):
    return lambda hpf: hpf.replace(f'id="{old}"', f'id="{new}"').replace(f'idref="{old}"', f'idref="{new}"')


def _section_messages(data: bytes, errors: bool) -> list[str]:
    report = validate_package(data)
    issues = report.errors if errors else report.warnings
    return [issue.message for issue in issues if "section" in issue.message and "id" in issue.message]


def test_sections_numbered_in_order_pass() -> None:
    data = _three_sections()

    assert _section_messages(data, errors=True) == []
    assert _section_messages(data, errors=False) == []


def test_a_missing_section_number_is_an_error() -> None:
    data = _edit_manifest(_three_sections(), _rename("section1", "section5"))

    messages = _section_messages(data, errors=True)
    assert len(messages) == 1 and "'section1'" in messages[0]
    assert not validate_editor_open_safety(data).ok


def test_section_ids_by_another_name_are_an_error() -> None:
    data = _three_sections()
    for index in range(3):
        data = _edit_manifest(data, _rename(f"section{index}", f"sec{index}"))

    assert len(_section_messages(data, errors=True)) == 1


def _ids_shifted() -> bytes:
    """Three sections whose ids run section1 to section3, as an older remove_section(0) could leave them."""
    data = _three_sections()
    for index in (2, 1, 0):
        data = _edit_manifest(data, _rename(f"section{index}", f"section{index + 1}"))
    return data


def test_another_item_naming_a_section_part_is_not_counted() -> None:
    def add_item(hpf: str) -> str:
        return hpf.replace(
            "</opf:manifest>", '<opf:item id="prv" href="Contents/section0.xml" media-type="application/xml"/></opf:manifest>', 1
        )

    data = _edit_manifest(_three_sections(), add_item)

    assert _section_messages(data, errors=True) == []


def test_removing_a_section_other_than_the_last_still_saves() -> None:
    document = HwpxDocument.open(_three_sections())
    document.remove_section(0)

    assert _section_messages(document.to_bytes(), errors=True) == []
    assert document.to_bytes(format="hwp")


def test_a_file_saved_with_shifted_ids_saves_again() -> None:
    data = _ids_shifted()
    assert _section_messages(data, errors=True)

    saved = HwpxDocument.open(data).to_bytes()

    assert _section_messages(saved, errors=True) == []
    assert HwpxDocument.open(data).to_bytes(format="hwp")


def test_repair_repack_puts_shifted_ids_right(tmp_path) -> None:
    source = tmp_path / "shifted.hwpx"
    source.write_bytes(_ids_shifted())

    repair_repack(source, tmp_path / "repaired.hwpx")

    repaired = (tmp_path / "repaired.hwpx").read_bytes()
    assert _section_messages(repaired, errors=True) == []
    texts = [section.paragraphs[-1].text for section in HwpxDocument.open(repaired).oxml.sections]
    assert texts == ["가", "나", "다"]


def test_a_spine_order_other_than_the_id_order_is_a_warning() -> None:
    def swap_spine(hpf: str) -> str:
        refs = re.findall(r'<opf:itemref [^>]*idref="section[12]"[^>]*/>', hpf)
        return hpf.replace(refs[0], "@1@").replace(refs[1], refs[0]).replace("@1@", refs[1])

    data = _edit_manifest(_three_sections(), swap_spine)

    assert _section_messages(data, errors=True) == []
    assert len(_section_messages(data, errors=False)) == 1
