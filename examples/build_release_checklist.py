#!/usr/bin/env python
# SPDX-License-Identifier: Apache-2.0
"""Generate an HWPX document exercising memo and style-editing features."""

from __future__ import annotations

from pathlib import Path

from hwpx.document import HwpxDocument

HPX_SOURCE = Path(__file__).with_name("FormattingShowcase.hwpx")
OUTPUT_PATH = Path(__file__).with_name("ReleaseChecklist.hwpx")


def build_checklist(document: HwpxDocument) -> None:
    """Populate the document with paragraphs, memos, and style edits."""

    # Two memo shapes and two run styles. ``ensure_*`` reuses a definition
    # that already exists and returns its id either way.
    blue_memo = document.styles.ensure_memo_shape(
        width=14000,
        line_width="0.6mm",
        line_type="SOLID",
        line_color="#4F81BD",
        fill_color="#EEF4FB",
        active_color="#DDE8F7",
    )
    red_memo = document.styles.ensure_memo_shape(
        width=16000,
        line_width="0.6mm",
        line_type="DOT",
        line_color="#C0504D",
        fill_color="#FDE9E9",
        active_color="#F6D8D8",
    )
    todo_style = document.styles.ensure_run(color="#C00000")
    signoff_style = document.styles.ensure_run(
        underline=True, underline_color="#1F4E79", color="#1F4E79"
    )

    document.add_paragraph("릴리스 최종 점검")
    document.add_paragraph("메모와 스타일 편집 기능이 적용된 QA 확인용 문서입니다.")
    todo = document.add_paragraph("TODO: 통합 테스트 결과 정리", char_pr_id_ref=todo_style)
    signoff = document.add_paragraph(
        "Draft: 문서 배포 전 QA 서명을 수집하세요.", char_pr_id_ref=signoff_style
    )

    document.notes.add_memo(
        "데이터 차트 수치를 2024년 4분기 기준으로 갱신하세요.",
        anchor=todo,
        memo_shape_id_ref=blue_memo,
        memo_id="release-memo-1",
        attributes={"author": "PM"},
        created="2024-12-02 09:00:00",
        number=1,
    )
    document.notes.add_memo(
        "QA 서명은 12월 15일까지 완료되어야 합니다.",
        anchor=signoff,
        memo_shape_id_ref=red_memo,
        memo_id="release-memo-2",
        attributes={"author": "QA Lead"},
        created="2024-12-02 09:30:00",
        number=2,
    )

    # Style-aware replacements: only runs with the given formatting change.
    document.text.replace("TODO", "DONE", text_color="#C00000")
    document.text.replace("Draft: ", "", underline_type="BOTTOM")


def main(output_path: Path = OUTPUT_PATH) -> Path:
    with HwpxDocument.open(HPX_SOURCE) as document:
        build_checklist(document)
        document.save_to_path(output_path)
    print(f"Generated {output_path}")
    return output_path


if __name__ == "__main__":
    main()
