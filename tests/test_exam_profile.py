from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.exam.profile import FormProfileError, profile_form

FIX = Path(__file__).parent / "fixtures" / "exam"


def test_profile_resolves_required_styles_and_body_region():
    doc = HwpxDocument.open(FIX / "A_form.hwpx")
    profile = profile_form(doc)
    # required roles resolve to real style ids present in the form
    for role in ("normal", "number", "choice1", "choice5"):
        rs = profile.role_styles[role]
        assert rs.style_id is not None and rs.name
    assert profile.admin_box_index == 0
    # measured (scripts/exam_profile_a_form.py / evidence/a-form-body-map.json):
    # question/answer styles span [1..70]; 관리박스 [0] and the trailing 바탕글
    # footer/essay zone [71..100] are preserved, NOT in the body.
    assert profile.body_start == 1
    assert profile.body_end == 70
    assert profile.body_end < len(doc.sections[0].paragraphs) - 1  # footer not in body
    assert profile.replaceable_indices == tuple(range(1, 71))
    assert not profile.ambiguous_indices  # A_form is known/clean in v1


def test_same_styles_resolve_in_a_filled_instance():
    # B_submitted is a filled instance of the same form -> same role styles exist
    doc = HwpxDocument.open(FIX / "B_submitted.hwpx")
    profile = profile_form(doc)
    assert profile.role_styles["number"].name == "문항자동번호넣기"


def test_missing_required_style_fails_loud():
    doc = HwpxDocument.open(FIX / "A_form.hwpx")
    with pytest.raises(FormProfileError):
        profile_form(doc, role_style_names={"number": "존재하지않는스타일"})
