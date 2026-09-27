# SPDX-License-Identifier: Apache-2.0
"""Errors raised while reading or writing HWP 5.0 (``.hwp``) documents."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ..errors import HwpxError


class Hwp5Error(HwpxError, ValueError):
    """An HWP 5.0 document cannot be read or written.

    ``code`` names the reason: ``hwp5-damaged`` (the container or its records
    are broken), ``hwp5-password``, ``hwp5-distribution`` and ``hwp5-drm`` (the
    body is encrypted), ``hwp5-not-hwp5`` (a compound file without an HWP 5.0
    file header), ``hwp5-version-unsupported``, ``hwp5-limit-exceeded`` (the
    input exceeds a parsing limit) and ``hwp5-write-unsupported`` (the document
    holds content the HWP 5.0 writer cannot express).
    """

    default_code = "hwp5-damaged"


class Hwp5ConversionWarning(UserWarning):
    """Opening an ``.hwp`` left content out of the document model.

    The message names each kind that was not converted and how often.
    """


@dataclass(frozen=True)
class Hwp5ConversionReport:
    """What opening an ``.hwp`` document could not carry into the document
    model, as counts by kind (``HwpxDocument.conversion_report``).

    ``unconverted`` is content the document model can hold but the conversion
    does not produce yet; opening warns about it once
    (:class:`Hwp5ConversionWarning`). ``dropped`` is data HWPX has no element
    for, which is counted without a warning. Both are read-only.
    """

    unconverted: Mapping[str, int]
    dropped: Mapping[str, int]

    @classmethod
    def of(cls, unconverted: Mapping[str, int], dropped: Mapping[str, int]) -> "Hwp5ConversionReport":
        """A report holding read-only copies of *unconverted* and *dropped*."""

        return cls(MappingProxyType(dict(unconverted)), MappingProxyType(dict(dropped)))


def damaged(message: str, **context: object) -> Hwp5Error:
    """Build the error for a broken container or record stream."""

    return Hwp5Error(
        message,
        code="hwp5-damaged",
        context=context,
        suggestion="The file is truncated or corrupted; open and re-save it in Hancom Office.",
    )


def limit_exceeded(message: str, **context: object) -> Hwp5Error:
    """Build the error for an input that exceeds a parsing limit."""

    return Hwp5Error(message, code="hwp5-limit-exceeded", context=context)


def write_unsupported(message: str, **context: object) -> Hwp5Error:
    """Build the error for content the HWP 5.0 writer cannot express."""

    return Hwp5Error(message, code="hwp5-write-unsupported", context=context)
