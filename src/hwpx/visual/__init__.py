# SPDX-License-Identifier: Apache-2.0
"""VisualComplete render gate (Phase A).

Public API::

    from hwpx.visual import RenderOracle, visual_check, VisualReport, EditMask

``visual_check`` renders a before/after ``.hwpx`` pair through Hancom (via
``RenderOracle``) and returns a ``VisualReport`` judging overlap / overflow /
out-of-mask change. Off-Windows (no Hancom) it degrades to a structural report
(``render_checked=False``) instead of crashing — see the module docstrings and
the implementation plan §0.0 for the assurance-tier contract.

The imaging stack (pymupdf / Pillow / numpy) is an optional dependency; install
it with ``pip install python-hwpx[visual]``. Importing this package never
requires it.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .masks import EditMask
from .report import VisualReport

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .oracle import RenderOracle, visual_check

__all__ = ["RenderOracle", "visual_check", "VisualReport", "EditMask"]


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


def __getattr__(name: str):
    # Lazy so importing the package stays light, and so running
    # ``python -m hwpx.visual.oracle`` does not pre-import the submodule
    # (which would trigger a runpy "found in sys.modules" RuntimeWarning).
    if name in ("RenderOracle", "visual_check"):
        from . import oracle

        return getattr(oracle, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

