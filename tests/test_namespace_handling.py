# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import io
import zipfile
from collections.abc import Mapping
from xml.etree import ElementTree as ET

from hwpx import HwpxDocument
from hwpx.oxml import namespaces
from hwpx.templates import blank_document_bytes
from hwpx.tools.text_extractor import TextExtractor


HWPML_2011 = {
    "app": "http://www.hancom.co.kr/hwpml/2011/app",
    "paragraph": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "section": "http://www.hancom.co.kr/hwpml/2011/section",
    "core": "http://www.hancom.co.kr/hwpml/2011/core",
    "head": "http://www.hancom.co.kr/hwpml/2011/head",
    "history": "http://www.hancom.co.kr/hwpml/2011/history",
    "master-page": "http://www.hancom.co.kr/hwpml/2011/master-page",
}


def _replace_package_namespaces(source: bytes, target: Mapping[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source), "r") as src:
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as dst:
            for info in src.infolist():
                payload = src.read(info.filename)
                if info.filename.endswith(".xml") or info.filename.endswith(".hpf"):
                    for family, old_uri in HWPML_2011.items():
                        payload = payload.replace(old_uri.encode(), target[family].encode())
                    if target["paragraph"].endswith("/2016/paragraph"):
                        payload = payload.replace(
                            b"http://www.hancom.co.kr/hwpml/2016/HwpUnitChar",
                            b"http://www.hancom.co.kr/hwpml/2016/HwpUnitChar",
                        )
                    elif target["paragraph"].endswith("/2024/paragraph"):
                        payload = payload.replace(
                            b"http://www.hancom.co.kr/hwpml/2016/paragraph",
                            target["paragraph"].encode(),
                        )
                dst.writestr(info, payload)
    return buffer.getvalue()


def _namespace_family(version: str) -> dict[str, str]:
    if version == "2016":
        return {
            family: uri.replace("/2011/", "/2016/")
            for family, uri in HWPML_2011.items()
        }
    if version == "2024":
        return {
            family: f"http://www.owpml.org/owpml/2024/{family}"
            for family in HWPML_2011
        }
    raise ValueError(version)


def _root_namespace(package_bytes: bytes, part_name: str) -> str:
    with zipfile.ZipFile(io.BytesIO(package_bytes), "r") as archive:
        root = ET.fromstring(archive.read(part_name))
    assert root.tag.startswith("{")
    return root.tag[1:].split("}", 1)[0]


def test_namespace_registry_exposes_supported_owpml_versions() -> None:
    assert namespaces.namespace_uri("paragraph", "2011") == HWPML_2011["paragraph"]
    assert namespaces.namespace_uri("paragraph", "2016") == (
        "http://www.hancom.co.kr/hwpml/2016/paragraph"
    )
    assert namespaces.namespace_uri("paragraph", "2024") == (
        "http://www.owpml.org/owpml/2024/paragraph"
    )
    assert namespaces.qn("paragraph", "p", version="2024") == (
        "{http://www.owpml.org/owpml/2024/paragraph}p"
    )


def test_detect_namespaces_identifies_document_version() -> None:
    section = ET.fromstring(
        "<hs:sec xmlns:hs='http://www.owpml.org/owpml/2024/section' "
        "xmlns:hp='http://www.owpml.org/owpml/2024/paragraph'>"
        "<hp:p/>"
        "</hs:sec>"
    )

    detected = namespaces.detect_namespaces(section)

    assert detected["section"] == "2024"
    assert detected["paragraph"] == "2024"


def test_open_accepts_2016_and_2024_namespaces() -> None:
    for version in ("2016", "2024"):
        package_bytes = _replace_package_namespaces(
            blank_document_bytes(),
            _namespace_family(version),
        )

        document = HwpxDocument.open(package_bytes)

        assert document.sections
        assert document.paragraphs


def test_text_extractor_accepts_2024_paragraph_namespace() -> None:
    package_bytes = _replace_package_namespaces(
        blank_document_bytes(),
        _namespace_family("2024"),
    )

    with TextExtractor(zipfile.ZipFile(io.BytesIO(package_bytes))) as extractor:
        paragraphs = list(extractor.iter_document_paragraphs())

    assert paragraphs


def test_open_to_bytes_preserves_source_namespace_after_edit() -> None:
    package_bytes = _replace_package_namespaces(
        blank_document_bytes(),
        _namespace_family("2024"),
    )
    document = HwpxDocument.open(package_bytes)
    document.paragraphs[0].text = "namespace preserved"

    roundtrip = document.to_bytes()

    assert _root_namespace(roundtrip, "Contents/section0.xml") == (
        "http://www.owpml.org/owpml/2024/section"
    )
