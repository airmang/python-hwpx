"""Where a floating object is on the page, for comparing python-hwpx's ``hp:pos`` with what Hangul saved.

Hangul hangs an object it moved on the paragraph at whose height it now starts and measures its offset down from
that paragraph; python-hwpx keeps one moved down on its paragraph and measures it from there, which draws it in the
same spot (objlim's rule, rotate9). (One moved above its paragraph python-hwpx hangs as Hangul does when it knows the
line layout, rotate12: Hangul does not draw it above that paragraph's top where its offset says.) To compare the two, Hangul's down offset is carried over to python-hwpx's paragraph:
less the heights of the paragraphs in between when Hangul's is above, plus them when it is below. A paragraph's
height (its lines and the spacing after them) is read from a Hangul-saved layout of the document before the change.
"""

from __future__ import annotations

from typing import Any

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def paragraph_heights(document: Any, *, first_line_only: bool = False) -> list[int | None]:
    """Each body paragraph's height in a Hangul-saved *document* (an ``HwpxDocument``): its lines and the spacing
    after them; with *first_line_only*, its first line's (a short paragraph Hangul laid out around an object it
    moved there wraps, so its height is its first line's)."""

    heights: list[int | None] = []
    for paragraph in document.paragraphs:
        lines = paragraph.element.findall(f"{HP}linesegarray/{HP}lineseg")
        if not lines:
            heights.append(None)
            continue
        last = lines[0] if first_line_only else lines[-1]
        heights.append(int(last.get("vertpos")) + int(last.get("vertsize")) + int(last.get("spacing"))
                       - int(lines[0].get("vertpos")))
    return heights


def paragraph_index(document: Any, obj: Any) -> int:
    """The index of the body paragraph of *document* holding *obj*."""

    return [paragraph.element for paragraph in document.paragraphs].index(obj.paragraph.element)


def carry_down_offset(theirs: Any, their_paragraph: int, our_paragraph: int, heights: list[int | None]) -> None:
    """Carry Hangul's down offset of *theirs* (an element, changed in place) from its paragraph to *our_paragraph*,
    when it is measured from its paragraph (``vertRelTo`` PARA)."""

    position = theirs.find(f"{HP}pos")
    if position is None or position.get("vertRelTo") != "PARA" or their_paragraph == our_paragraph:
        return
    low, high = sorted((their_paragraph, our_paragraph))
    between = heights[low:high]
    if any(height is None for height in between):
        raise ValueError("a paragraph in between has no line layout")
    moved = sum(h for h in between if h is not None) * (1 if their_paragraph < our_paragraph else -1)
    offset = int(position.get("vertOffset", "0")) & 0xFFFFFFFF
    offset = offset - (1 << 32) if offset >= 1 << 31 else offset
    position.set("vertOffset", str((offset - moved) & 0xFFFFFFFF))


def lay_out(document: Any, tops: list[int]) -> None:
    """Give the first body paragraphs of *document* (an ``HwpxDocument`` python-hwpx made) the line layout Hangul gave
    the same document: one line each, starting *tops* down the page (``hp:lineseg/@vertpos``; a one-line paragraph of
    the default 10-point text is 1600 high in every Hangul-saved file here)."""

    for paragraph, top in zip(document.paragraphs, tops):
        element = paragraph.element
        array = element.makeelement(f"{HP}linesegarray", {})
        array.append(array.makeelement(f"{HP}lineseg", {
            "textpos": "0", "vertpos": str(top), "vertsize": "1000", "textheight": "1000", "baseline": "850",
            "spacing": "600", "horzpos": "0", "horzsize": "42520", "flags": "393216"}))
        element.append(array)
