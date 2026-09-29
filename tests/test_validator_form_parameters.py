"""Index marks and shape parameter sets that Hancom cannot open.

``form_params_base.hwpx``: Hancom saved a new document with an index mark (``add_index_mark``) and a drop cap
(``add_drop_cap``), whose text box carries an ``hp:parameterset`` holding an ``hp:listParam`` with one
``hp:unsignedintegerParam``. Each case below removes one thing from that saved document; Hancom refuses to
open the result or crashes on it.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest
from lxml import etree

from hwpx.tools.package_validator import validate_package

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
BASE = Path(__file__).parent / "fixtures" / "hancom_saved" / "form_params_base.hwpx"
SECTION = "Contents/section0.xml"
Change = Callable[[etree._Element], None]


def _mutate(change: Change) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(BASE) as source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            data = source.read(info)
            if info.filename == SECTION:
                root = etree.fromstring(data)
                change(root)
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            target.writestr(info, data)
    return out.getvalue()


def _drop(tag: str) -> Change:
    def change(root: etree._Element) -> None:
        for element in list(root.iter(f"{HP}{tag}")):
            element.getparent().remove(element)
    return change


def _drop_attribute(tag: str, attribute: str) -> Change:
    def change(root: etree._Element) -> None:
        for element in root.iter(f"{HP}{tag}"):
            del element.attrib[attribute]
    return change


def _errors(data: bytes) -> list[str]:
    return [issue.message for issue in validate_package(data).errors]


def test_the_saved_document_passes() -> None:
    root = etree.fromstring(zipfile.ZipFile(BASE).read(SECTION))
    assert [len(list(root.iter(f"{HP}{tag}"))) for tag in ("indexmark", "listParam", "unsignedintegerParam")] == [1, 1, 1]
    assert _errors(BASE.read_bytes()) == []


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (_drop("firstKey"), "hp:indexmark without hp:firstKey"),
        (_drop_attribute("listParam", "name"), "hp:listParam missing name"),
        (_drop_attribute("unsignedintegerParam", "name"), "hp:unsignedintegerParam missing name"),
        (_drop("listParam"), "hp:parameterset cnt=1 holds no parameter"),
        (_drop("unsignedintegerParam"), "hp:listParam cnt=1 holds no parameter"),
    ],
    ids=["indexmark-firstKey", "listParam-name", "unsignedintegerParam-name", "empty-parameterset", "empty-listParam"],
)
def test_a_document_hancom_cannot_open_is_an_error(change: Change, message: str) -> None:
    assert any(message in error for error in _errors(_mutate(change)))


def test_a_parameter_list_that_counts_none_may_be_empty() -> None:
    def change(root: etree._Element) -> None:
        for listed in root.iter(f"{HP}listParam"):
            for child in list(listed):
                listed.remove(child)
            listed.set("cnt", "0")

    assert not any("holds no parameter" in error for error in _errors(_mutate(change)))


def test_a_count_other_than_the_parameters_held_is_fine() -> None:
    def change(root: etree._Element) -> None:
        for listed in root.iter(f"{HP}listParam"):
            listed.set("cnt", "2")
        for parameter_set in root.iter(f"{HP}parameterset"):
            parameter_set.set("cnt", "0")

    assert not any("holds no parameter" in error for error in _errors(_mutate(change)))
