from __future__ import annotations

import importlib
import logging
import sys
import warnings
import xml.etree.ElementTree as ET
from typing import cast

from hwpx.document import HwpxDocument, _append_element
from hwpx.oxml.document import HwpxOxmlDocument, HwpxOxmlSection
from hwpx.opc.package import HwpxPackage


class _NoopResource:
    pass


class _BrokenResource:
    def flush(self) -> None:
        raise RuntimeError("flush error")

    def close(self) -> None:
        raise RuntimeError("close error")


def _minimal_document() -> HwpxDocument:
    section = HwpxOxmlSection("section0.xml", ET.Element("section"))
    root = HwpxOxmlDocument(ET.Element("manifest"), [section], [])
    return HwpxDocument(cast(HwpxPackage, object()), root)


def test_append_element_uses_same_element_type() -> None:
    parent = ET.Element("parent")
    child = _append_element(parent, "child", {"id": "42"})

    assert child.tag == "child"
    assert child.attrib["id"] == "42"
    assert parent[0] is child


def test_flush_and_close_resource_are_noop_without_method() -> None:
    HwpxDocument._flush_resource(_NoopResource())
    HwpxDocument._close_resource(_NoopResource())


def test_flush_and_close_resource_swallow_exceptions(caplog) -> None:
    caplog.set_level(logging.DEBUG)
    resource = _BrokenResource()

    HwpxDocument._flush_resource(resource)
    HwpxDocument._close_resource(resource)

    assert "자원 flush 중 예외를 무시합니다" in caplog.text
    assert "자원 close 중 예외를 무시합니다" in caplog.text


def test_package_module_warns_on_import_and_exports_symbols() -> None:
    module_name = "hwpx.package"
    sys.modules.pop(module_name, None)

    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        module = importlib.import_module(module_name)

    assert records
    assert any("더 이상 권장되지 않습니다" in str(record.message) for record in records)
    assert module.__all__ == [
        "HwpxPackage",
        "HwpxPackageError",
        "HwpxStructureError",
        "RootFile",
        "VersionInfo",
    ]
