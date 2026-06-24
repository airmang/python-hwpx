# SPDX-License-Identifier: Apache-2.0
"""Phase E — template/profile builder tests (plan §2 Phase E).

Exercises the committed profiles (harvested from real Hancom saves) end-to-end:
a DocumentPlan lowers onto the verified skeleton + fragments, the output is
open-safe with styleCoverage == 1.0, production mode forbids any minimal-XML
fallback, and an opt-in Mac-oracle smoke confirms a generated doc renders.
"""
from __future__ import annotations

import io
import os

import pytest

from hwpx.design import (
    Block,
    DocumentPlan,
    Profile,
    ProfileRequiredError,
    available_profiles,
    compose,
    compose_bytes,
    load_profile,
    style_coverage,
)
from hwpx.document import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety

PROFILES = ["official_notice", "report", "application_form"]


def _plan(profile: str) -> dict:
    return {
        "profile": profile,
        "title": "테스트 문서 제목",
        "blocks": [
            {"type": "paragraph", "role": "heading", "text": "첫 번째 항목"},
            {"type": "paragraph", "role": "body", "text": "본문 내용을 한 줄로 작성합니다."},
            {
                "type": "table", "role": "info",
                "columns": ["구분", "내용"],
                "rows": [["가", "값1"], ["나", "값2"]],
            },
        ],
    }


# --------------------------------------------------------------------------- #
# Plan model.
# --------------------------------------------------------------------------- #
def test_document_plan_from_dict_and_title_promotion():
    plan = DocumentPlan.from_dict(_plan("report"))
    assert plan.profile == "report"
    blocks = plan.iter_blocks()
    assert blocks[0].role == "title" and blocks[0].text == "테스트 문서 제목"
    assert any(b.type == "table" for b in blocks)


def test_document_plan_requires_profile():
    with pytest.raises(ValueError):
        DocumentPlan.from_dict({"title": "x"})


# --------------------------------------------------------------------------- #
# Profiles are real Hancom-derived and complete.
# --------------------------------------------------------------------------- #
def test_three_profiles_are_available():
    assert set(PROFILES).issubset(set(available_profiles()))


@pytest.mark.parametrize("pid", PROFILES)
def test_profile_loads_with_fragments_and_open_safe_skeleton(pid):
    prof = load_profile(pid)
    for role in ("title", "heading", "body", "info_table"):
        assert prof.has_role(role), f"{pid} missing {role}"
    # The committed skeleton is itself a genuine, open-safe Hancom package.
    assert validate_editor_open_safety(prof.template_bytes).ok


# --------------------------------------------------------------------------- #
# Compose end-to-end.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("pid", PROFILES)
def test_compose_is_open_safe_full_coverage_and_keeps_content(pid, tmp_path):
    out = tmp_path / f"{pid}.hwpx"
    result = compose(_plan(pid), output_path=out)
    assert result.ok, result.errors
    assert result.style_coverage.coverage == pytest.approx(1.0)
    assert out.exists()

    data = out.read_bytes()
    assert validate_editor_open_safety(data).ok
    doc = HwpxDocument.open(io.BytesIO(data))
    try:
        text = doc.export_text()
        tables = sum(len(getattr(p, "tables", [])) for p in doc.sections[0].paragraphs)
    finally:
        doc.close()
    assert "테스트 문서 제목" in text
    assert "본문 내용을 한 줄로 작성합니다." in text
    assert "값1" in text and "값2" in text
    assert tables == 1


def test_compose_bytes_roundtrips():
    data, result = compose_bytes(_plan("official_notice"))
    assert result.ok and data
    assert validate_editor_open_safety(data).ok


def test_compose_table_fills_cells_not_placeholders():
    data, res = compose_bytes(_plan("application_form"))
    assert res.ok
    assert b"{{cell}}" not in data  # harvested placeholders never ship
    doc = HwpxDocument.open(io.BytesIO(data))
    try:
        table = next(
            t for p in doc.sections[0].paragraphs for t in getattr(p, "tables", [])
        )
        assert table.cell(1, 0).text.strip() == "가"
        assert table.cell(2, 0).text.strip() == "나"
    finally:
        doc.close()


@pytest.mark.parametrize("n_rows,expected", [(1, 2), (4, 5)])
def test_table_row_count_tracks_plan_rows(n_rows, expected):
    # Row counts that DON'T coincide with the fragment's native 3 rows, so a
    # no-op / off-by-one in the row cloning fails the assertion.
    plan = {
        "profile": "application_form", "title": "제목",
        "blocks": [{
            "type": "table", "role": "info", "columns": ["구분", "내용"],
            "rows": [[f"가{i}", f"값{i}"] for i in range(n_rows)],
        }],
    }
    data, res = compose_bytes(plan)
    assert res.ok
    doc = HwpxDocument.open(io.BytesIO(data))
    try:
        table = next(t for p in doc.sections[0].paragraphs for t in getattr(p, "tables", []))
        assert table.row_count == expected
    finally:
        doc.close()


def test_empty_columns_does_not_ship_placeholder():
    # A headerless-table request (columns=[]) must blank the header, not leave
    # the harvested {{cell}} placeholder.
    plan = {
        "profile": "report", "title": "제목",
        "blocks": [{"type": "table", "role": "info", "columns": [], "rows": [["a", "b", "c", "d"]]}],
    }
    data, res = compose_bytes(plan)
    assert res.ok
    assert b"{{cell}}" not in data


