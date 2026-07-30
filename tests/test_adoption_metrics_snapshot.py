# SPDX-License-Identifier: Apache-2.0
"""채택 지표 스냅샷 스크립트의 순수 로직 계약(네트워크 없이)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "snapshot_adoption_metrics.py"
HISTORY = ROOT / "docs" / "_extra" / "adoption-metrics-history.json"


def _module():
    spec = importlib.util.spec_from_file_location(
        "snapshot_adoption_metrics", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sample_snapshot(module, as_of: str) -> dict:
    return module.build_snapshot(
        as_of=as_of,
        downloads={"last_month": 10, "last_week": 3},
        repo_info={
            "stargazers_count": 1,
            "forks_count": 2,
            "open_issues_count": 0,
        },
        contributors=[{"login": "airmang"}, {"login": "someone"}],
        first_response={
            "externalIssuesTotal": 0,
            "respondedCount": 0,
            "unansweredOpenCount": 0,
            "medianHours": None,
            "worstHours": None,
            "note": "외부 작성 이슈가 없어 값이 비어 있다",
        },
    )


def test_snapshot_schema_is_stable_and_honest() -> None:
    module = _module()
    snapshot = _sample_snapshot(module, "2026-01-01")
    assert set(snapshot) == {
        "asOf",
        "pypiDownloads",
        "github",
        "externalContributors",
        "issueFirstResponse",
    }
    # 표본 없음은 0·평균으로 눙치지 않고 null과 사유로 남는다.
    assert snapshot["issueFirstResponse"]["medianHours"] is None
    assert snapshot["issueFirstResponse"]["note"]
    # 캐비앗 문자열이 값 옆에 산다.
    assert snapshot["pypiDownloads"]["caveat"]
    assert snapshot["github"]["caveat"]
    assert snapshot["externalContributors"]["count"] == 1


def test_history_merge_is_idempotent_and_sorted() -> None:
    module = _module()
    first = _sample_snapshot(module, "2026-01-02")
    second = _sample_snapshot(module, "2026-01-01")
    merged = module.merge_history([first], second)
    assert [entry["asOf"] for entry in merged] == ["2026-01-01", "2026-01-02"]
    # 같은 날짜 재실행은 교체된다.
    replaced = module.merge_history(merged, _sample_snapshot(module, "2026-01-02"))
    assert [entry["asOf"] for entry in replaced] == ["2026-01-01", "2026-01-02"]
    assert len(replaced) == 2


def test_checked_in_history_matches_schema() -> None:
    module = _module()
    document = json.loads(HISTORY.read_text(encoding="utf-8"))
    assert document["schemaVersion"] == module.SCHEMA_VERSION
    assert document["package"] == "python-hwpx"
    assert document["snapshots"], "history must carry at least one snapshot"
    for snapshot in document["snapshots"]:
        assert set(snapshot) == {
            "asOf",
            "pypiDownloads",
            "github",
            "externalContributors",
            "issueFirstResponse",
        }
