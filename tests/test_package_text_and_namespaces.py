# SPDX-License-Identifier: Apache-2.0
"""Package-wide text replacement and namespace normalization as public core API.

``hwpx-plugins`` used to keep its own ZIP/XML editors for these two jobs
(``zip_replace_all.py`` and ``fix_namespaces.py``). The contracts below are
what those scripts now delegate to.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.patch import replace_package_text
from hwpx.tools.repair import normalize_package_namespaces

_SECTION = "Contents/section0.xml"


def _document_bytes(*texts: str) -> bytes:
    doc = HwpxDocument.new()
    for text in texts:
        doc.add_paragraph(text)
    table = doc.add_table(1, 1)
    table.cell(0, 0).text = "{CELL}"
    return doc.to_bytes()


def _members(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def _with_member(data: bytes, name: str, payload: bytes) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            dst.writestr(info, payload if info.filename == name else src.read(info))
        if name not in src.namelist():
            dst.writestr(name, payload)
    return out.getvalue()


def _minimal_unsafe_package() -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr(_SECTION, "<root>OLD</root>")
    return out.getvalue()


def test_replaces_body_cell_and_metadata_text_only() -> None:
    source = _document_bytes("{NAME} 님께", "그대로")
    hpf = _members(source)["Contents/content.hpf"].decode("utf-8")
    source = _with_member(
        source,
        "Contents/content.hpf",
        hpf.replace("<opf:title/>", "<opf:title>{NAME}</opf:title>").encode("utf-8"),
    )

    result = replace_package_text(source, {"{NAME}": "A & <B>", "{CELL}": "칸"})

    assert result.ok, result.open_safety
    assert result.entries == tuple(_members(source))
    assert result.replacements == 3
    assert set(result.changed_parts) == {_SECTION, "Contents/content.hpf"}
    reopened = HwpxDocument.open(result.data)
    text = reopened.text.plain()
    assert "A & <B> 님께" in text and "칸" in text and "{CELL}" not in text
    section = _members(result.data)[_SECTION].decode("utf-8")
    assert "A &amp; &lt;B&gt; 님께" in section
    assert "{NAME}" in _members(result.data)["Contents/content.hpf"].decode("utf-8") or "<opf:title>" not in hpf
    before, after = _members(source), _members(result.data)
    for name in before:
        if name not in result.changed_parts:
            assert after[name] == before[name], name


def test_attributes_comments_and_cdata_are_not_searched() -> None:
    source = _document_bytes("본문")
    section = _members(source)[_SECTION].decode("utf-8")
    marked = section.replace("<hp:t>본문</hp:t>", '<hp:t>본문</hp:t><!-- KEY --><hp:t><![CDATA[KEY]]></hp:t>', 1)
    source = _with_member(source, _SECTION, marked.encode("utf-8"))

    assert 'lang="HANGUL"' in _members(source)["Contents/header.xml"].decode("utf-8")

    result = replace_package_text(source, {"KEY": "X", "HANGUL": "LATIN", "hp:t": "hp:x"})

    # Comments, CDATA, attribute values and element names hold every key; none is touched.
    assert result.replacements == 0 and result.byte_identical


def test_a_changed_part_loses_its_layout_caches_and_others_keep_theirs() -> None:
    source = _document_bytes("{A}")
    section = _members(source)[_SECTION].decode("utf-8")
    cached = section.replace(
        "</hp:run></hp:p>",
        '</hp:run><hp:linesegarray><hp:lineseg textpos="0" vertpos="0" vertsize="1000" textheight="1000" '
        'baseline="850" spacing="600" horzpos="0" horzsize="42520" flags="393216"/></hp:linesegarray></hp:p>',
        1,
    )
    source = _with_member(source, _SECTION, cached.encode("utf-8"))
    assert "linesegarray" in cached

    unchanged = replace_package_text(source, {"{absent}": "x"})
    assert unchanged.layout_caches_removed == 0 and unchanged.byte_identical

    result = replace_package_text(source, {"{A}": "새 글"})
    assert result.layout_caches_removed >= 1
    assert "linesegarray" not in _members(result.data)[_SECTION].decode("utf-8").lower()


def test_output_path_is_written_only_when_the_gate_passes(tmp_path: Path) -> None:
    target = tmp_path / "out.hwpx"
    target.write_bytes(b"existing output")

    rejected = replace_package_text(_minimal_unsafe_package(), {"OLD": "NEW"}, output_path=target)
    assert not rejected.ok and rejected.output_path is None
    assert target.read_bytes() == b"existing output"

    accepted = replace_package_text(_document_bytes("{A}"), {"{A}": "B"}, output_path=target)
    assert accepted.ok and accepted.output_path == str(target)
    assert target.read_bytes() == accepted.data
    with zipfile.ZipFile(target) as archive:
        first = archive.infolist()[0]
        assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED


def test_an_empty_key_is_refused() -> None:
    with pytest.raises(ValueError):
        replace_package_text(_document_bytes(), {"": "x"})


def test_normalize_namespaces_gives_section_and_header_roots_the_hancom_surface() -> None:
    source = _document_bytes("본문")
    section = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
        'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
        + _members(source)[_SECTION].decode("utf-8").split(">", 2)[2].rsplit("</hs:sec>", 1)[0]
        + "</hs:sec>"
    )
    stripped = _with_member(source, _SECTION, section.encode("utf-8"))
    hpf_before = _members(stripped)["Contents/content.hpf"]

    result = normalize_package_namespaces(stripped)

    assert result.ok, result.open_safety
    members = _members(result.data)
    assert result.entries == tuple(members)
    assert _SECTION in result.normalized_parts and not result.unparsed_parts
    assert members["Contents/content.hpf"] == hpf_before
    for name in (_SECTION, "Contents/header.xml"):
        payload = members[name]
        assert b"xmlns:ha=" in payload and b"xmlns:hp10=" in payload
        assert b"standalone='yes'" in payload or b'standalone="yes"' in payload
    assert HwpxDocument.open(result.data).text.plain() == HwpxDocument.open(source).text.plain()


def test_normalize_namespaces_keeps_a_part_that_does_not_parse() -> None:
    broken = _with_member(_document_bytes("본문"), "Contents/broken.xml", b"<not-closed>")
    result = normalize_package_namespaces(broken)
    assert result.unparsed_parts == ("Contents/broken.xml",)
    assert _members(result.data)["Contents/broken.xml"] == b"<not-closed>"
    assert not result.ok  # the gate still refuses malformed XML


def test_normalize_namespaces_withholds_an_unsafe_output(tmp_path: Path) -> None:
    target = tmp_path / "out.hwpx"
    target.write_bytes(b"existing output")
    result = normalize_package_namespaces(_minimal_unsafe_package(), output_path=target)
    assert not result.ok and result.output_path is None
    assert target.read_bytes() == b"existing output"

    source = tmp_path / "in.hwpx"
    source.write_bytes(_document_bytes("본문"))
    written = normalize_package_namespaces(source, output_path=target)
    assert written.ok and target.read_bytes() == written.data
