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
from hwpx.opc.package import HwpxPackageError


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


class _ShortEachTime(io.BytesIO):
    """Takes as many bytes of each write as the next of *limits* says."""

    def __init__(self, held: bytes, limits: list[int]) -> None:
        super().__init__(held)
        self._limits = iter(limits)

    def write(self, data) -> int:  # type: ignore[no-untyped-def, override]
        return super().write(bytes(data)[: next(self._limits)])


@pytest.mark.parametrize("format", ["hwp", "hwpx"])
def test_the_stream_is_put_back_also_when_it_takes_the_old_content_in_parts(format: str) -> None:
    """The rollback wrote the old content with one ``write`` and did not look at what was taken: a stream
    that took one byte of it kept seven bytes of the new file's header."""

    stream = _ShortEachTime(b"original contents", [8, 1, 20])
    stream.seek(0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with pytest.raises(OSError, match="short write"):
            _document().save(stream, format=format)
    assert (stream.getvalue(), stream.tell()) == (b"original contents", 0)


def test_a_hwp_file_is_never_reported_as_the_source_byte_for_byte() -> None:
    """The receipt measures the HWPX parts; the file written is HWP 5.0. An unedited document saved as
    ``.hwp`` used to say ``whole_package_identical`` though the two files share no byte."""

    source = _document().to_bytes()
    stream = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        report = HwpxDocument.open(source).save(stream, format="hwp")
    assert report.preservation.whole_package_identical is False
    assert HwpxDocument.open(source).save(io.BytesIO()).preservation.whole_package_identical is True


class _BytesOnly(io.BytesIO):
    """Takes three bytes of the first write, then whole writes of ``bytes`` and nothing else."""

    def __init__(self, held: bytes) -> None:
        super().__init__(held)
        self._calls = 0

    def write(self, data) -> int:  # type: ignore[no-untyped-def, override]
        self._calls += 1
        if self._calls == 1:
            return super().write(data[:3])
        if not isinstance(data, bytes):
            raise TypeError("bytes required")
        return super().write(data)


def test_the_rollback_gives_the_stream_bytes_as_the_save_does() -> None:
    from hwpx.opc.package import _write_stream_or_rollback as package_write
    from hwpx.quality.save_pipeline import write_stream_or_rollback as pipeline_write

    for write in (pipeline_write, package_write):
        stream = _BytesOnly(b"abcdef")
        with pytest.raises((OSError, HwpxPackageError), match="short write"):  # the package's own error
            write(stream, b"XXXXX")
        assert stream.getvalue() == b"abcdef"
