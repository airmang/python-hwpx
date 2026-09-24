# SPDX-License-Identifier: Apache-2.0
"""normalize_hwpml_namespaces: same bytes as a full markup scan, without rescanning every tag."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

from hwpx.opc import xml_utils
from hwpx.opc.xml_utils import (
    _HWPML_2016_TO_2011,
    _XML_ATTRIBUTE,
    _XML_MARKUP,
    normalize_hwpml_namespaces,
)

OLD = b"http://www.hancom.co.kr/hwpml/2016/paragraph"
NEW = b"http://www.hancom.co.kr/hwpml/2011/paragraph"
UNIT = b"http://www.hancom.co.kr/hwpml/2016/HwpUnitChar"


def _reference(data: bytes) -> bytes:
    """Every tag and every attribute scanned in document order."""

    mapping = dict(_HWPML_2016_TO_2011)

    def attribute(match: re.Match[bytes]) -> bytes:
        name, equals, quote, value = match.groups()
        if name == b"xmlns" or name.startswith(b"xmlns:"):
            value = mapping.get(value, value)
        return name + equals + quote + value + quote

    def markup(match: re.Match[bytes]) -> bytes:
        tag = match.group()
        if tag.startswith((b"<!", b"<?")):
            return tag
        return _XML_ATTRIBUTE.sub(attribute, tag)

    return _XML_MARKUP.sub(markup, data)


CASES = {
    "declarations-and-case": (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
        b'<hs:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" xmlns:hp10="' + OLD + b'"'
        b' xmlns:hhs="http://www.hancom.co.kr/hwpml/2016/history">'
        b'<hp:p id="1"><hp:switch><hp:case hp:required-namespace="' + UNIT + b'"><hp:t>a</hp:t></hp:case>'
        b"</hp:switch><hp:run><hp:t>" + OLD + b"</hp:t></hp:run></hp:p></hs:sec>"
    ),
    "nested-declaration": b'<a><b xmlns:x="' + OLD + b'" y="' + OLD + b'"/><c>' + OLD + b"</c></a>",
    "single-quotes-and-gt-in-value": b"<a note='1 > 0' xmlns='" + OLD + b"'><b t=\"x>y\"/></a>",
    "uri-only-in-text": b"<a><b>" + OLD + b"</b><b>" + OLD + b"</b></a>",
    "uri-in-processing-instruction": b'<?pi xmlns="' + OLD + b'"?><a xmlns="' + OLD + b'"/>',
    "comment-and-cdata": (
        b'<p xmlns="' + OLD + b'"><!-- xmlns="' + OLD + b'" --><![CDATA[xmlns="' + OLD + b'"]]></p>'
    ),
    "no-2016-uri": b'<a xmlns="http://www.hancom.co.kr/hwpml/2011/paragraph"><b c="d"/></a>',
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_matches_full_markup_scan(name: str) -> None:
    assert normalize_hwpml_namespaces(CASES[name]) == _reference(CASES[name])


def test_rewrites_declarations_only() -> None:
    out = normalize_hwpml_namespaces(CASES["declarations-and-case"])
    assert b'xmlns:hp10="' + NEW + b'"' in out
    assert b'xmlns:hhs="http://www.hancom.co.kr/hwpml/2011/history"' in out
    assert b'hp:required-namespace="' + UNIT + b'"' in out
    assert b"<hp:t>" + OLD + b"</hp:t>" in out


def test_every_fixture_part_matches_full_markup_scan() -> None:
    root = Path(__file__).parent
    checked = 0
    for package in sorted(root.rglob("*.hwpx")):
        try:
            with zipfile.ZipFile(package) as archive:
                parts = [
                    archive.read(name)
                    for name in archive.namelist()
                    if name.endswith((".xml", ".hpf"))
                ]
        except (zipfile.BadZipFile, OSError):
            continue
        for data in parts:
            assert normalize_hwpml_namespaces(data) == _reference(data), package.name
            checked += 1
    assert checked > 0


def test_tags_without_2016_uri_are_not_rescanned(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    class CountingPattern:
        def sub(self, repl, string):  # noqa: ANN001, ANN201
            calls.append(string)
            return _XML_ATTRIBUTE.sub(repl, string)

    monkeypatch.setattr(xml_utils, "_XML_ATTRIBUTE", CountingPattern())
    body = b"".join(b'<hp:p id="%d"><hp:run charPrIDRef="0"><hp:t>x</hp:t></hp:run></hp:p>' % i for i in range(200))
    data = b'<hs:sec xmlns:hp10="' + OLD + b'">' + body + b"</hs:sec>"
    out = normalize_hwpml_namespaces(data)
    assert out == _reference(data)
    assert len(calls) == 1
