# SPDX-License-Identifier: Apache-2.0
"""``hwpx.tools.id_integrity`` -- referential-integrity gate itself.

Found while gating document_merge's MEMO-merge feature (train 38, cycle
6.10): a fresh document's own ``hp:secPr`` always carries
``memoShapeIDRef="0"`` (Hancom's own "no memo shape override" skeleton
default), which was only tolerated by ``_EMPTY_TABLE_IS_ALLOWED`` while the
``memo_shapes`` table happened to be completely empty -- any real feature
that populates it (``ensure_memo_shape`` directly, or ``document_merge``
copying a memo shape) newly exposed it as a dangling reference on *every*
document, unrelated to whatever actually populated the table. Pre-existing
and orthogonal to document_merge; not caught earlier because no prior test
combined a real memo shape with a referential-integrity check.
"""

from __future__ import annotations

from hwpx.document import HwpxDocument
from hwpx.tools.id_integrity import check_id_integrity


def test_fresh_document_passes_before_any_memo_shape_exists() -> None:
    doc = HwpxDocument.new()
    report = check_id_integrity(doc)
    assert report.ok, report.dangling


def test_ensure_memo_shape_alone_does_not_dangle_the_skeleton_secpr() -> None:
    """No merge involved at all -- reproduces with nothing but a bare
    ensure_memo_shape call, confirming the gap was in the checker itself,
    not in whatever populates the memo_shapes table."""

    doc = HwpxDocument.new()
    doc.styles.ensure_memo_shape(fill_color="#F0FFE9")

    report = check_id_integrity(doc)
    assert report.ok, report.dangling


def test_a_genuinely_dangling_memo_shape_id_is_still_caught() -> None:
    """The sentinel-widening fix must not blanket-ignore memoShapeIDRef --
    only "0" is Hancom's own unconditional default; any other unresolved
    value must still be reported."""

    doc = HwpxDocument.new()
    doc.styles.ensure_memo_shape(fill_color="#F0FFE9")
    for section in doc.sections:
        for node in section.element.iter():
            if node.tag.endswith("}secPr"):
                node.set("memoShapeIDRef", "999")

    report = check_id_integrity(doc)
    assert not report.ok
    assert any(d.attr == "memoShapeIDRef" and d.value == "999" for d in report.dangling)
