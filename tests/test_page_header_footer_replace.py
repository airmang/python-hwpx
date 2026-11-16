# SPDX-License-Identifier: Apache-2.0
"""Setting a header or footer on a Hancom-made document replaces the one it has (7.0 fix).

Hancom writes its header and footer controls in a run of their own after the section settings.
``doc.page.set_header``/``set_footer``/``set_page_number`` looked for them only in the settings
run and added a second control beside the first.
"""
from __future__ import annotations

import io
import warnings
from pathlib import Path

import pytest

from hwpx import HwpxDocument

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"


def _controls(doc: HwpxDocument, tag: str) -> list:
    return [ctrl for ctrl in doc.sections[0].element.iter(f"{HP}ctrl") if ctrl.find(f"{HP}{tag}") is not None]


def _reopened(doc: HwpxDocument) -> HwpxDocument:
    buffer = io.BytesIO()
    doc.save(buffer)
    return HwpxDocument.open(buffer.getvalue())


def _texts(ctrl, tag: str) -> str:
    return "".join(node.text or "" for node in ctrl.find(f"{HP}{tag}").iter(f"{HP}t"))


def test_set_header_replaces_the_header_hancom_wrote() -> None:
    doc = HwpxDocument.open(FIXTURES / "header_before_field_saved.hwpx")
    assert len(_controls(doc, "header")) == 1
    doc.page.set_header(text="바뀐 머리말", section=0)
    again = _reopened(doc)
    (ctrl,) = _controls(again, "header")
    assert _texts(ctrl, "header") == "바뀐 머리말"


@pytest.mark.parametrize(
    "fixture",
    ["new_page_number_largest_kept.hwpx", "new_page_number_wrapped.hwpx", "new_page_number_smallest_kept.hwpx"],
)
def test_set_footer_and_set_page_number_replace_the_footer_hancom_wrote(fixture: str) -> None:
    doc = HwpxDocument.open(FIXTURES / fixture)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        doc.page.set_footer(text="바뀐 꼬리말", section=0)
    (ctrl,) = _controls(_reopened(doc), "footer")
    assert _texts(ctrl, "footer") == "바뀐 꼬리말"

    doc = HwpxDocument.open(FIXTURES / fixture)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        doc.page.set_page_number(section=0)
    (ctrl,) = _controls(_reopened(doc), "footer")
    assert ctrl.find(f"{HP}footer").find(f".//{HP}autoNum") is not None


def test_the_replaced_control_stays_where_hancom_put_it() -> None:
    doc = HwpxDocument.open(FIXTURES / "new_page_number_largest_kept.hwpx")
    first = doc.sections[0].element.find(f"{HP}p")
    holder_index = next(
        index for index, run in enumerate(first.findall(f"{HP}run"))
        if run.find(f"{HP}ctrl/{HP}footer") is not None
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        doc.page.set_footer(text="꼬리말", section=0)
    runs = first.findall(f"{HP}run")
    assert runs[holder_index].find(f"{HP}ctrl/{HP}footer") is not None
    assert sum(1 for run in runs if run.find(f"{HP}ctrl/{HP}footer") is not None) == 1


def test_a_header_changed_later_in_the_body_is_left_alone() -> None:
    doc = HwpxDocument.open(FIXTURES / "pages_controls_before_a_table_wider_than_the_line.hwpx")
    doc.page.set_header(text="구역 머리말", section=0)
    controls = _controls(doc, "header")
    assert len(controls) == 2  # the section's own header, and the one that takes over from its page


def test_removing_and_setting_again_still_gives_one() -> None:
    doc = HwpxDocument.open(FIXTURES / "header_before_field_saved.hwpx")
    doc.page.remove_header(section=0)
    assert _controls(doc, "header") == []
    doc.page.set_header(text="새 머리말", section=0)
    assert len(_controls(_reopened(doc), "header")) == 1


def test_footer_text_after_a_page_number_warns_that_the_number_goes() -> None:
    doc = HwpxDocument.new()
    doc.page.set_page_number()
    with pytest.warns(UserWarning, match="쪽 번호"):
        doc.page.set_footer(text="대외비")


def test_a_page_number_after_footer_text_warns_that_the_text_goes() -> None:
    doc = HwpxDocument.new()
    doc.page.set_footer(text="대외비")
    with pytest.warns(UserWarning, match="문구"):
        doc.page.set_page_number()


def test_text_and_number_together_in_content_keep_both_without_a_warning() -> None:
    doc = HwpxDocument.new()
    doc.page.set_page_number()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        doc.page.set_footer(content=[{"align": "CENTER", "children": [
            {"type": "run", "text": "대외비 - "}, {"type": "page_number", "page_number": "page"},
        ]}])
    (ctrl,) = _controls(doc, "footer")
    assert _texts(ctrl, "footer").startswith("대외비 - ")
    assert ctrl.find(f".//{HP}autoNum") is not None


def test_text_over_text_does_not_warn() -> None:
    doc = HwpxDocument.new()
    doc.page.set_footer(text="첫 문구")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        doc.page.set_footer(text="다른 문구")
    (ctrl,) = _controls(doc, "footer")
    assert _texts(ctrl, "footer") == "다른 문구"


def test_page_calls_without_a_section_warn_once_in_a_document_of_several() -> None:
    doc = HwpxDocument.new()
    doc.add_section()
    with pytest.warns(UserWarning, match="마지막 구역") as record:
        doc.page.setup(paper_size="A4")
        doc.page.set_header(text="머리말")
    assert sum("마지막 구역" in str(item.message) for item in record) == 1
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        doc.page.size()  # reading does not warn
        doc.page.setup(paper_size="A4", section=0)


def test_a_single_section_document_does_not_warn() -> None:
    doc = HwpxDocument.new()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        doc.page.setup(paper_size="A4")
        doc.page.set_header(text="머리말")
