"""Saving as ``.hwp`` to a stream checks the write, as the ``.hwpx`` stream save does (exec7/rv3).

``doc.save(stream, format="hwp")`` called ``stream.write(...)`` and returned a receipt whatever the stream
took: a stream that wrote 64 of 10,752 bytes got a ``MutationReport``. It now goes through the same
``write_stream_or_rollback`` as ``.hwpx``: a short write is an ``OSError`` and the stream is put back as
it was.
"""

from __future__ import annotations

import io
import warnings

import pytest

from hwpx import HwpxDocument


class _Short(io.BytesIO):
    """Takes the first 64 bytes of what it is given and says so."""

    def write(self, data) -> int:  # type: ignore[no-untyped-def, override]
        return super().write(bytes(data)[:64])


def _document() -> HwpxDocument:
    document = HwpxDocument.new()
    document.add_paragraph("스트림에 쓰는 문단")
    return document


@pytest.mark.parametrize("format", ["hwp", "hwpx"])
def test_a_short_write_is_an_error_and_the_stream_is_put_back(format: str) -> None:
    stream = _Short()
    stream.write(b"kept")  # what the stream held before the save
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # .hwp writing announces itself once
        with pytest.raises(OSError, match="short write"):
            _document().save(stream, format=format)
    assert stream.getvalue() == b"kept"


def test_a_whole_write_still_saves_the_hwp_file() -> None:
    stream = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        report = _document().save(stream, format="hwp")
    assert report.path is None
    assert "스트림에 쓰는 문단" in [paragraph.text for paragraph in HwpxDocument.open(stream.getvalue()).paragraphs]
