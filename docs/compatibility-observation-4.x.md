# 4.x 호환 표면 관찰 정책

`python-hwpx` 4.x의 기존 import, CLI, 스키마/리포트 버전, 워크플로 래퍼는
계속 동작한다. 런타임의 정본이 MCP 서버로 이동했더라도 4.x에서 공개 호환
표면을 제거하지 않는다.

이 문서는 2026-07-24에 시작한 공개 관찰의 기준이다. 관찰은
2026-10-31(Asia/Seoul)까지, 최소 90일 동안 진행한다. 의견과 실제 사용 사례는
[호환 표면 관찰 이슈](https://github.com/airmang/python-hwpx/issues/68)에 남길
수 있다.

## 현재 결정

- 관찰 시작 시점의 제거 권고는 **0건**이다.
- 아래 8개 family, 3개 CLI를 모두 **extend**한다.
- deprecated 표시는 새 코드가 canonical 경로를 선택하도록 돕는 안내이며,
  이 관찰 자체가 제거 승인은 아니다.
- 4.x에서는 보안 또는 정확성 수정만 양쪽 런타임에 parity test와 영수증을
  동반해 mirror한다. 신규 application workflow는 MCP 정본에 둔다.
- 어떤 제거도 관찰 종료 뒤 별도로 승인된 core major에서만 검토한다.

`extend`는 “계속 사용을 권장한다”는 뜻이 아니라 “호환을 유지하며 실제 사용을
더 관찰한다”는 뜻이다. 새 코드는 아래 canonical 경로를 우선한다.

## 전체 family 판정

`qualified import` 수는 공개 모듈별 재내보내기까지 센 호환 projection 수다.
중복 없는 기능 수나 사용량으로 해석하면 안 된다.

| 4.x 호환 family | qualified import | 새 코드의 canonical 경로 | 판정 |
|---|---:|---|---|
| agent runtime | 219 | MCP agent-document/mixed-form 도구; 재사용 가능한 OXML·mutation은 core | extend |
| authoring runtime | 79 | MCP authoring/generation/layout/style 도구; 재사용 가능한 object model은 core | extend |
| compliance/quality/utilities | 20 | MCP official-document, PII, page-quality, table-utility 도구 | extend |
| form-fill runtime | 103 | `analyze_form_fill` → `apply_form_fill` → `verify_form_fill` | extend |
| eval-plan runtime | 14 | MCP `apply_evalplan_fill(phase="clean")` + J1~J6 skill workflow | extend |
| exam runtime | 20 | MCP `compose_exam` + exam skill workflow | extend |
| visual application runtime | 30 | MCP rendering/oracle/worker/page-QA runtime | extend |
| document-operations wrappers | 3 | MCP comparison, PII-aware mail merge, canonical-render redline verification | extend |

core에 남는 재사용 가능한 구조·알고리즘 계약은 계속 core API다. MCP가 정본인
것은 workspace policy, orchestration, client ToolSpec, 렌더 worker 같은
application runtime이다.

## CLI와 스키마/리포트

다음 console entry point도 4.x에서 유지한다.

| 명령 | entry point | 새 자동화의 우선 경로 | 판정 |
|---|---|---|---|
| `hwpx` | `hwpx.agent.cli:main` | MCP agent-document 도구 | extend |
| `hwpx-analyze-template` | `hwpx.tools.template_analyzer:main` | MCP authoring/template 분석 도구 | extend |
| `hwpx-page-guard` | `hwpx.tools.page_guard:main` | MCP page-quality 도구 | extend |

공개 스키마와 리포트 버전 문자열도 4.x에서 유지한다. 관찰 기준에는 모듈별
재내보내기를 포함한 46개 projection이 있으며, 기존 버전의 required 필드를
바꾸지 않는다. additive 확장은 Optional 필드로만 하고, 파괴 변경은 새 스키마
버전과 별도 major 승인이 필요하다.

## 알려진 독립 사용

공개 코드 검색에서 core를 MCP 없이 직접 쓰는 사용을 확인했다. 예를 들어
`hwpx.builder`로 Markdown을 HWPX로 만드는 경로, `hwpx.tools.template_analyzer`
직접 호출, official lint, template/mail-merge, 두 CLI를 번들에서 호출하는
사용이 있다. 따라서 “검색 결과가 적다” 또는 “MCP에 정본이 있다”만으로
zero-use를 주장하지 않는다.

## 이행과 rollback

기존 import나 CLI는 즉시 바꿀 필요가 없다. 신규 코드는 위 표의 canonical 경로를
쓰고, 기존 경로는 한 번에 한 family씩 이행한다.

1. 현재 입력과 결과 리포트를 fixture로 고정한다.
2. canonical MCP 경로를 side-by-side로 실행해 의미 결과와 오류 계약을 비교한다.
3. parity와 설치 환경 검증이 통과한 뒤 호출자를 전환한다.
4. 문제가 있으면 호출자를 4.x 호환 경로로 되돌린다. 패키지나 스키마를
   downgrade할 필요는 없다.

호환 경로의 보안·정확성 결함은 관찰 이슈에 재현 입력, 사용한 import/CLI,
기대 결과를 함께 남긴다. 관찰 기간에도 해당 수정은 허용하지만, 기능 확장은
canonical MCP owner에 먼저 구현한다.

## 관찰 종료 뒤

2026-10-31이 지나도 자동으로 제거되지 않는다. 종료 census는 family·qualified
import·CLI·스키마/리포트·워크플로별로 keep/remove/extend 근거를 다시 만들고,
사용자 피드백과 clean-install parity/rollback 증거를 포함해야 한다. 실제 제거는
그 자료를 검토해 별도로 승인한 다음 core major에서만 가능하다.
