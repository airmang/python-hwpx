from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument


def test_to_bytes_returns_hwpx_bytes() -> None:
    document = HwpxDocument.new()

    output = document.to_bytes()

    assert isinstance(output, bytes)
    assert output.startswith(b"PK")


def test_save_to_path_returns_same_path(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    output_path = tmp_path / "saved.hwpx"

    result = document.save_to_path(output_path)

    assert result == output_path
    assert output_path.exists()


def test_save_to_stream_returns_same_stream() -> None:
    document = HwpxDocument.new()
    stream = BytesIO()

    result = document.save_to_stream(stream)

    assert result is stream
    stream.seek(0)
    assert stream.read(2) == b"PK"


def test_save_deprecated_wrapper_warns_and_routes_to_new_methods(tmp_path: Path) -> None:
    document = HwpxDocument.new()

    with pytest.deprecated_call(match="deprecated"):
        path_result = document.save(tmp_path / "wrapped-path.hwpx")
    assert path_result == tmp_path / "wrapped-path.hwpx"

    with pytest.deprecated_call(match="deprecated"):
        bytes_result = document.save()
    assert isinstance(bytes_result, bytes)

    stream = BytesIO()
    with pytest.deprecated_call(match="deprecated"):
        stream_result = document.save(stream)
    assert stream_result is stream