def _extra_columns_plan() -> DocumentPlan:
    # application_form info_table is 2-col; ask for 3 (data loss).
    return DocumentPlan(
        profile="application_form", title="제목",
        blocks=[Block(type="table", role="info", columns=["A", "B", "C"], rows=[["1", "2", "3"]])],
    )


def test_production_raises_on_column_data_loss(tmp_path):
    with pytest.raises(ProfileRequiredError):
        compose(_extra_columns_plan(), production=True, output_path=tmp_path / "x.hwpx")


def test_debug_warns_on_column_data_loss(tmp_path):
    res = compose(_extra_columns_plan(), production=False, output_path=tmp_path / "x.hwpx")
    assert res.ok
    assert any("COLUMN_MISMATCH" in w for w in res.warnings)


def test_empty_plan_raises_profile_required(tmp_path):
    with pytest.raises(ProfileRequiredError, match="produced no content"):
        compose(DocumentPlan(profile="report", blocks=[]), output_path=tmp_path / "x.hwpx")


def test_compose_returns_not_ok_when_open_safety_raises(tmp_path, monkeypatch):
    def boom(self, *args, **kwargs):
        raise ValueError("Generated HWPX package failed open-safety validation: seeded")

    monkeypatch.setattr(HwpxDocument, "save_report", boom)
    res = compose(_plan("report"), output_path=tmp_path / "x.hwpx")
    assert res.ok is False
    assert any("OPEN_SAFETY" in e for e in res.errors)


# --------------------------------------------------------------------------- #
# Privacy: no residual source PII in committed templates or generated docs.
# --------------------------------------------------------------------------- #
_PII_NEEDLES = [
    "홍옥수", "csteacher", "bluewave", "shkimde", "옥지현", "keris", "kokyu",
    "광교", "매원", "경기도교육청", "학교공간혁신", "상용클라우드",
]


def _text_blob(data: bytes) -> str:
    import zipfile

    z = zipfile.ZipFile(io.BytesIO(data))
    return "".join(
        z.read(n).decode("utf-8", "ignore")
        for n in z.namelist()
        if not n.endswith((".bmp", ".png", ".jpg", ".jpeg"))
    ).lower()


@pytest.mark.parametrize("pid", PROFILES)
def test_profile_and_output_carry_no_source_pii(pid):
    prof = load_profile(pid)
    blob = _text_blob(prof.template_bytes)
    assert not [n for n in _PII_NEEDLES if n in blob], pid
    data, res = compose_bytes(_plan(pid))
    assert res.ok
    out_blob = _text_blob(data)
    assert not [n for n in _PII_NEEDLES if n in out_blob], pid


# --------------------------------------------------------------------------- #
# styleCoverage + production no-fallback.
# --------------------------------------------------------------------------- #
def test_style_coverage_flags_an_undefined_reference():
    from lxml import etree

    prof = load_profile("report")
    doc = HwpxDocument.open(prof.template_bytes)
    try:
        bogus = etree.fromstring(
            '<p xmlns="http://www.hancom.co.kr/hwpml/2011/paragraph" '
            'paraPrIDRef="0"><run charPrIDRef="99999999"><t>x</t></run></p>'
        )
        cov = style_coverage(doc, [bogus])
    finally:
        doc.close()
    assert cov.coverage < 1.0
    assert ("charPr", "99999999") in cov.missing


def _profile_without(role: str) -> Profile:
    base = load_profile("report")
    return Profile(
        id=base.id, root=base.root, manifest=base.manifest,
        template_bytes=base.template_bytes,
        _fragments={k: v for k, v in base._fragments.items() if k != role},
    )


def test_production_mode_forbids_missing_fragment_fallback(tmp_path):
    broken = _profile_without("info_table")
    plan = DocumentPlan(
        profile="report",
        blocks=[
            Block(type="paragraph", role="body", text="본문"),
            Block(type="table", role="info", columns=["a"], rows=[["1"]]),
        ],
    )
    with pytest.raises(ProfileRequiredError):
        compose(plan, profile=broken, production=True, output_path=tmp_path / "x.hwpx")


def test_debug_mode_warns_and_skips_missing_fragment(tmp_path):
    broken = _profile_without("info_table")
    plan = DocumentPlan(
        profile="report",
        blocks=[
            Block(type="paragraph", role="body", text="본문"),
            Block(type="table", role="info", columns=["a"], rows=[["1"]]),
        ],
    )
    result = compose(plan, profile=broken, production=False, output_path=tmp_path / "x.hwpx")
    assert result.ok  # body composed; table skipped with a warning
    assert any("info_table" in w for w in result.warnings)


# --------------------------------------------------------------------------- #
# Opt-in Mac-oracle render smoke (mirrors the visual-oracle gating).
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(
    os.environ.get("HWPX_MAC_ORACLE_SMOKE") != "1",
    reason="set HWPX_MAC_ORACLE_SMOKE=1 on macOS+Hancom to render-verify a composed doc",
)
def test_composed_document_renders_in_hancom(tmp_path):
    from hwpx.visual.oracle import MacHancomOracle

    oracle = MacHancomOracle(timeout=200)
    if not oracle.available():
        pytest.skip("Hancom not reachable")
    out = tmp_path / "official_notice.hwpx"
    compose(_plan("official_notice"), output_path=out)
    pdf = oracle.render_pdf(str(out), str(tmp_path / "out.pdf"))
    assert pdf and os.path.getsize(pdf) > 0
