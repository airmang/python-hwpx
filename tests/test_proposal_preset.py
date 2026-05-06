from hwpx.presets import ProposalSpec, create_proposal_document, inspect_proposal_quality


def _spec() -> dict:
    return {
        "title": "AI 융합형 교육실 구축 제안서",
        "subtitle": "학생 맞춤형 디지털 학습 공간 구축",
        "organization": "샘플 고등학교",
        "author": "교육혁신팀",
        "date": "2026-05-06",
        "metadata": {"문서유형": "제안서", "보안등급": "내부 검토"},
        "executive_summary": "AI 융합형 교육실을 구축해 수업, 평가, 기록을 연결합니다.",
        "sections": [
            {"title": "추진 배경 및 문제 정의", "paragraphs": ["디지털 학습 도구 활용 격차를 해소해야 합니다."]},
            {"title": "제안 내용", "bullets": ["AI 실습 존 구성", "교원 연수 운영"]},
            {"title": "구축 및 운영 계획", "paragraphs": ["1학기 설계, 2학기 운영으로 추진합니다."]},
        ],
        "budget_items": [{"item": "기자재", "amount": "5,000,000원", "note": "노트북 및 주변기기"}],
        "expected_outcomes": ["수업 참여도 향상", "학생별 피드백 강화"],
        "closing": "본 제안서를 검토 후 승인 요청드립니다.",
    }


def test_create_proposal_document_uses_public_api_and_validates(tmp_path):
    doc = create_proposal_document(_spec())
    output = tmp_path / "proposal.hwpx"
    doc.save_to_path(output)
    doc.close()

    report = inspect_proposal_quality(output)

    assert output.exists()
    assert report["outline"]["required_sections_present"] is True
    assert report["table_checks"]["has_budget_table"] is True
    assert report["report_version"] == "proposal-quality-v2"
    assert report["sample_match"]["pass"] is True
    assert report["sample_match"]["visual_review_required"] is True
    assert report["sample_match"]["dimensions"]["lean_asset_payload"]["status"] == "pass"
    assert report["sample_match"]["dimensions"]["purposeful_table_readability"]["status"] == "pass"
    assert report["style_token_usage"]["unique_run_style_count"] >= 4
    assert report["rubric_average"] >= 4.0


def test_normalizes_dataclass_spec():
    doc = create_proposal_document(ProposalSpec(title="테스트 제안서", executive_summary="요약"))
    assert any("테스트 제안서" in (paragraph.text or "") for paragraph in doc.paragraphs)
    doc.close()
