# SPDX-License-Identifier: Apache-2.0
"""``Highlight`` — one ``hp:markpenBegin``/``markpenEnd`` pair, read or written.

Pure result payload (design table style: frozen dataclass + ``to_dict()``,
``TrackedChange``'s shape) rather than a live view — a highlight is a text
range, not a standalone element with its own settable property the way
``CheckBox.checked`` is.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..model import Paragraph


@dataclass(frozen=True)
class Highlight:
    """One highlighted text range.

    ``color`` is the raw ``#RRGGBB`` OWPML value read from ``markpenBegin``,
    or ``None`` when the mark carries no ``color`` attribute — the schema
    (``ParaList XML schema.xml``) makes it optional, and real Hancom output
    has been observed dropping it on a re-save.

    ``paragraph`` is always set — unlike :class:`TrackedChange`, there is no
    low-level primitive that mints a ``Highlight`` without anchoring it to
    body text.
    """

    text: str
    color: str | None
    paragraph: "Paragraph | None" = None

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "color": self.color}


__all__ = ["Highlight"]
