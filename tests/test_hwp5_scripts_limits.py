# SPDX-License-Identifier: Apache-2.0
"""``Scripts/DefaultJScript`` is read within the same bounds as every other stream."""

from __future__ import annotations

import io
import struct
import zlib

import pytest

from hwpx import HwpxDocument
from hwpx.errors import Hwp5Error
from hwpx.hwp5 import cfb, records
from hwpx.hwp5 import summary as sm

_LIMIT = 64 * 1024


def _deflated(raw: bytes) -> bytes:
    packer = zlib.compressobj(9, zlib.DEFLATED, -15)
    return packer.compress(raw) + packer.flush()


def test_a_script_stream_beyond_the_inflate_limit_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(records, "MAX_INFLATED_BYTES", _LIMIT)
    oversized = _deflated(struct.pack("<i", -1) + b"\0" * (_LIMIT * 4))
    with pytest.raises(Hwp5Error) as caught:
        sm.read_scripts(oversized, is_compressed=True)
    assert caught.value.code == "hwp5-limit-exceeded"


def test_opening_a_document_with_an_oversized_script_stream_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    buffer = io.BytesIO()
    HwpxDocument.new().save_to_stream(buffer, format="hwp")
    streams = [
        (name, data)
        for name, data in cfb.read_all_streams(cfb.CompoundFile(buffer.getvalue()))
        if name != "Scripts/DefaultJScript"
    ]
    monkeypatch.setattr(records, "MAX_INFLATED_BYTES", 4 * 1024 * 1024)
    streams.append(("Scripts/DefaultJScript", _deflated(struct.pack("<i", -1) + b"\0" * (16 * 1024 * 1024))))
    with pytest.raises(Hwp5Error) as caught:
        HwpxDocument.open(io.BytesIO(cfb.build_compound_file(streams)))
    assert caught.value.code == "hwp5-limit-exceeded"


def test_a_script_stream_within_the_limit_still_reads() -> None:
    stream = sm.write_scripts(sm.DEFAULT_HEADER_SCRIPT, "function f(){}\r\n")
    assert sm.read_scripts(stream, is_compressed=True) == [sm.DEFAULT_HEADER_SCRIPT, "function f(){}\r\n", "", ""]


def test_a_stream_that_is_not_deflate_is_unreadable_not_an_error() -> None:
    assert sm.read_scripts(b"\xff\xff\xff\xff\xff", is_compressed=True) is None


@pytest.mark.parametrize("is_compressed", [True, False])
def test_a_stream_listing_more_scripts_than_a_document_holds_is_unreadable(is_compressed: bool) -> None:
    raw = b"\0" * (4 * (sm.MAX_SCRIPTS + 10)) + struct.pack("<i", -1)
    assert sm.read_scripts(_deflated(raw) if is_compressed else raw, is_compressed=is_compressed) is None
