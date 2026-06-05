"""python -m cctv_daily_report.cli ..."""

from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import run_report


def main() -> int:
    parser = argparse.ArgumentParser(description="CCTV AI 일일 보고서 HWPX 생성")
    parser.add_argument("--report-date", default=None, help="YYYY-MM-DD (기본: 오늘)")
    parser.add_argument("--output", type=Path, default=None, help="출력 디렉토리")
    parser.add_argument("--skip-vlm", action="store_true", help="VLM 호출 생략 (mock 응답)")
    parser.add_argument("--skip-llm", action="store_true", help="LLM·번역 호출 생략 (rule-based)")
    args = parser.parse_args()

    path = run_report(
        report_date=args.report_date,
        output_dir=args.output,
        skip_vlm=args.skip_vlm,
        skip_llm=args.skip_llm,
    )
    print(f"\nReport generated: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
