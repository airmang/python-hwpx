from __future__ import annotations

from hwpx import (
    diff_paragraphs,
    doc_diff,
)


def test_diff_paragraphs_classifies_equal_added_removed_changed() -> None:
    changes = diff_paragraphs(
        ["제1조 목적", "제2조 예산", "제3조 시행"],
        ["제1조 목적", "제2조 예산 변경", "제2조의2 추가", "제3조 시행"],
    )

    assert [change["tag"] for change in changes] == ["equal", "changed", "added", "equal"]
    assert changes[1]["old_text"] == "제2조 예산"
    assert changes[1]["new_text"] == "제2조 예산 변경"


def test_diff_paragraphs_handles_removal_boundary() -> None:
    changes = diff_paragraphs(["A", "B", "C"], ["A", "C"])

    assert [change["tag"] for change in changes] == ["equal", "removed", "equal"]
    assert changes[1]["old_index"] == 1
    assert changes[1]["new_index"] is None


def test_doc_diff_accepts_text_sources() -> None:
    report = doc_diff("A\nB\nC", "A\nB2\nC")

    assert report["report_version"] == "doc-diff-v1"
    assert report["summary"]["counts"] == {
        "equal": 2,
        "added": 0,
        "removed": 0,
        "changed": 1,
    }
