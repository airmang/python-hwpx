"""채움본 잔존물 zero-체크 — 범용 form-fill goal Stage 3의 기계 게이트.

2026-07-06 평가계획 거짓 수렴(빨간 지시문 ~15곳·타과목 샘플·placeholder 잔존이
스코어 94.9를 통과)의 결함 유형을 **양식 불문 신호**로 검사한다. 도메인 어휘 없음:

- **삭제색 잔존**(ERROR): blank의 범례가 "삭제"로 선언한 색의 런 텍스트가
  produced에 남아 있음(예: 빨간 지시문).
- **미수정 샘플**(ERROR): 범례가 "수정"으로 선언한 색의 blank 런 텍스트가
  produced에 **그대로** 남아 있음 — 코드 없는 prose 샘플(음악 '연주', 한국사
  '전근대사' 등)을 잡는 일반 신호.
- **placeholder 잔존**: ◯◯◯·□□□(2연속 이상)=ERROR. 리터럴 ``**``는 각주
  표식("경비** 집행 불가")과 중의적이라 NEEDS_REVIEW(2026-07-07 신청서 실측).
- **고아 마커**(NEEDS_REVIEW): 텍스트가 목록 마커('-', '•', '가.' 류)뿐인 문단 —
  의도적으로 남긴 하위 항목 자리일 수 있어 사람 판단으로 넘긴다.

이 게이트는 필요조건이다 — 통과해도 "제출 가능" 확언은 렌더 PDF를 사람이 전
페이지 본 뒤에만 한다(철칙).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

from .guidance_scan import scan_form_guidance, _color_family  # noqa: F401 (계열 재사용)
from .document import HwpxDocument
import hwpx.guidance_scan as _gs

__all__ = ["ResidueFinding", "ResidueReport", "inspect_fill_residue"]

_PLACEHOLDER_RES = {
    "circle_blank": re.compile(r"[◯○〇]{2,}"),
    "square_blank": re.compile(r"□{2,}"),
}
# ``**``는 placeholder(**과목)일 수도, 각주 표식(경비**)일 수도 있어 사람 판단으로.
_AMBIGUOUS_RES = {
    "double_star": re.compile(r"\*\*"),
}
_MARKER_ONLY = re.compile(r"^\s*(?:[-•‧∙·]|[가나다라마바사아자차카타파하]\.|\(\d+\)|\d+\))\s*$")
_MIN_SAMPLE_LEN = 4  # 이보다 짧은 수정색 텍스트(숫자·기호 등)는 미수정 판정에서 제외


@dataclass(slots=True)
class ResidueFinding:
    kind: str  # delete_color_residue / unmodified_sample / placeholder / marker_only
    severity: str  # error / needs_review
    location: str
    text_preview: str
    signal: str


@dataclass(slots=True)
class ResidueReport:
    produced: str
    errors: list[ResidueFinding] = field(default_factory=list)
    needs_review: list[ResidueFinding] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        def d(f: ResidueFinding) -> dict:
            return {"kind": f.kind, "severity": f.severity, "location": f.location,
                    "textPreview": f.text_preview, "signal": f.signal}

        return {"ok": self.ok, "errors": [d(f) for f in self.errors],
                "needsReview": [d(f) for f in self.needs_review], "stats": self.stats}


def _scan_paragraphs(source: Union[str, Path, HwpxDocument]):
    doc = source if isinstance(source, HwpxDocument) else HwpxDocument.open(str(source))
    chars = doc._root.char_properties
    out = []
    for s_idx, section in enumerate(doc.sections):
        walker = _gs._Walker(chars)
        for b_idx, p in enumerate(section.paragraphs):
            walker.walk_paragraph(p.element, s_idx, b_idx, None)
        out.extend(walker.out)
    return out


def inspect_fill_residue(
    produced: Union[str, Path],
    blank: Union[str, Path, None] = None,
) -> ResidueReport:
    """채움본(produced)의 잔존물을 검사한다. blank가 있으면 범례 기반 신호까지."""
    report = ResidueReport(produced=str(produced))
    paras = _scan_paragraphs(produced)
    produced_text = "\n".join(p.text for p in paras)

    delete_families: set[str] = set()
    modify_families: set[str] = set()
    blank_delete_texts: list[tuple[str, str]] = []  # (text, 위치 힌트)
    blank_modify_texts: list[tuple[str, str]] = []
    if blank is not None:
        blank_report = scan_form_guidance(blank)
        delete_families = {b.family for b in blank_report.legend if b.action == "delete"}
        modify_families = {b.family for b in blank_report.legend if b.action == "modify"}
        for bp in _scan_paragraphs(blank):
            for _, hex_color, text in bp.spans:
                t = text.strip()
                if not t:
                    continue
                fam = _color_family(hex_color)
                if fam in delete_families:
                    blank_delete_texts.append((t, bp.location()))
                elif fam in modify_families and len(t) >= _MIN_SAMPLE_LEN:
                    blank_modify_texts.append((t, bp.location()))

    # 1) 삭제색 잔존: blank의 삭제색 텍스트가 produced에 남음
    seen: set[str] = set()
    for t, loc in blank_delete_texts:
        if t in seen:
            continue
        seen.add(t)
        if t in produced_text:
            report.errors.append(ResidueFinding(
                "delete_color_residue", "error", loc, t[:80],
                "blank 범례가 '삭제'로 선언한 색의 텍스트가 잔존"))

    # 2) 미수정 샘플: 수정색 텍스트가 blank와 동일하게 잔존
    seen.clear()
    for t, loc in blank_modify_texts:
        if t in seen:
            continue
        seen.add(t)
        if t in produced_text:
            report.errors.append(ResidueFinding(
                "unmodified_sample", "error", loc, t[:80],
                "blank 범례가 '수정'으로 선언한 텍스트가 그대로 잔존(샘플 미교체)"))

    # 3) placeholder 잔존
    for p in paras:
        text = p.text
        if not text.strip():
            continue
        for name, pat in _PLACEHOLDER_RES.items():
            if pat.search(text):
                report.errors.append(ResidueFinding(
                    "placeholder", "error", p.location(), text.strip()[:80],
                    f"placeholder:{name}"))
        for name, pat in _AMBIGUOUS_RES.items():
            if pat.search(text):
                report.needs_review.append(ResidueFinding(
                    "placeholder_ambiguous", "needs_review", p.location(),
                    text.strip()[:80], f"placeholder?:{name} — 각주 표식일 수 있음"))
        if _MARKER_ONLY.match(text):
            report.needs_review.append(ResidueFinding(
                "marker_only", "needs_review", p.location(), text.strip()[:20],
                "목록 마커만 있는 문단 — 의도된 빈 자리인지 사람 판단"))

    report.stats = {
        "paragraphs": len(paras),
        "blankDeleteTexts": len({t for t, _ in blank_delete_texts}),
        "blankModifyTexts": len({t for t, _ in blank_modify_texts}),
        "errors": len(report.errors),
        "needsReview": len(report.needs_review),
    }
    return report
