# SPDX-License-Identifier: Apache-2.0
"""VisualComplete render gate (Phase A).

Public API::

    from hwpx.visual import resolve_oracle, visual_check, VisualReport, EditMask
    from hwpx.visual import WindowsComOracle, MacHancomOracle, NullOracle

``visual_check`` renders a before/after ``.hwpx`` pair through a Hancom backend
and returns a ``VisualReport`` judging overlap / overflow / out-of-mask change.
``resolve_oracle()`` picks the best reachable backend — ``WindowsComOracle``
(COM; CI/scale), then ``MacHancomOracle`` (``Hancom Office HWP.app`` via GUI;
dev/spot-check), else ``NullOracle``. With no Hancom reachable it degrades to a
structural report (``render_checked=False``) instead of crashing — see the
module docstrings and the implementation plan §0.0 for the assurance-tier
contract. ``RenderOracle`` is a backward-compatible alias of ``WindowsComOracle``.

The imaging stack (pymupdf / Pillow / numpy) is an optional dependency; install
it with ``pip install python-hwpx[visual]``. Importing this package never
requires it.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .masks import EditMask
from .fixture_corpus import FixtureCase, FixtureCorpus, FixturePage, load_fixture_manifest
from .page_qa import inspect_fixture_case, inspect_page_png, inspect_page_set
from .qa_contracts import (
    TAXONOMY_VERSION,
    DefectCategory,
    DocumentTarget,
    Evidence,
    FindingSeverity,
    NormalizedBBox,
    PageVerdict,
    Provenance,
    VerdictStatus,
    VisualFinding,
    VisualVerdict,
)
from .report import VisualReport

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .oracle import (
        MacHancomOracle,
        NullOracle,
        RenderBackend,
        RenderOracle,
        WindowsComOracle,
        resolve_oracle,
        visual_check,
    )

_ORACLE_EXPORTS = frozenset(
    {
        "RenderBackend",
        "WindowsComOracle",
        "MacHancomOracle",
        "NullOracle",
        "RenderOracle",
        "resolve_oracle",
        "visual_check",
    }
)

__all__ = [
    "resolve_oracle",
    "visual_check",
    "RenderBackend",
    "WindowsComOracle",
    "MacHancomOracle",
    "NullOracle",
    "RenderOracle",
    "VisualReport",
    "EditMask",
    "TAXONOMY_VERSION",
    "DefectCategory",
    "FindingSeverity",
    "VerdictStatus",
    "NormalizedBBox",
    "Evidence",
    "Provenance",
    "DocumentTarget",
    "VisualFinding",
    "PageVerdict",
    "VisualVerdict",
    "FixturePage",
    "FixtureCase",
    "FixtureCorpus",
    "load_fixture_manifest",
    "inspect_page_png",
    "inspect_page_set",
    "inspect_fixture_case",
]


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


def __getattr__(name: str):
    # Lazy so importing the package stays light, and so running
    # ``python -m hwpx.visual.oracle`` does not pre-import the submodule
    # (which would trigger a runpy "found in sys.modules" RuntimeWarning).
    if name in _ORACLE_EXPORTS:
        from . import oracle

        return getattr(oracle, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
