"""Package errors are ``HwpxError`` s with a registered code (engine contract 4 and 8).

Before 7.0 the ``hwpx.opc.package`` family (and ``HwpxSecurityError``) derived from plain
``Exception``/``ValueError``: a save the open-safety check refused raised a code-less
``HwpxPackageError``, and opening a damaged file raised errors outside ``HwpxError``.
They now derive from ``HwpxError`` and keep every class they were before, so an existing
``except`` still catches them.
"""

from __future__ import annotations

import inspect
import io
import zipfile
import zlib
from pathlib import Path

import pytest
from lxml import etree

import hwpx.opc.package as package_module
from hwpx import HwpxDocument
from hwpx.errors import ERROR_CODES, HwpxError
from hwpx.opc.package import (
    HwpxArchiveError,
    HwpxCompressedDataError,
    HwpxPackageError,
    HwpxStructureError,
    HwpxXmlSyntaxError,
)
from hwpx.opc.security import HwpxSecurityError

FIXTURES = Path(__file__).parent / "fixtures"
#: A damaged input (its table lacks the parts Hancom requires): it opens, but the
#: open-safety check refuses to write it back.
DAMAGED = FIXTURES / "reader_robustness" / "irb_form_blank.hwpx"


def _package_error_classes() -> list[type[BaseException]]:
    classes = [
        obj for _, obj in inspect.getmembers(package_module, inspect.isclass)
        if issubclass(obj, HwpxPackageError)
    ]
    return [*classes, HwpxSecurityError]


def test_every_package_error_is_an_hwpx_error_with_a_registered_code() -> None:
    for cls in _package_error_classes():
        assert issubclass(cls, HwpxError), cls
        assert cls.default_code in ERROR_CODES, (cls, cls.default_code)
    # the classes they were before, so existing handlers still catch them
    assert issubclass(HwpxArchiveError, zipfile.BadZipFile)
    assert issubclass(HwpxCompressedDataError, zlib.error)
    assert issubclass(HwpxXmlSyntaxError, etree.XMLSyntaxError)
    assert issubclass(HwpxSecurityError, ValueError)


@pytest.mark.parametrize(
    ("data", "code"),
    [(b"", "open-empty-file"), (b"PK\x03\x04broken", "open-archive-damaged"), (b"plain text", "open-not-hwpx")],
)
def test_opening_a_damaged_file_raises_an_hwpx_error(data: bytes, code: str) -> None:
    with pytest.raises(HwpxError) as caught:
        HwpxDocument.open(data)
    assert isinstance(caught.value, HwpxArchiveError)
    assert isinstance(caught.value, zipfile.BadZipFile)
    assert caught.value.code == code
    assert caught.value.to_dict()["code"] == code


def test_a_package_error_raised_without_a_reason_has_the_class_code() -> None:
    error = HwpxPackageError("something")
    assert (error.code, error.message, error.context, error.suggestion) == ("package-invalid", "something", {}, None)
    assert str(error) == "something"
    assert HwpxStructureError("x").code == "package-structure-invalid"
    reasoned = HwpxPackageError("x", code="open-safety-failed", context={"a": 1}, suggestion="do y")
    assert reasoned.to_dict() == {"code": "open-safety-failed", "message": "x", "context": {"a": 1},
                                  "suggestion": "do y"}


def test_a_broken_xml_part_keeps_lxml_number_in_lxml_code() -> None:
    with pytest.raises(etree.XMLSyntaxError) as caught:
        etree.fromstring(b"<a>")
    raw = caught.value
    wrapped = HwpxXmlSyntaxError.wrap(raw, part_name="Contents/section0.xml")
    assert wrapped.code == "package-xml-invalid"
    assert wrapped.lxml_code == raw.code  # type: ignore[attr-defined]
    assert wrapped.position == raw.position
    assert wrapped.part_name == "Contents/section0.xml"


def test_a_too_large_input_is_an_hwpx_error_and_a_value_error() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../evil", b"x")
    with pytest.raises(HwpxError) as caught:
        HwpxDocument.open(buffer.getvalue())
    assert isinstance(caught.value, ValueError)
    assert caught.value.code == "open-input-unsafe"


@pytest.mark.parametrize("how", ["to_bytes", "save"])
def test_a_refused_save_of_a_damaged_input_says_open_safety_failed(how: str, tmp_path: Path) -> None:
    document = HwpxDocument.open(DAMAGED)
    target = tmp_path / "out.hwpx"
    with pytest.raises(HwpxPackageError) as caught:  # still the class 6.x callers caught
        document.to_bytes() if how == "to_bytes" else document.save(target)
    assert isinstance(caught.value, HwpxError)
    assert caught.value.code == "open-safety-failed"
    assert caught.value.suggestion
    assert "summary" in caught.value.context
    assert not target.exists()
