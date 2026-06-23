"""Standard mutation battery for the lineSegArray baseline measurement.

Each mutation applies a realistic text-length change to a document using the
public python-hwpx editing API, exercising the layout-cache path. The SAME
mutation is applied under lineseg ON and OFF (see lineseg_toggle) to form a
control pair whose Hancom renders are then compared.

The mutations are deliberately content-agnostic: they target the first
non-empty text paragraph so they apply to any corpus document.
"""
from __future__ import annotations

from dataclasses import dataclass

# A long Korean filler used to force "short -> long". If a retained line-segment
# cache (which describes FEWER characters than now present) is trusted by the
# renderer, this is the case most likely to surface overlapping glyphs.
_KO_LONG = "서울특별시 강남구 테헤란로 123길 45, 678호 (역삼동, 가나다빌딩) 추가 기재 사항입니다"
_KO_PAD = "가나다라마바사아자차카타파하"


@dataclass
class MutationResult:
    kind: str
    applied: bool
    detail: str
    paragraph_index: int | None = None
    old_len: int | None = None
    new_len: int | None = None


def _first_text_paragraph(doc):
    for idx, paragraph in enumerate(doc.paragraphs):
        try:
            text = paragraph.text
        except Exception:
            text = ""
        if text and text.strip():
            return idx, paragraph
    return None, None


def short_to_long(doc) -> MutationResult:
    idx, paragraph = _first_text_paragraph(doc)
    if paragraph is None:
        return MutationResult("short_to_long", False, "no text paragraph found")
    old = paragraph.text
    new = f"{old} {_KO_LONG}"
    paragraph.text = new
    return MutationResult(
        "short_to_long", True, "appended long korean run", idx, len(old), len(new)
    )


def long_to_short(doc) -> MutationResult:
    idx, paragraph = _first_text_paragraph(doc)
    if paragraph is None:
        return MutationResult("long_to_short", False, "no text paragraph found")
    old = paragraph.text
    new = old[: max(1, len(old) // 3)]
    paragraph.text = new
    return MutationResult(
        "long_to_short", True, "truncated to ~one third", idx, len(old), len(new)
    )


def same_length_ko(doc) -> MutationResult:
    idx, paragraph = _first_text_paragraph(doc)
    if paragraph is None:
        return MutationResult("same_length_ko", False, "no text paragraph found")
    old = paragraph.text
    new = "".join(_KO_PAD[i % len(_KO_PAD)] for i in range(len(old)))
    paragraph.text = new
    return MutationResult(
        "same_length_ko", True, "same-length korean replacement", idx, len(old), len(new)
    )


MUTATIONS = {
    "short_to_long": short_to_long,
    "long_to_short": long_to_short,
    "same_length_ko": same_length_ko,
}
