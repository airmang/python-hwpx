# SPDX-License-Identifier: Apache-2.0
"""``hwpx-repair`` and ``hwpx-pack`` read package parts without expanding entities."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.opc.security import HwpxSecurityError
from hwpx.opc.xml_utils import parse_untrusted_xml
from hwpx.tools import archive_cli
from hwpx.tools.repair import repair_repack

_SECTION = "Contents/section0.xml"
_MARK = "ENTITY-EXPANDED-MARK"
#: Declarations past the window the byte guard looks at.
_FAR = "<!--" + "x" * 5000 + "-->"


def _section_with_entity(path: Path, lead: str) -> tuple[dict[str, bytes], list[zipfile.ZipInfo]]:
    HwpxDocument.new().save_to_path(path)
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        parts = {info.filename: archive.read(info.filename) for info in infos}
    body = parts[_SECTION].decode("utf-8").split("?>", 1)[1]
    replaced = body.replace("<hp:t/>", "<hp:t>&mark;</hp:t>", 1)
    assert replaced != body
    parts[_SECTION] = (
        f'<?xml version="1.0" encoding="UTF-8"?>{lead}<!DOCTYPE sec [ <!ENTITY mark "{_MARK}"> ]>{replaced}'
    ).encode("utf-8")
    return parts, infos


@pytest.mark.parametrize("lead", ["", _FAR], ids=["near", "far"])
def test_parse_untrusted_xml_refuses_a_document_type(lead: str) -> None:
    payload = f'<?xml version="1.0"?>{lead}<!DOCTYPE a [ <!ENTITY mark "{_MARK}"> ]><a>&mark;</a>'.encode()
    with pytest.raises(HwpxSecurityError):
        parse_untrusted_xml(payload, part_name="part")


def test_parse_untrusted_xml_reads_an_ordinary_part() -> None:
    root = parse_untrusted_xml(b'<?xml version="1.0"?><a><b>text</b></a>')
    assert etree.QName(root).localname == "a"
    assert root[0].text == "text"


@pytest.mark.parametrize("lead", ["", _FAR], ids=["near", "far"])
def test_repair_does_not_expand_entities_into_its_output(tmp_path: Path, lead: str) -> None:
    parts, infos = _section_with_entity(tmp_path / "base.hwpx", lead)
    source = tmp_path / "source.hwpx"
    with zipfile.ZipFile(source, "w") as archive:
        for info in infos:
            archive.writestr(info.filename, parts[info.filename], compress_type=info.compress_type)
    output = tmp_path / "repaired.hwpx"
    with pytest.raises(ValueError):
        repair_repack(source, output)
    assert not output.exists()


@pytest.mark.parametrize("lead", ["", _FAR], ids=["near", "far"])
def test_pack_leaves_a_part_with_a_document_type_as_it_is(tmp_path: Path, lead: str) -> None:
    parts, _infos = _section_with_entity(tmp_path / "base.hwpx", lead)
    payload = parts[_SECTION]
    assert archive_cli._normalize_hwpml_compat_root(_SECTION, payload) == payload
    assert archive_cli._format_xml_bytes(payload) == payload


def test_pack_still_formats_an_ordinary_part() -> None:
    formatted = archive_cli._format_xml_bytes(b'<?xml version="1.0" encoding="UTF-8"?><a><b>text</b></a>')
    assert b"\n  <b>text</b>" in formatted
