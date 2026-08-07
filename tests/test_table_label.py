# SPDX-License-Identifier: Apache-2.0
"""hp:label read/write model (DEV-023, cycle 6.7 train 26).

hp:label (Avery-style label-sheet/nameplate print layout) was the last
code-blind high-frequency element the completeness ledger found (64/237
real files in the census population, 27%). The vendored 47-file corpus has
no examples -- structure was reverse-engineered from 75 of the
maintainer's private real-world documents (school administrative
paperwork). That private corpus's path is never recorded anywhere,
including here (privacy) -- every value in this file is synthetic, not
copied from any real document. See docs/owpml-deviations.md's DEV-023
entry for the reverse-engineering evidence (schema/real-output agreement,
the 2 observed attribute-combination clusters, the always-last-child
position).
"""
from __future__ import annotations

import io

import pytest

from hwpx.document import HwpxDocument
from hwpx.oxml.body import Label
from hwpx.oxml.namespaces import tag_local_name


def test_table_label_defaults_to_none() -> None:
    doc = HwpxDocument.new()
    table = doc.sections[0].add_paragraph().add_table(2, 2)

    assert table.label is None


def test_set_label_creates_and_places_as_last_child() -> None:
    """DEV-023: 실코퍼스 436/436이 hp:label을 hp:tbl의 마지막 자식으로
    둔다(모든 hp:tr 뒤) -- 스키마 시퀀스 순서와도 일치."""

    doc = HwpxDocument.new()
    table = doc.sections[0].add_paragraph().add_table(2, 2)

    label = table.set_label(
        topmargin=2500, leftmargin=900, boxwidth=18000, boxlength=7500,
        boxmarginhor=450, boxmarginver=0, labelcols=3, labelrows=8,
        landscape="WIDELY", pagewidth=59528, pageheight=84188,
    )

    assert isinstance(label, Label)
    assert label.labelcols == 3
    assert label.labelrows == 8
    children = [tag_local_name(c.tag) for c in table.element]
    assert children[-1] == "label", children


def test_set_label_round_trips_through_a_real_document() -> None:
    doc = HwpxDocument.new()
    table = doc.sections[0].add_paragraph().add_table(2, 2)
    table.set_label(
        topmargin=2500, leftmargin=900, boxwidth=18000, boxlength=7500,
        boxmarginhor=450, boxmarginver=0, labelcols=3, labelrows=8,
        landscape="WIDELY", pagewidth=59528, pageheight=84188,
    )

    out = doc.to_bytes()
    doc.close()

    reopened = HwpxDocument.open(io.BytesIO(out))
    reopened_table = next(
        t for p in reopened.sections[0].paragraphs for t in p.tables
    )
    label = reopened_table.label
    assert label is not None
    assert label.topmargin == 2500
    assert label.leftmargin == 900
    assert label.boxwidth == 18000
    assert label.boxlength == 7500
    assert label.boxmarginhor == 450
    assert label.boxmarginver == 0
    assert label.labelcols == 3
    assert label.labelrows == 8
    assert label.landscape == "WIDELY"
    assert label.pagewidth == 59528
    assert label.pageheight == 84188
    reopened.close()


def test_set_label_replaces_an_existing_one() -> None:
    doc = HwpxDocument.new()
    table = doc.sections[0].add_paragraph().add_table(2, 2)
    table.set_label(labelcols=2, labelrows=9)

    table.set_label(labelcols=1, labelrows=2)

    labels = [c for c in table.element if tag_local_name(c.tag) == "label"]
    assert len(labels) == 1
    assert table.label.labelcols == 1
    assert table.label.labelrows == 2


def test_remove_label() -> None:
    doc = HwpxDocument.new()
    table = doc.sections[0].add_paragraph().add_table(2, 2)
    table.set_label(labelcols=2, labelrows=9)

    removed = table.remove_label()

    assert removed is True
    assert table.label is None


def test_remove_label_on_a_table_without_one_returns_false() -> None:
    doc = HwpxDocument.new()
    table = doc.sections[0].add_paragraph().add_table(2, 2)

    assert table.remove_label() is False


def test_set_label_does_not_restrict_values_to_the_two_observed_combinations() -> None:
    """DEV-023: 사설 코퍼스 리버스가 관측한 조합은 딱 2개뿐이지만, 다른
    조합의 실한컴 수용/거부 실증이 없으므로 값 자체를 제한하지 않는다."""

    doc = HwpxDocument.new()
    table = doc.sections[0].add_paragraph().add_table(2, 2)

    label = table.set_label(labelcols=5, labelrows=1, landscape="NARROWLY")

    assert label.labelcols == 5
    assert label.labelrows == 1
    assert label.landscape == "NARROWLY"


@pytest.mark.parametrize(
    "field_name",
    [
        "topmargin", "leftmargin", "boxwidth", "boxlength", "boxmarginhor",
        "boxmarginver", "labelcols", "labelrows", "pagewidth", "pageheight",
    ],
)
def test_label_partial_update_only_sets_the_given_field(field_name: str) -> None:
    doc = HwpxDocument.new()
    table = doc.sections[0].add_paragraph().add_table(2, 2)

    label = table.set_label(**{field_name: 4242})

    assert getattr(label, field_name) == 4242
    other_fields = {
        "topmargin", "leftmargin", "boxwidth", "boxlength", "boxmarginhor",
        "boxmarginver", "labelcols", "labelrows", "pagewidth", "pageheight",
    } - {field_name}
    for other in other_fields:
        assert getattr(label, other) is None
