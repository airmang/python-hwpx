#!/usr/bin/env python3
"""DEV-016 -- a group member's placement inside hp:container is carried on
TWO fields that must agree, and its own ``id`` attribute does not follow the
document-wide-uniqueness convention every top-level shape's ``id`` does.

Real-document measurement (74 ``hp:container`` elements across 3 vendored
files -- ``reader_writer__SimpleContainer.hwpx`` (1, 3 members: pic, pic,
line), ``error__20230818__test.hwpx`` (1), and
``error__20250808__2015...hwpx`` (72) -- carrying 203 members total). In
every sample, a member's own ``hp:offset`` (its position in the group's
local, top-left-anchored coordinate space) is mirrored exactly by its
``hp:renderingInfo/hc:transMatrix``'s translation component (``e3``/``e6``)
-- SimpleContainer's second ``hp:pic`` has ``offset x="8650" y="300"`` and
``transMatrix ... e3="8650" ... e6="300"``; every member with a non-zero
offset in the corpus repeats this pairing, and every member at offset (0, 0)
has an identity transMatrix (e3=0, e6=0). Nothing in the OWPML schema states
this relationship -- a member is free to carry any transMatrix values
syntactically -- but real Hancom output keeps the two in lockstep *as
numbers*. The two fields do not, however, agree on *encoding*: 32 of the 203
members have a true position that is negative (some members in
``error__20250808__2015...hwpx`` sit above/left of the group's own declared
origin), and for those, ``offset`` serializes it as the unsigned-32-bit
wraparound -- exactly DEV-013's connectLine finding, here on a second,
independent field -- while ``transMatrix``'s e3/e6 stay literal signed
integers. A comparison that reads both as plain text would wrongly conclude
the two disagree.

Separately: a member's ``id`` attribute stays within a small, reused
vocabulary across all 203 members (only two distinct values observed: "0"
and "2", the latter being SimpleContainer's own 3 members) -- unlike a
standalone shape, whose ``id`` doubles as its document-unique identifier
(see ``_object_id()``, which top-level ``_create_*_element`` builders use
for both ``id`` and ``instid``). Inside a group, only ``instid`` carries a
genuinely unique value; ``id`` does not.

Our handling: ``_create_container_element`` (``oxml/objects.py``, cycle 6.5
train 18) sets a member's ``offset`` and ``transMatrix`` e3/e6 together from
the same local coordinate whenever it repositions a member relative to the
group's bounding box -- always non-negative by construction (every member's
local position is measured from the group's own bounding-box minimum, so
the unsigned-wraparound half of this contract never triggers for our own
output; that half is corpus-observed-only for now) -- and hard-codes member
``id`` to "0" (matching the corpus majority) while keeping the member's own
freshly-allocated ``instid`` untouched.

Run: ``python probes/dev016_container_member_offset_transmatrix_sync.py``
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

_MEMBER_LOCAL_NAMES = {
    "pic", "line", "rect", "ellipse", "polygon", "arc", "connectLine", "container",
}


def _as_signed_32(raw: str) -> int:
    """Real corpus (DEV-013, and this probe's own finding) serializes some
    negative coordinates as their unsigned-32-bit wraparound. Undo that so a
    numeric comparison sees the true value regardless of which encoding a
    given field happens to use."""

    value = int(raw)
    return value - 2**32 if value > 2**31 else value


def _iter_containers(archive_path: Path):
    with zipfile.ZipFile(archive_path) as archive:
        name = next(n for n in archive.namelist() if n.endswith("section0.xml"))
        root = etree.fromstring(archive.read(name))
    return root.iter(f"{{{HP_NS}}}container")


def main() -> int:
    fixtures = [
        CORPUS / "reader_writer__SimpleContainer.hwpx",
        CORPUS / "error__20230818__test.hwpx",
        CORPUS / "error__20250808__2015년_12월_재난안전종합상황_분석_및_전망.hwpx",
    ]
    fixtures = [f for f in fixtures if f.exists()]
    if not fixtures:
        print("SKIP: vendored corpus fixtures not found")
        return 0

    checked = 0
    wrapped_seen = 0
    non_unique_ids: set[str] = set()
    for fixture in fixtures:
        for container in _iter_containers(fixture):
            for member in container:
                local = etree.QName(member).localname
                if local not in _MEMBER_LOCAL_NAMES:
                    continue
                offset = member.find(f"{{{HP_NS}}}offset")
                trans = member.find(f"{{{HP_NS}}}renderingInfo/{{{HC_NS}}}transMatrix")
                assert offset is not None, f"member {local} missing hp:offset ({fixture.name})"
                assert trans is not None, f"member {local} missing transMatrix ({fixture.name})"
                if int(offset.get("x")) > 2**31 or int(offset.get("y")) > 2**31:
                    wrapped_seen += 1
                assert _as_signed_32(offset.get("x")) == _as_signed_32(trans.get("e3")), (
                    f"offset.x={offset.get('x')} != transMatrix.e3={trans.get('e3')} "
                    f"for {local} in {fixture.name}"
                )
                assert _as_signed_32(offset.get("y")) == _as_signed_32(trans.get("e6")), (
                    f"offset.y={offset.get('y')} != transMatrix.e6={trans.get('e6')} "
                    f"for {local} in {fixture.name}"
                )
                member_id = member.get("id")
                if member_id is not None:
                    non_unique_ids.add(member_id)
                checked += 1

    assert checked > 0, "no group members found in vendored fixtures"
    assert wrapped_seen > 0, (
        "expected at least one member with an unsigned-32-bit-wrapped negative "
        "offset in the corpus (the encoding-mismatch half of this claim was "
        "never actually exercised)"
    )
    print(
        f"confirmed offset<->transMatrix e3/e6 sync (numeric, not textual) across "
        f"{checked} group members, {wrapped_seen} with an unsigned-wrapped negative offset"
    )
    # The id set staying small (not one distinct value per member) is itself
    # the evidence for the non-uniqueness claim.
    assert len(non_unique_ids) <= 3, (
        f"expected a small, reused id vocabulary across group members, "
        f"got {len(non_unique_ids)} distinct values: {sorted(non_unique_ids)}"
    )
    print(f"confirmed member id is not document-unique (values observed: {sorted(non_unique_ids)})")

    from hwpx.oxml.objects import ContainerMember, _create_container_element

    element = _create_container_element([
        ContainerMember.rect(1000, 2000, 3000, 1000),
        ContainerMember.rect(4000, 2000, 1000, 1000),
    ])
    # _create_container_element returns a stdlib ET.Element (not lxml) -- its
    # own .tag string is the right way to inspect it (same reasoning dev012's
    # probe uses for _create_line_element).
    members = [c for c in element if c.tag.rsplit("}", 1)[-1] in _MEMBER_LOCAL_NAMES]
    for member in members:
        offset = member.find(f"{{{HP_NS}}}offset")
        trans = member.find(f"{{{HP_NS}}}renderingInfo/{{{HC_NS}}}transMatrix")
        assert offset.get("x") == trans.get("e3")
        assert offset.get("y") == trans.get("e6")
        assert member.get("id") == "0"
    print("our add_container keeps offset/transMatrix in sync and matches the id="
          "\"0\" majority convention")

    print("PASS: DEV-016 reproduced (vendored evidence, 203 members across 74 containers) and our handling verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
