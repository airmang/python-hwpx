"""``doc.fields.fill(value, char_pr_id_ref=)`` gives the value a character shape of its own.

Without it the value takes the shape of the run holding the field's begin, as Hancom fills a field.
Hancom itself keeps a value of another shape in a run of its own between the field's begin and end
(``hancom_saved/field_value_shape_saved.hwpx``: begin run 0, value run 7, end run 0); a value sharing a
run with other children is cut into runs that way.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.form_fit import FitPolicy
from hwpx.errors import HwpxValueError

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
SAVED = Path(__file__).parent / "fixtures" / "hancom_saved"


def _runs(paragraph) -> list[tuple[str | None, str]]:
    """(charPrIDRef, what the run holds) for each run of *paragraph*."""

    out = []
    for run in paragraph.element.findall(f"{HP}run"):
        held = []
        for child in run:
            local = child.tag.split("}")[-1]
            if local == "t":
                held.append("".join(child.itertext()))
            elif local == "ctrl":
                held.append("<" + "/".join(c.tag.split("}")[-1] for c in child) + ">")
        out.append((run.get("charPrIDRef"), "".join(held)))
    return out


def _reopen(doc: HwpxDocument) -> HwpxDocument:
    reopened = HwpxDocument.open(doc.to_bytes())
    assert reopened.validate().ok
    return reopened


def test_the_value_in_a_run_of_its_own_takes_the_shape() -> None:
    doc = HwpxDocument.open(SAVED / "form_field_unnamed_before.hwpx")
    black = doc.styles.ensure_run(color="#000000", base_char_pr_id_ref="0")
    result = doc.fields.fill("김철수", name="이름", char_pr_id_ref=black)

    assert result.after == "김철수"
    field = next(f for f in _reopen(doc).fields.all if f.name == "이름")
    value_runs = {t.getparent().get("charPrIDRef") for t in field.text_elements}
    assert value_runs == {black}


def test_a_value_sharing_its_run_is_cut_out_and_the_rest_keeps_its_shape() -> None:
    doc = HwpxDocument.open(SAVED / "form_field_unnamed_after.hwpx")  # "이름: " + begin + value + end in one run
    paragraph = next(f for f in doc.fields.all if f.name == "이름").paragraph
    text_before = paragraph.text
    shaped = doc.styles.ensure_run(bold=True, base_char_pr_id_ref="0")

    doc.fields.fill("홍길순", name="이름", char_pr_id_ref=shaped)

    runs = _runs(paragraph)
    assert ("0", "이름: <fieldBegin>") in runs
    assert (shaped, "홍길순") in runs
    assert all(ref == "0" for ref, held in runs if "fieldEnd" in held)
    assert paragraph.text == text_before.replace("홍길동", "홍길순")
    assert paragraph.element.find(f"{HP}linesegarray") is None
    reopened = _reopen(doc)
    assert next(f for f in reopened.fields.all if f.name == "이름").value == "홍길순"


def test_without_char_pr_id_ref_the_value_takes_the_begin_runs_shape() -> None:
    doc = HwpxDocument.open(SAVED / "form_field_unnamed_before.hwpx")
    doc.fields.fill("김철수", name="이름")
    field = next(f for f in doc.fields.all if f.name == "이름")
    assert {t.getparent().get("charPrIDRef") for t in field.text_elements} == {"0"}


@pytest.mark.parametrize("ref", ["999", "", "abc", True, 1.5])
def test_an_id_the_header_does_not_hold_is_refused_before_filling(ref: object) -> None:
    doc = HwpxDocument.open(SAVED / "form_field_unnamed_before.hwpx")
    before = doc.to_bytes()
    with pytest.raises(HwpxValueError) as caught:
        doc.fields.fill("김철수", name="이름", char_pr_id_ref=ref)  # type: ignore[arg-type]
    assert caught.value.code == "field-char-pr-not-found"
    assert doc.to_bytes() == before


def test_fit_and_char_pr_id_ref_together_are_refused() -> None:
    doc = HwpxDocument.open(SAVED / "form_field_unnamed_before.hwpx")
    with pytest.raises(HwpxValueError) as caught:
        doc.fields.fill("김철수", name="이름", char_pr_id_ref="0", fit=FitPolicy(mode="shrink"), box_width=5000)
    assert caught.value.code == "field-fill-char-shape-conflict"
