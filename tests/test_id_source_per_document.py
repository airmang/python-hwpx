# SPDX-License-Identifier: Apache-2.0
"""A document's ``seed=``/``now=`` are its own (7.0).

Up to this change ``HwpxDocument.new(seed=..., now=...)`` put its id and clock source in force for the
whole thread until it was closed: another document made or edited meanwhile drew its ids from that
seed and dated its memos with that ``now``, two seeded documents open together each wrote other bytes
than when made alone, closing them in the order they were made left the first seed in force, and a
seeded document dropped without ``close()`` kept it in force for good. Now the source belongs to the
document: whatever else is open, made, closed or dropped, a document writes what it writes alone.
"""

from __future__ import annotations

import gc
import io
import threading
import zipfile
from datetime import datetime, timezone

from hwpx import HwpxDocument
from hwpx.oxml._document_primitives import IdSource
from hwpx.tools.document_merge import insert_document

FIXED = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _drawn(seed: int) -> set[str]:
    source = IdSource(seed)
    return {str(source.next_id()) for _ in range(500)}


def _section(doc: HwpxDocument) -> bytes:
    with zipfile.ZipFile(io.BytesIO(doc.to_bytes())) as archive:
        return archive.read("Contents/section0.xml")


def _new_ids(doc: HwpxDocument) -> set[str]:
    """Ids the document gives three new paragraphs (its first paragraph keeps the template's id)."""

    for text in ("1", "2", "3"):
        doc.add_paragraph(text)
    return {str(p.element.get("id")) for p in doc.paragraphs[1:]}


def _edit(doc: HwpxDocument, tag: str) -> None:
    doc.add_paragraph(tag)
    doc.add_table(1, 2)
    doc.notes.add_memo("메모 " + tag, paragraph=len(doc.paragraphs) - 1)


def _alone(seed: int, *tags: str) -> bytes:
    with HwpxDocument.new(seed=seed, now=FIXED) as doc:
        for tag in tags:
            _edit(doc, tag)
        return _section(doc)


def test_a_document_without_a_seed_stays_random_beside_a_seeded_one() -> None:
    with HwpxDocument.new(seed=7, now=FIXED) as seeded, HwpxDocument.new() as plain:
        assert _new_ids(plain).isdisjoint(_drawn(7))
        plain.notes.add_memo("메모", paragraph=1)
        assert FIXED.astimezone().strftime("%Y-%m-%dT%H:%M:%SZ").encode() not in _section(plain)
        _edit(seeded, "A")
        assert _section(seeded) == _alone(7, "A")


def test_two_seeded_documents_edited_in_turn_each_write_what_they_write_alone() -> None:
    x = HwpxDocument.new(seed=7, now=FIXED)
    y = HwpxDocument.new(seed=8, now=FIXED)
    same = HwpxDocument.new(seed=7, now=FIXED)
    with x, y, same:
        for step in ("1", "2"):
            _edit(x, "X" + step)
            _edit(y, "Y" + step)
            _edit(same, "X" + step)
        assert _section(x) == _alone(7, "X1", "X2") == _section(same)
        assert _section(y) == _alone(8, "Y1", "Y2")


def test_editing_an_unseeded_document_in_between_changes_nothing() -> None:
    with HwpxDocument.new(seed=7, now=FIXED) as seeded, HwpxDocument.new() as plain:
        for step in ("1", "2"):
            _edit(plain, "P" + step)
            _edit(seeded, "X" + step)
        assert _section(seeded) == _alone(7, "X1", "X2")


def test_closing_in_the_order_they_were_made_leaves_no_seed_behind() -> None:
    first = HwpxDocument.new(seed=7)
    second = HwpxDocument.new(seed=8)
    first.close()
    second.close()
    with HwpxDocument.new() as later:
        ids = _new_ids(later)
    assert ids.isdisjoint(_drawn(7)) and ids.isdisjoint(_drawn(8))


def test_a_seeded_document_dropped_without_close_leaves_no_seed_behind() -> None:
    def fails() -> None:
        HwpxDocument.new(seed=9).add_paragraph("버려짐")
        raise RuntimeError("중간 실패")

    try:
        fails()
    except RuntimeError:
        pass
    gc.collect()
    with HwpxDocument.new() as later:
        assert _new_ids(later).isdisjoint(_drawn(9))


def test_another_thread_does_not_see_the_seed() -> None:
    seen: list[set[str]] = []

    def other() -> None:
        with HwpxDocument.new() as doc:
            seen.append(_new_ids(doc))

    with HwpxDocument.new(seed=11):
        thread = threading.Thread(target=other)
        thread.start()
        thread.join()
    assert seen[0].isdisjoint(_drawn(11))


def test_a_copy_into_another_document_takes_the_receiving_documents_ids() -> None:
    with HwpxDocument.new(seed=101) as target, HwpxDocument.new(seed=202) as source:
        source.add_paragraph("원본")
        rectangle = source.add_paragraph("도형").add_rectangle(width=2000, height=1000)
        target.add_paragraph("받는 문서")
        before = {str(p.element.get("id")) for p in target.paragraphs}
        copied = source.paragraphs[0].copy_to(target.paragraphs[-1])
        rectangle.copy_to(target.paragraphs[-1])
        insert_document(target, source, after_paragraph_index=0)
        new = {str(p.element.get("id")) for p in target.paragraphs} - before
        assert copied.element.get("id") in new
        assert new <= _drawn(101)


def test_a_copy_into_an_unseeded_document_gets_random_ids() -> None:
    with HwpxDocument.new(seed=202) as source, HwpxDocument.new() as target:
        source.add_paragraph("원본")
        copied = source.paragraphs[0].copy_to(target.paragraphs[-1])
        assert copied.element.get("id") not in _drawn(202)


def _member_ids(group: object) -> list[str]:
    element = group.element  # type: ignore[attr-defined]
    return [str(node.get("instid")) for node in element.iter() if node is not element and node.get("instid")]


def test_group_members_get_their_ids_from_the_document_that_takes_them() -> None:
    from hwpx.objects import ContainerMember

    def build() -> tuple[bytes, list[str]]:
        with HwpxDocument.new(seed=5, now=FIXED) as doc:
            members = [ContainerMember.rect(0, 0, 2000, 1000), ContainerMember.ellipse(2500, 0, 1000, 1000)]
            assert [m.element.get("instid") for m in members] == ["", ""]  # none before a document takes them
            group = doc.shapes.add_container(members)
            ids = _member_ids(group)
            assert len(ids) == 2 and set(ids) <= _drawn(5)
            return _section(doc), ids

    assert build() == build()


def test_group_members_made_beside_a_seeded_document_do_not_touch_it() -> None:
    from hwpx.objects import ContainerMember

    with HwpxDocument.new(seed=7, now=FIXED) as seeded, HwpxDocument.new() as plain:
        members = [ContainerMember.rect(0, 0, 2000, 1000), ContainerMember.ellipse(2500, 0, 1000, 1000)]
        group = plain.shapes.add_container(members)
        assert set(_member_ids(group)).isdisjoint(_drawn(7))
        _edit(seeded, "A")
        assert _section(seeded) == _alone(7, "A")
