"""이벤트 데이터 소스 추상화.

pipeline은 "데이터가 어디서 오는지" 모르고 EventSource.load(report_date)만 호출한다.
실데이터(DB·이벤트 로그) 연동 시 pipeline 수정 없이 새 소스 클래스만 추가하면 된다.
CctvEvent / ReportInfo dataclass가 소스와 pipeline 사이의 계약(contract)이다.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .mock_data import CctvEvent, ReportInfo, build_mock_dataset


@runtime_checkable
class EventSource(Protocol):
    """보고 일자에 대한 (ReportInfo, 이벤트 목록)을 제공하는 소스."""

    def load(self, report_date: str) -> tuple[ReportInfo, list[CctvEvent]]:
        ...


class MockEventSource:
    """하드코딩 mock 데이터 소스 (기본값).

    실제 시스템에서는 DbEventSource 등으로 교체한다.
    """

    def load(self, report_date: str) -> tuple[ReportInfo, list[CctvEvent]]:
        return build_mock_dataset(report_date)
