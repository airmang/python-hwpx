"""Profile a school form: resolve role->style and classify the body region.

Grounded by the measure-first A_form probe (scripts/exam_profile_a_form.py).
No style-by-name API exists, so we build a name->Style index ourselves."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from hwpx.document import HwpxDocument
from hwpx.oxml import Style

DEFAULT_ROLE_STYLE_NAMES: dict[str, str] = {
    "normal": "바탕글",
    "number": "문항자동번호넣기",
    "choice1": "1행답항",
    "choice2": "2행답항",
    "choice3": "3행답항",
    "choice5": "5행답항",
    "box_guide": "(보기)박스안내용",
    "box": "박스안내용",
}
# Roles that MUST exist for composition (others are optional conveniences).
REQUIRED_ROLES = ("normal", "number", "choice1", "choice5")


class FormProfileError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResolvedStyle:
    name: str
    style_id: str
    para_pr_id: str | None
    char_pr_id: str | None


@dataclass(frozen=True, slots=True)
class FormProfile:
    role_styles: dict[str, ResolvedStyle]
    admin_box_index: int
    body_start: int
    body_end: int
    replaceable_indices: tuple[int, ...]
    structural_indices: tuple[int, ...]
    ambiguous_indices: tuple[int, ...]


def _name_index(doc: HwpxDocument) -> dict[str, Style]:
    index: dict[str, Style] = {}
    for style in doc.styles.values():
        if style.name:
            index.setdefault(style.name, style)
    return index


def profile_form(
    doc: HwpxDocument,
    *,
    role_style_names: Mapping[str, str] | None = None,
) -> FormProfile:
    names = dict(DEFAULT_ROLE_STYLE_NAMES)
    if role_style_names:
        names.update(role_style_names)

    by_name = _name_index(doc)
    role_styles: dict[str, ResolvedStyle] = {}
    for role, style_name in names.items():
        style = by_name.get(style_name)
        if style is None:
            if role in REQUIRED_ROLES:
                raise FormProfileError(
                    f"required role '{role}' style {style_name!r} not found in form"
                )
            continue
        role_styles[role] = ResolvedStyle(
            name=style_name,
            style_id=str(style.id if style.id is not None else style.raw_id),
            para_pr_id=None if style.para_pr_id_ref is None else str(style.para_pr_id_ref),
            char_pr_id=None if style.char_pr_id_ref is None else str(style.char_pr_id_ref),
        )

    # Anchor the body region on the QUESTION/ANSWER styles ONLY. 바탕글(normal)
    # also clothes the 관리박스 [0] and the trailing footer/essay zone, so it
    # cannot delimit the body (measured: A_form [0] and [71..100] are all 바탕글;
    # the question/answer slots span [1..70], footer marker sits at [99]).
    anchor_names = {rs.name for role, rs in role_styles.items() if role != "normal"}
    section = doc.sections[0]
    paragraphs = section.paragraphs

    anchors: list[int] = []
    for idx, para in enumerate(paragraphs):
        if idx == 0:  # 관리박스 (never replaceable)
            continue
        sid = para.style_id_ref
        style = doc.style(sid) if sid is not None else None
        if style is not None and style.name in anchor_names:
            anchors.append(idx)

    if not anchors:
        raise FormProfileError("no question/answer-style body paragraphs found (form profile failed)")

    body_start, body_end = anchors[0], anchors[-1]
    # The whole [body_start..body_end] span is recomposed from the exam IR
    # (inline 바탕글 lines + 논술형 scaffolding within it included); 관리박스 [0]
    # and the tail [body_end+1..] (footer / essay answer space) are preserved.
    return FormProfile(
        role_styles=role_styles,
        admin_box_index=0,
        body_start=body_start,
        body_end=body_end,
        replaceable_indices=tuple(range(body_start, body_end + 1)),
        structural_indices=(),
        ambiguous_indices=(),  # v1: the body span is recomposed wholesale from the IR
    )
