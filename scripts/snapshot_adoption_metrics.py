# SPDX-License-Identifier: Apache-2.0
"""채택·응답 지표 스냅샷을 수집해 기계 판독 history에 기록한다.

측정 원칙: 수집 방법을 값 옆에 명시하고, 표본이 없으면 null과 사유를
기록한다(추정 금지). 같은 날 다시 실행하면 그날 항목을 교체한다(멱등).

수집 지표와 한계:
- PyPI 다운로드(pypistats): CI/미러 트래픽 포함 — 순 사용자 수가 아니다.
- GitHub stars/forks: 관심 신호이지 사용량이 아니다.
- 이슈 첫 응답: 외부 작성 이슈에 대해 소유자의 첫 코멘트(없이 닫혔으면
  닫힌 시각)까지의 시간. 공개 타임라인 기준이며 이메일 등 밖의 응답은
  보이지 않는다.
- 외부 기여자: 커밋 기여자 목록에서 소유자를 제외한 수.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "docs" / "_extra" / "adoption-metrics-history.json"
SCHEMA_VERSION = "python-hwpx.adoption-metrics/v1"
REPO = "airmang/python-hwpx"
OWNER = "airmang"
PACKAGE = "python-hwpx"


def _http_json(url: str) -> object:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def _gh_json(path: str) -> object:
    result = subprocess.run(
        ["gh", "api", path],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def collect_issue_first_response() -> dict[str, object]:
    """외부 작성 이슈의 첫 응답 시간(시간 단위)을 전 구간에서 계산한다."""

    issues: list[dict] = []
    page = 1
    while True:
        batch = _gh_json(
            f"repos/{REPO}/issues?state=all&per_page=100&page={page}"
        )
        assert isinstance(batch, list)
        issues.extend(item for item in batch if "pull_request" not in item)
        if len(batch) < 100:
            break
        page += 1

    external = [
        issue for issue in issues if issue["user"]["login"] != OWNER
    ]
    latencies_hours: list[float] = []
    unanswered = 0
    for issue in external:
        created = _iso(issue["created_at"])
        responded: datetime | None = None
        if issue["comments"]:
            comments = _gh_json(
                f"repos/{REPO}/issues/{issue['number']}/comments?per_page=100"
            )
            assert isinstance(comments, list)
            owner_comments = [
                _iso(comment["created_at"])
                for comment in comments
                if comment["user"]["login"] == OWNER
            ]
            if owner_comments:
                responded = min(owner_comments)
        if responded is None and issue.get("closed_at"):
            responded = _iso(issue["closed_at"])
        if responded is None:
            unanswered += 1
        else:
            latencies_hours.append(
                (responded - created).total_seconds() / 3600
            )

    latencies_hours.sort()
    if latencies_hours:
        median = latencies_hours[len(latencies_hours) // 2]
        worst = latencies_hours[-1]
    else:
        median = None
        worst = None
    return {
        "externalIssuesTotal": len(external),
        "respondedCount": len(latencies_hours),
        "unansweredOpenCount": unanswered,
        "medianHours": round(median, 1) if median is not None else None,
        "worstHours": round(worst, 1) if worst is not None else None,
        "note": (
            "외부 작성 이슈가 없어 값이 비어 있다"
            if not external
            else "소유자 첫 코멘트(없이 닫힌 경우 닫힌 시각) 기준"
        ),
    }


def build_snapshot(
    *,
    as_of: str,
    downloads: dict,
    repo_info: dict,
    contributors: list,
    first_response: dict[str, object],
) -> dict[str, object]:
    return {
        "asOf": as_of,
        "pypiDownloads": {
            "lastMonth": downloads["last_month"],
            "lastWeek": downloads["last_week"],
            "source": "pypistats.org/api/packages/{package}/recent",
            "caveat": "CI/미러 트래픽 포함 — 순 사용자 수가 아니다",
        },
        "github": {
            "stars": repo_info["stargazers_count"],
            "forks": repo_info["forks_count"],
            "openIssues": repo_info["open_issues_count"],
            "caveat": "관심 신호이지 사용량이 아니다",
        },
        "externalContributors": {
            "count": sum(
                1 for person in contributors if person["login"] != OWNER
            ),
            "source": "GitHub commit contributors, owner 제외",
        },
        "issueFirstResponse": first_response,
    }


def merge_history(history: list[dict], snapshot: dict) -> list[dict]:
    """같은 날짜 항목은 교체하고, 날짜순 정렬을 유지한다(멱등)."""

    kept = [entry for entry in history if entry["asOf"] != snapshot["asOf"]]
    kept.append(snapshot)
    kept.sort(key=lambda entry: entry["asOf"])
    return kept


def main() -> int:
    as_of = datetime.now(timezone.utc).date().isoformat()
    downloads = _http_json(
        f"https://pypistats.org/api/packages/{PACKAGE}/recent"
    )["data"]
    repo_info = _gh_json(f"repos/{REPO}")
    contributors = _gh_json(f"repos/{REPO}/contributors?per_page=100")
    first_response = collect_issue_first_response()

    snapshot = build_snapshot(
        as_of=as_of,
        downloads=downloads,
        repo_info=repo_info,
        contributors=contributors,
        first_response=first_response,
    )

    if HISTORY.exists():
        document = json.loads(HISTORY.read_text(encoding="utf-8"))
        assert document["schemaVersion"] == SCHEMA_VERSION
        history = document["snapshots"]
    else:
        history = []
    document = {
        "schemaVersion": SCHEMA_VERSION,
        "package": PACKAGE,
        "repository": REPO,
        "snapshots": merge_history(history, snapshot),
    }
    HISTORY.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[OK] {HISTORY.relative_to(ROOT)} ({len(document['snapshots'])} snapshots)")
    print(json.dumps(snapshot, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
