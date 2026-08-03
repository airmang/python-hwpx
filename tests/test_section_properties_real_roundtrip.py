# SPDX-License-Identifier: Apache-2.0
"""새 secPr/스타일 편집 API의 무인자(no-op) 호출이 실한컴 저장본을 훼손하지
않는지 확인한다(pageBorderFill·footNotePr·endNotePr·hh:style — 062-엔진
표면 전진 이후 재배정 게이트 ②).

부분 갱신 계약의 신뢰는 합성 문서 테스트(``test_document_formatting.py``)
만으로는 못 얻는다 — 실문서의 낯선 속성 조합·중첩 깊이에서도 "인자를 안 준
자리는 안 건드린다"가 성립해야 진짜 안전하다. 그래서 여기서는 실한컴이
저장한 코퍼스 파일을 열고, 새 setter를 인자 없이 호출한 뒤, 저장본을 구조
비교한다 — 바이트가 달라도 되지만(zip 컨테이너 프레이밍) **구조적으로는
빈틈없이 동일**해야 한다.

비교 로직은 ``scripts/roundtrip_fidelity.py``(왕복 충실도 하니스, 이미
검증됨)를 그대로 재사용한다 — 같은 문제를 두 번 다르게 풀지 않는다.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx.document import HwpxDocument
from roundtrip_fidelity import _COSMETIC_CATEGORIES, diff_elements  # scripts/는 pytest pythonpath에 있다

FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: 실한컴 코퍼스 표본 — roundtrip_fidelity의 included 목록에서 출처를 다양화해 골랐다
#: (전부 pageBorderFill·footNotePr·endNotePr·hh:style을 갖는 걸 사전 확인함).
SAMPLE_FILES = [
    "hwpxlib_corpus/error__20230413__test.hwpx",
    "hwpxlib_corpus/reader_writer__sample1.hwpx",
    "m2_corpus/form_002.hwpx",
    "m3_gongmun_gold/seoul_sihaengmun.hwpx",
    "m7_toc_gold/hancom-native-toc-A.hwpx",
    "exam/A_form.hwpx",
    "equation_preview/equation_p0.hwpx",
    "m105_evalplan/blank_form_1-2hak.hwpx",
]


def _assert_structurally_identical(original: bytes, resaved: bytes, *, label: str) -> None:
    with zipfile.ZipFile(io.BytesIO(original)) as za, zipfile.ZipFile(io.BytesIO(resaved)) as zb:
        names_a, names_b = set(za.namelist()), set(zb.namelist())
        assert names_a == names_b, f"{label}: zip 멤버 집합이 달라짐 {names_a ^ names_b}"
        for name in sorted(names_a):
            content_a, content_b = za.read(name), zb.read(name)
            if content_a == content_b:
                continue
            if not name.endswith((".xml", ".hpf")):
                pytest.fail(f"{label}/{name}: 비-XML 멤버가 바이트 단위로 달라짐(무인자 호출인데)")
            tree_a, tree_b = etree.fromstring(content_a), etree.fromstring(content_b)
            diffs = diff_elements(tree_a, tree_b)
            structural = [d for d in diffs if d.category not in _COSMETIC_CATEGORIES]
            assert not structural, (
                f"{label}/{name}: 무인자 호출인데 구조 변화 발생 — "
                + "; ".join(f"{d.path} :: {d.detail}" for d in structural[:10])
            )


@pytest.mark.parametrize("rel_path", SAMPLE_FILES)
def test_noop_setters_do_not_perturb_real_documents(rel_path: str) -> None:
    path = FIXTURES / rel_path
    original = path.read_bytes()

    doc = HwpxDocument.open(path)
    properties = doc.sections[0].properties
    header = doc.oxml.headers[0]

    for page_type in ("BOTH", "EVEN", "ODD"):
        properties.set_page_border_fill(page_type=page_type)
    properties.set_footnote_auto_num_format()
    properties.set_footnote_note_line()
    properties.set_footnote_note_spacing()
    properties.set_footnote_numbering()
    properties.set_footnote_placement()
    properties.set_endnote_auto_num_format()
    properties.set_endnote_note_line()
    properties.set_endnote_note_spacing()
    properties.set_endnote_numbering()
    properties.set_endnote_placement()

    # ensure_style은 "인자 없음"이 성립하지 않는다(name은 필수 식별자) —
    # 대신 "이미 있는 이름으로, 다른 값은 하나도 안 준" 호출이 그 동형이다:
    # 기존 스타일 중 하나를 골라 이름만으로 다시 부르면 그 항목은 완전 무변경이어야 한다.
    styles_before = list(header.styles.values())
    assert styles_before, f"{rel_path}: 스타일이 하나도 없어 게이트가 무의미함"
    target_name = styles_before[0].name
    reused_id = header.ensure_style(target_name)
    assert reused_id == str(styles_before[0].id)

    assert doc.sections[0].dirty is False, f"{rel_path}: secPr 무인자 호출인데 dirty가 섬"
    assert header.dirty is False, f"{rel_path}: ensure_style 재호출(무변경)인데 header dirty가 섬"

    resaved = doc.to_bytes()
    doc.close()

    _assert_structurally_identical(original, resaved, label=rel_path)
