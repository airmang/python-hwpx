#!/usr/bin/env python3
"""DEV-013 — ``hp:connectLine`` is a shape-to-shape "smart connector", not a
standalone line, and its geometry-transform relationship cannot be reversed
from a single real sample — this is why train 14 (cycle 6.4) left authoring
for it deferred.

Schema claim: ``ConnectLineType`` (``ParaList XML schema.xml``) extends
``AbstractDrawingObjectType`` the same way ``LineType`` does — plain
``offset``/``orgSz``/``curSz``/``scaMatrix`` fields with no special
constraint written down, plus ``startPt``/``endPt`` (typed
``hp:ConnectPointType``, which is ``hc:PointType`` + ``subjectIDRef``/
``subjectIdx``) and an optional ``controlPoints`` list. Read in isolation
the schema does not say a connector's ``offset``/``curSz``/``scaMatrix`` are
*derived* from where its two anchor shapes sit — it looks like just another
drawing object with its own independent geometry.

Real-document measurement: ``reader_writer__SimpleConnectLine.hwpx``
(vendored) is the one "Simple" — i.e. purpose-built canonical, not an error-
regression fixture — connectLine sample in this corpus. Its ``startPt``/
``endPt`` carry non-zero ``subjectIDRef`` values that resolve to an actual
``hp:rect`` and ``hp:ellipse`` in the same document: this connector is
anchored to two other shapes, not free-floating. Its ``offset`` is negative,
serialized as the unsigned-32-bit wraparound of that negative value (e.g.
4294966971 == 2**32 - 325 == -325 as a signed int) rather than a literal
minus sign. Its ``curSz`` differs from its ``orgSz``, and its
``renderingInfo/hc:scaMatrix`` carries a translation component on top of
scale (not the identity matrix every other authored shape in this package
writes) — the whole tuple looks derived from the anchor shapes' positions by
a formula this repo has no way to reconstruct from one sample.

A second connectLine sample exists (``error__20230818__test.hwpx``,
vendored) with unattached endpoints (``subjectIDRef="0"``) — but its own
``scaMatrix`` is degenerate (``e1=0``, a non-invertible transform that
collapses the x-axis), and the file's own name flags it as an error-
regression fixture, not a clean baseline either. Between "anchored, with an
unreversible relationship" and "unattached, but structurally broken", there
is no sample this repo can safely generalize an authoring contract from.

Our handling: no ``add_connect_line``/``ensure_connect_line`` exists on
``doc.shapes`` — this is a deliberate absence, not an oversight (train 14's
own commit message and ``docs/support-matrix.md`` record the same evidence
this probe reproduces). The read/preserve path is unaffected: connectLine
elements already round-trip byte-identically through the patch path like any
other unauthored shape.

Run: ``python probes/dev013_connectline_smart_connector_relationship.py``
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lxml import etree  # noqa: E402

HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HC_NS = "http://www.hancom.co.kr/hwpml/2011/core"
CORPUS = ROOT / "tests" / "fixtures" / "hwpxlib_corpus"

_IDENTITY = {"e1": "1", "e2": "0", "e3": "0", "e4": "0", "e5": "1", "e6": "0"}


def main() -> int:
    canonical = CORPUS / "reader_writer__SimpleConnectLine.hwpx"
    degenerate = CORPUS / "error__20230818__test.hwpx"
    if not canonical.exists():
        print("SKIP: reader_writer__SimpleConnectLine.hwpx not found in vendored corpus")
        return 0

    with zipfile.ZipFile(canonical) as archive:
        name = next(n for n in archive.namelist() if n.endswith("section0.xml"))
        root = etree.fromstring(archive.read(name))
    (connect_line,) = root.iter(f"{{{HP_NS}}}connectLine")

    start_pt = connect_line.find(f"{{{HP_NS}}}startPt")
    end_pt = connect_line.find(f"{{{HP_NS}}}endPt")
    assert start_pt is not None and end_pt is not None
    start_subject = start_pt.get("subjectIDRef")
    end_subject = end_pt.get("subjectIDRef")
    assert start_subject not in (None, "0"), "expected an anchored startPt, not free-floating"
    assert end_subject not in (None, "0"), "expected an anchored endPt, not free-floating"

    # subjectIDRef resolves against instid, not id -- a further wrinkle this
    # probe pins: the two identity fields usually agree on a top-level shape
    # (id == instid on every shape this package authors) but the schema
    # keeps them distinct, and connectLine's cross-reference specifically
    # uses the one this package does not otherwise key by.
    subject_instids = {
        el.get("instid") for el in root.iter()
        if el.tag in (f"{{{HP_NS}}}rect", f"{{{HP_NS}}}ellipse")
    }
    assert start_subject in subject_instids, f"startPt subjectIDRef {start_subject!r} does not resolve to a shape's instid in this document"
    assert end_subject in subject_instids, f"endPt subjectIDRef {end_subject!r} does not resolve to a shape's instid in this document"
    print(f"connectLine anchored to two other shapes by instid (not id): startPt->{start_subject}, endPt->{end_subject}")

    offset = connect_line.find(f"{{{HP_NS}}}offset")
    assert offset is not None
    offset_x = int(offset.get("x", "0"))
    # unsigned-32-bit wraparound of a negative value
    assert offset_x > 2**31, f"expected an unsigned-32-bit-wrapped negative offset, got {offset_x}"
    signed_x = offset_x - 2**32
    print(f"offset.x={offset_x} (unsigned) == {signed_x} (signed) -- confirmed negative-via-wraparound")

    org_sz = connect_line.find(f"{{{HP_NS}}}orgSz")
    cur_sz = connect_line.find(f"{{{HP_NS}}}curSz")
    assert org_sz is not None and cur_sz is not None
    assert (org_sz.get("width"), org_sz.get("height")) != (cur_sz.get("width"), cur_sz.get("height"))
    print(f"orgSz={dict(org_sz.attrib)} != curSz={dict(cur_sz.attrib)}")

    sca_matrix = connect_line.find(f"{{{HP_NS}}}renderingInfo/{{{HC_NS}}}scaMatrix")
    assert sca_matrix is not None
    assert dict(sca_matrix.attrib) != _IDENTITY
    print(f"scaMatrix={dict(sca_matrix.attrib)} -- not identity (translation on top of scale)")

    if degenerate.exists():
        with zipfile.ZipFile(degenerate) as archive:
            name = next(n for n in archive.namelist() if n.endswith("section0.xml"))
            degenerate_root = etree.fromstring(archive.read(name))
        degenerate_connect_lines = list(degenerate_root.iter(f"{{{HP_NS}}}connectLine"))
        assert degenerate_connect_lines
        for cl in degenerate_connect_lines:
            start = cl.find(f"{{{HP_NS}}}startPt")
            assert start is not None and start.get("subjectIDRef") == "0", "expected unattached endpoints"
        # groupLevel="1" connectLines in this file each carry TWO
        # hc:scaMatrix siblings inside one renderingInfo (a group-level
        # transform stacked on the element's own) -- findall, not find, or
        # the degenerate second one is silently missed.
        degenerate_matrices = [
            m for cl in degenerate_connect_lines
            for m in cl.findall(f"{{{HP_NS}}}renderingInfo/{{{HC_NS}}}scaMatrix")
        ]
        assert any(m.get("e1") == "0" for m in degenerate_matrices), (
            "expected at least one known degenerate (non-invertible, e1=0) matrix"
        )
        print(f"second sample ({degenerate.name}) unattached but has a degenerate scaMatrix (e1=0) among its transforms -- confirmed unusable as a clean baseline")

    import hwpx.document as _document_module

    assert not hasattr(_document_module.HwpxDocument, "add_connect_line")
    doc = _document_module.HwpxDocument.new()
    assert not hasattr(doc.shapes, "add_connect_line")
    print("confirmed: no add_connect_line authoring entry point exists (deliberate)")

    print("PASS: DEV-013 reproduced (vendored evidence) and our handling (deferred) verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
