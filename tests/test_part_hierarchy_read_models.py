# SPDX-License-Identifier: Apache-2.0
"""파트 계층 읽기 모델 — version.xml/masterpage.xml/history.xml (감사 갭 #15).

``settings.xml``(``HwpxOxmlSettings``/``ApplicationSettings``) 관용구를
그대로 따른다: ``_HwpxOxmlSimplePart`` 서브클래스에 ``to_model()``을
붙이고, 실제 파싱 로직은 별도 모듈(``version_part``/``master_page``/
``history_part``)에 둔다.

``version.xml``·``masterpage.xml``은 실코퍼스(``hwpxlib_corpus``) 전량/1건
역설계 — 둘 다 ``DevDoc/OWPML SCHEMA``의 2024 초안 스키마와 루트 이름·
네임스페이스가 어긋난다는 게 실측으로 확인됐다(스키마가 아니라 실코퍼스가
진실 원천). ``history.xml``은 실코퍼스 0건이라 스키마 전용 — 그 사실을
여기서도 테스트로 고정한다(다음에 실 예시가 나오면 이 스위트가 먼저
깨져야 한다).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.oxml.history_part import DiffNode, History, HistoryEntry, parse_history
from hwpx.oxml.master_page import MasterPage, parse_master_page
from hwpx.oxml.version_part import HcfVersion, parse_hcf_version

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "tests" / "fixtures" / "hwpxlib_corpus"

MASTERPAGE_FIXTURE = (
    CORPUS / "error__20250808__2015년_12월_재난안전종합상황_분석_및_전망.hwpx"
)


def _all_corpus_hwpx() -> list[Path]:
    return sorted(CORPUS.glob("*.hwpx"))


# ============================================================================
# version.xml — 실코퍼스 47/47
# ============================================================================


def test_parse_hcf_version_matches_a_real_sample() -> None:
    with zipfile.ZipFile(CORPUS / "error__20231219__test1.hwpx") as archive:
        root = etree.fromstring(archive.read("version.xml"))
    version = parse_hcf_version(root)
    assert version == HcfVersion(
        taget_application="WORDPROCESSOR",
        major=5, minor=1, micro=1, build_number=0, os=10,
        xml_version="1.5", application="Hancom Office Hangul",
        app_version="12.30.0.5491 MAC64LEDarwin_22.6.0",
    )


def test_parse_hcf_version_across_the_whole_vendored_corpus() -> None:
    """47/47 이 예외 없이 파싱돼야 한다 — 필수 8개 속성 실측."""

    files = _all_corpus_hwpx()
    assert len(files) == 47
    for path in files:
        with zipfile.ZipFile(path) as archive:
            root = etree.fromstring(archive.read("version.xml"))
        version = parse_hcf_version(root)
        assert version.taget_application == "WORDPROCESSOR"
        assert version.major is not None
        assert version.minor is not None
        assert version.micro is not None
        assert version.build_number is not None
        assert version.xml_version is not None
        assert version.application is not None
        assert version.app_version is not None
        # os 는 46/47 관측(옵션) — None 이어도 실패시키지 않는다.


def test_parse_hcf_version_preserves_the_taget_application_typo() -> None:
    """실 산출물 속성명은 tagetApplication(오탈자) — 정정하지 않는다."""

    root = etree.fromstring(
        b'<hv:HCFVersion xmlns:hv="http://www.hancom.co.kr/hwpml/2011/version" '
        b'tagetApplication="WORDPROCESSOR" major="5" minor="1" micro="1" '
        b'buildNumber="0" xmlVersion="1.5" application="x" appVersion="y"/>'
    )
    assert parse_hcf_version(root).taget_application == "WORDPROCESSOR"


def test_parse_hcf_version_rejects_wrong_root() -> None:
    root = etree.fromstring(b"<notVersion/>")
    with pytest.raises(HwpxValueError) as excinfo:
        parse_hcf_version(root)
    assert excinfo.value.code == "document-version-root-invalid"


def test_document_parts_version_to_model(tmp_path: Path) -> None:
    doc = HwpxDocument.new()
    version = doc.parts.version
    assert version is not None
    model = version.to_model()
    assert isinstance(model, HcfVersion)
    assert model.taget_application == "WORDPROCESSOR"
    doc.close()


# ============================================================================
# masterpage.xml — 실코퍼스 1파일
# ============================================================================


def test_parse_master_page_matches_the_real_sample() -> None:
    with zipfile.ZipFile(MASTERPAGE_FIXTURE) as archive:
        root = etree.fromstring(archive.read("Contents/masterpage0.xml"))
    master_page = parse_master_page(root)
    assert master_page == MasterPage(
        id="masterpage0", type="OPTIONAL_PAGE", page_number=1,
        page_duplicate=False, page_front=False, paragraph_texts=("",),
    )


def test_master_page_root_has_no_namespace_in_the_real_sample() -> None:
    """스키마는 hm:masterPage를 말하지만, 실 산출물 루트는 네임스페이스가
    없다 — element-census.json의 unnamespacedElements 항목과 일치."""

    with zipfile.ZipFile(MASTERPAGE_FIXTURE) as archive:
        root = etree.fromstring(archive.read("Contents/masterpage0.xml"))
    assert root.tag == "masterPage"
    assert not root.tag.startswith("{")


def test_parse_master_page_rejects_wrong_root() -> None:
    root = etree.fromstring(b"<notMasterPage/>")
    with pytest.raises(HwpxValueError) as excinfo:
        parse_master_page(root)
    assert excinfo.value.code == "document-master-page-root-invalid"


def test_document_parts_master_pages_to_model() -> None:
    doc = HwpxDocument.open(MASTERPAGE_FIXTURE)
    master_pages = doc.parts.master_pages
    assert len(master_pages) == 1
    model = master_pages[0].to_model()
    assert isinstance(model, MasterPage)
    assert model.id == "masterpage0"
    assert model.type == "OPTIONAL_PAGE"
    doc.close()


def test_master_page_round_trips_through_save_and_reopen(tmp_path: Path) -> None:
    doc = HwpxDocument.open(MASTERPAGE_FIXTURE)
    before = doc.parts.master_pages[0].to_model()
    path = tmp_path / "roundtrip.hwpx"
    doc.save_to_path(path)
    doc.close()

    reopened = HwpxDocument.open(path)
    after = reopened.parts.master_pages[0].to_model()
    assert after == before
    reopened.close()


# ============================================================================
# history.xml — 실코퍼스 0건, 스키마 전용(정직 표기 고정)
# ============================================================================


def test_no_corpus_fixture_has_a_history_part() -> None:
    """이 테스트는 명제를 고정한다: 언젠가 실 예시가 이 코퍼스에 들어오면
    여기서 먼저 깨져야 한다 — 그때 History 모델을 실측으로 재검증한다."""

    for path in _all_corpus_hwpx():
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
        assert not any("history" in name.lower() for name in names), path.name


def test_parse_history_handles_a_schema_shaped_synthetic_fixture() -> None:
    """실 예시가 없어 DevDoc/OWPML SCHEMA/Document History XML schema.xml
    그대로 조립한 합성 픽스처로 검증한다 — insert/update/delete/position의
    재귀 중첩과 delete의 mixed-content 텍스트를 포함."""

    xml = b"""<hhs:history
        xmlns:hhs="http://www.hancom.co.kr/hwpml/2011/history" version="1.0">
      <hhs:historyEntry revisionNumber="1"
          revisionDate="2026-08-06 10:00:00.000" revisionAuthor="tester"
          revisionDesc="init" revisionLock="0" autoSave="1">
        <hhs:bodyDiff href="Contents/section0.xml">
          <hhs:update path="/hp:p[1]" oldValue="old">
            <hhs:insert path="/hp:p[1]/hp:run[1]"/>
            <hhs:delete path="/hp:p[1]/hp:run[2]">removed text</hhs:delete>
            <hhs:position path="/hp:p[1]/hp:run[3]"/>
          </hhs:update>
        </hhs:bodyDiff>
      </hhs:historyEntry>
    </hhs:history>"""
    root = etree.fromstring(xml)
    history = parse_history(root)

    assert history == History(
        version="1.0",
        entries=[
            HistoryEntry(
                revision_number=1,
                revision_date="2026-08-06 10:00:00.000",
                revision_author="tester",
                revision_desc="init",
                revision_lock=False,
                auto_save=True,
                package_diff=None,
                head_diff=None,
                body_diffs=[
                    DiffNode(
                        op="update", path="/hp:p[1]", old_value="old", text=None,
                        attributes={},
                        children=[
                            DiffNode(
                                op="insert", path="/hp:p[1]/hp:run[1]",
                                old_value=None, text=None, attributes={},
                            ),
                            DiffNode(
                                op="delete", path="/hp:p[1]/hp:run[2]",
                                old_value=None, text="removed text",
                                attributes={},
                            ),
                            DiffNode(
                                op="position", path="/hp:p[1]/hp:run[3]",
                                old_value=None, text=None, attributes={},
                            ),
                        ],
                    ),
                ],
                tail_diff=None,
            ),
        ],
    )


def test_parse_history_rejects_wrong_root() -> None:
    root = etree.fromstring(b"<notHistory/>")
    with pytest.raises(HwpxValueError) as excinfo:
        parse_history(root)
    assert excinfo.value.code == "document-history-root-invalid"


def test_document_parts_histories_is_empty_for_real_corpus() -> None:
    doc = HwpxDocument.open(MASTERPAGE_FIXTURE)
    assert doc.parts.histories == []
    doc.close()
