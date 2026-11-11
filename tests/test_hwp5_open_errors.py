# SPDX-License-Identifier: Apache-2.0
"""Opening a damaged or oversized ``.hwp`` fails with :class:`Hwp5Error`."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import Hwp5Error
from hwpx.hwp5 import cfb, records
from hwpx.hwp5 import package as hwp5_package


def _hwp_bytes(text: str = "AQZ") -> bytes:
    document = HwpxDocument.new()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save_to_stream(buffer, format="hwp")
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("raised", "code"),
    [
        (RecursionError("maximum recursion depth exceeded"), "hwp5-limit-exceeded"),
        (MemoryError(), "hwp5-limit-exceeded"),
        (ValueError("not enough values to unpack"), "hwp5-damaged"),
        (OverflowError("date value out of range"), "hwp5-damaged"),
        (UnicodeEncodeError("utf-16-le", "\ud800", 0, 1, "surrogates not allowed"), "hwp5-damaged"),
    ],
)
def test_a_failure_while_converting_is_an_hwp5_error(
    monkeypatch: pytest.MonkeyPatch, raised: BaseException, code: str
) -> None:
    def fail(data: bytes) -> hwp5_package.Converted:
        raise raised

    monkeypatch.setattr(hwp5_package, "_convert", fail)
    with pytest.raises(Hwp5Error) as caught:
        HwpxDocument.open(io.BytesIO(_hwp_bytes()))
    assert caught.value.code == code
    assert caught.value.__cause__ is raised


def test_an_hwp5_error_passes_through_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    original = Hwp5Error("password", code="hwp5-password")

    def fail(data: bytes) -> hwp5_package.Converted:
        raise original

    monkeypatch.setattr(hwp5_package, "_convert", fail)
    with pytest.raises(Hwp5Error) as caught:
        hwp5_package.convert(_hwp_bytes())
    assert caught.value is original


def test_text_holding_half_a_surrogate_pair_is_reported_as_damage() -> None:
    streams = []
    replaced = False
    for name, data in cfb.read_all_streams(cfb.CompoundFile(_hwp_bytes("AQZ"))):
        if name == "BodyText/Section0":
            body = records.inflate(data, name)
            marker = "AQZ".encode("utf-16-le")
            assert marker in body
            body = body.replace(marker, b"A\x00\x00\xd8Z\x00")
            data = records.deflate(body)
            replaced = True
        streams.append((name, data))
    assert replaced
    with pytest.raises(Hwp5Error) as caught:
        HwpxDocument.open(io.BytesIO(cfb.build_compound_file(streams)))
    assert caught.value.code == "hwp5-damaged"
    assert isinstance(caught.value.__cause__, UnicodeEncodeError)


class _CountingStream(io.BytesIO):
    largest_read = 0

    def read(self, size: int | None = -1) -> bytes:
        data = super().read(size)
        self.largest_read = max(self.largest_read, len(data))
        return data


def test_a_file_beyond_the_size_limit_is_refused_without_reading_all_of_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data = _hwp_bytes()
    limit = len(data) // 2
    monkeypatch.setattr(hwp5_package, "MAX_FILE_BYTES", limit)

    stream = _CountingStream(data)
    with pytest.raises(Hwp5Error) as caught:
        HwpxDocument.open(stream)
    assert caught.value.code == "hwp5-limit-exceeded"
    assert stream.largest_read <= limit + 1

    path = tmp_path / "large.hwp"
    path.write_bytes(data)
    with pytest.raises(Hwp5Error) as caught:
        HwpxDocument.open(path)
    assert caught.value.code == "hwp5-limit-exceeded"


def test_a_file_within_the_size_limit_opens() -> None:
    document = HwpxDocument.open(io.BytesIO(_hwp_bytes("AQZ")))
    assert "AQZ" in document.text.plain()
