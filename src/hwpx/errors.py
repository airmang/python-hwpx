# SPDX-License-Identifier: Apache-2.0
"""Structured exception base for python-hwpx (S-091 P2).

Every fail-closed public contract raises a :class:`HwpxError` (or a subclass).
The base carries three machine-readable fields on top of the human-readable
message, so a caller can branch on a stable ``code``, read the measured
``context``, and surface an actionable ``suggestion`` without parsing prose:

- ``code`` — a stable, kebab-case identifier for the failure class. Callers may
  switch on it; it is part of the contract and changes only on a major boundary.
- ``context`` — a JSON-serialisable dict of the measured values that triggered
  the failure (offending parts, indices, counts…). Empty when there is nothing
  to measure.
- ``suggestion`` — one actionable next step, or ``None`` when there is nothing
  specific to advise.

``str(exc)`` stays the human sentence (the ``message``), so existing ``except``
handlers and log lines are unchanged. Subclasses set :attr:`default_code`, which
lets a historical ``raise Subclass("message")`` site keep working while gaining
the structured fields with no raise-site churn (§11 — no bulk raise rewrites).
"""

from __future__ import annotations

from typing import Any, Mapping


class HwpxError(Exception):
    """Base for structured, fail-closed python-hwpx errors."""

    #: Stable ``code`` used when a raise site does not pass an explicit ``code``.
    default_code: str = "hwpx-error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        context: Mapping[str, Any] | None = None,
        suggestion: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.default_code
        self.context: dict[str, Any] = dict(context) if context else {}
        self.suggestion = suggestion

    def to_dict(self) -> dict[str, Any]:
        """The structured envelope: ``code`` / ``message`` / ``context`` / ``suggestion``."""

        return {
            "code": self.code,
            "message": self.message,
            "context": dict(self.context),
            "suggestion": self.suggestion,
        }


class SaveError(HwpxError, ValueError):
    """A representative save path (``save_to_path`` / ``save_to_stream`` /
    ``to_bytes``) failed closed before writing any output.

    Subclasses :class:`ValueError` for backward compatibility: pre-4.0 callers
    caught ``ValueError`` from these paths and must keep working.
    """

    default_code = "save-failed"


__all__ = ["HwpxError", "SaveError"]
