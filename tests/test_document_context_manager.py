from __future__ import annotations

import pytest

from hwpx.document import HwpxDocument
from hwpx.templates import blank_document_bytes


class _TrackingResource:
    def __init__(self, *, flush_error: bool = False, close_error: bool = False) -> None:
        self.flush_calls = 0
        self.close_calls = 0
        self.flush_error = flush_error
        self.close_error = close_error

    def flush(self) -> None:
        self.flush_calls += 1
        if self.flush_error:
            raise RuntimeError("flush failed")

    def close(self) -> None:
        self.close_calls += 1
        if self.close_error:
            raise RuntimeError("close failed")


def test_with_open_closes_internal_stream_when_exception_occurs() -> None:
    internal_stream = None

    with pytest.raises(RuntimeError, match="boom"):
        with HwpxDocument.open(blank_document_bytes()) as document:
            assert document._managed_resources
            internal_stream = document._managed_resources[0]
            assert getattr(internal_stream, "closed", False) is False
            raise RuntimeError("boom")

    assert internal_stream is not None
    assert internal_stream.closed is True


def test_context_manager_flushes_and_closes_managed_resource() -> None:
    document = HwpxDocument.new()
    tracked = _TrackingResource()
    document._managed_resources.append(tracked)

    with pytest.raises(ValueError, match="context"):
        with document:
            raise ValueError("context")

    assert tracked.flush_calls == 1
    assert tracked.close_calls == 1


def test_close_ignores_resource_cleanup_errors_and_continues() -> None:
    document = HwpxDocument.new()
    broken = _TrackingResource(flush_error=True, close_error=True)
    healthy = _TrackingResource()
    document._managed_resources.extend([broken, healthy])

    document.close()

    assert broken.flush_calls == 1
    assert broken.close_calls == 1
    assert healthy.flush_calls == 1
    assert healthy.close_calls == 1
