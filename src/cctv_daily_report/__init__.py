"""CCTV AI 탐지 일일 보고서 자동 생성 모듈.

feature_docs.md에 명시된 파이프라인 구현:
  mock 이벤트 데이터 -> 통계 집계 -> 주요 이벤트 선정 -> VLM 영문 시각 요약 ->
  영문 LLM 요약 -> 한국어 번역 -> report_template.hwpx 렌더링 -> .hwpx 파일 저장.
"""

from .pipeline import run_report

__all__ = ["run_report"]
