# HWPX Stack Master Task

이 문서는 `python-hwpx`, `hwpx-mcp-server`, `hwpx-skill`을 하나의 작업으로 볼 때 쓰는 **단일 진행판**이다.

원칙:
- 세부 아이디어는 backlog/action map에 둔다.
- 현재 상태, 어디까지 했는지, 다음 한 묶음은 여기서 본다.
- 퍼센트 대신 **상태 / 현재 단계 / 완료 묶음 / 다음 묶음 / blocker**를 기록한다.

## 1. 작업 식별자

- 작업명: `HWPX Stack Stabilization`
- 범위: `python-hwpx` + `hwpx-mcp-server` + `hwpx-skill`
- 소유 스레드: Discord `#hwpx`
- 단일 기준 문서: `shared/hwpx/HWPX_STACK_MASTER_TASK.md`

## 2. 현재 상태

- 전체 상태: `running`
- 현재 단계: `문서/벤치마크/Discord 진행판 배치 마감 완료, 다음 실행 묶음 선정 준비`
- 마지막 확인 시각: `2026-04-17 15:50 Asia/Seoul`
- blocker: 없음

## 3. 이번 작업의 목표

1. HWPX 스택을 하나의 제품처럼 추적 가능하게 만든다.
2. fixture / smoke / compatibility / docs / skill / MCP 흐름을 같은 기준선 위에 올린다.
3. 각 배치가 끝날 때 "어디까지 됐는지"를 한 문서에서 바로 보이게 만든다.

## 4. 이미 끝난 묶음

### A. 스택 기준선 정리
- 세 레포를 하나의 HWPX 스택으로 묶어 운영 기준 수립
- 공통 문서 루트와 smoke 경로 정리
- editor-authored fixture baseline 정리
- canonical vs supplemental fixture 정책 고정

근거:
- `shared/hwpx/HWPX_STACK_OPERATING_PLAN.md`
- `shared/hwpx/HWPX_STACK_VALIDATION_2026-04-16.md`
- `shared/hwpx/fixtures/README.md`

### B. 자동 검증 루프 복구
- stack smoke 재실행 경로 정리
- fixture matrix 통과
- MCP focused tests 통과
- skill extract/replace smoke 통과

근거:
- `shared/hwpx/scripts/run_stack_smoke_test.sh`
- `shared/hwpx/HWPX_STACK_VALIDATION_2026-04-16.md`

### C. 벤치마크 1차
- `python-docx`
- `modelcontextprotocol/servers`
- `Open XML SDK`
- `VS Code Agent Skills`

산출물:
- `shared/hwpx/benchmarks/python-docx.md`
- `shared/hwpx/benchmarks/modelcontextprotocol-servers.md`
- `shared/hwpx/benchmarks/open-xml-sdk.md`
- `shared/hwpx/benchmarks/vscode-agent-skills.md`
- `shared/hwpx/HWPX_STACK_ACTION_MAP.md`

### D. 벤치마크 2차
- `docx4j`
- `pyhwp`

산출물:
- `shared/hwpx/benchmarks/docx4j.md`
- `shared/hwpx/benchmarks/pyhwp.md`

### E. 문서 UX 정리 1차
- `python-hwpx/README.md` 상단을 첫 성공 경로 중심으로 재배치
- `docs/index.md`를 작업 단위 진입점 중심으로 재정리
- `docs/quickstart.md`를 경로 기반 예제로 단순화
- Sphinx 검증용 `.venv-docs` 준비 및 dummy build 통과

검증 명령:
- `.venv-docs/bin/python -m sphinx -b dummy docs docs/_build/dummy`

### F. 벤치마크/진행판 배치 마감
- `docx4j`, `pyhwp` 벤치마크 메모 추가
- `HWPX_STACK_ACTION_MAP.md`, backlog, benchmark candidates 갱신
- `HWPX_STACK_MASTER_TASK.md`를 단일 진행판으로 정리
- Discord 스레드에 핀 고정 상태 메시지 1개를 만들고 조회 규칙을 정착
- `usage.md`는 다음 문서 정리 배치로 분리 결정

## 5. 지금 진행 중인 묶음

### G. 다음 실행 묶음 선정 및 문서 보강 우선순위 조정

현재 상태:
- 문서 UX 1차, 벤치마크 2차, Discord 진행판 도입 배치는 커밋 가능한 단위로 정리됐다.
- `python-hwpx`는 이 배치를 clean baseline으로 닫고, 다음 실행 대상은 `hwpx-mcp-server` 문서 구획 강화와 추가 벤치마크 후보다.

현재 초점:
- `hwpx-mcp-server`의 inspect vs mutate 문서 구획 강화
- 다음 벤치마크 후보를 `pyhwpx` 또는 filesystem / git 계열 MCP server로 좁히기
- `docs/usage.md`는 다음 문서 정리 배치에서 별도로 다루기

## 6. 다음 한 묶음

1. `hwpx-mcp-server` 문서를 inspect vs mutate 흐름 기준으로 더 분리한다.
2. 다음 후보 벤치마크를 `pyhwpx` 또는 filesystem / git 계열 MCP server 중에서 하나로 좁힌다.
3. `python-hwpx/docs/usage.md`는 다음 문서 정리 배치에서 별도로 다룬다.

## 7. 결정/대기 사항

이번에 확정된 결정:
- `usage.md`는 이번 배치에 억지로 넣지 않고, 다음 문서 정리 배치로 분리한다.
- Discord 조회 방식은 **핀 고정 상태 메시지 1개 + 같은 메시지 edit 갱신**으로 정착한다.

현재 대기:
- 다음 벤치마크 후보를 `pyhwpx`와 filesystem / git 계열 MCP server 중 어디부터 볼지 결정

## 8. 레포별 상태

### python-hwpx
- 상태: `stable`
- 현재 초점: 이번 문서 UX 배치는 정리 완료, 다음 `usage.md` 정리 배치 전까지 기준선 유지

### hwpx-mcp-server
- 상태: `next_up`
- 현재 초점: inspect vs mutate 문서 구획 강화 준비

### hwpx-skill
- 상태: `stable`
- 현재 초점: 다음 트리거/검증 루프 정리 전까지 기준선 유지

## 9. Discord에서 확인하는 법

이 스레드에서는 아래 짧은 질의로 상태를 확인한다.

- `상태` 또는 `hwpx 상태`
  - 전체 상태
  - 현재 단계
  - 지금 진행 중인 묶음
  - blocker
- `다음`
  - 다음 한 묶음
  - 결정 필요 사항
- `완료`
  - 최근 끝난 묶음
- `검증`
  - 최신 smoke / docs / test 상태
- `변경`
  - 현재 워킹트리에 남은 변경 파일과 레포 상태
- `요약`
  - 상태 + 완료 + 진행 중 + 다음 + blocker를 한 번에

응답 기준:
- 이 문서를 1차 기준선으로 본다.
- 필요하면 각 레포 `git status`와 최신 validation 문서를 같이 확인한다.
- 배치가 끝나면 먼저 이 문서를 갱신한 뒤, Discord 응답도 같은 구조로 준다.

## 10. 핀 고정 상태 메시지 포맷

Discord에서는 이 문서를 그대로 보여주지 말고, 아래 **짧은 상태판** 하나를 스레드에 고정해 두는 편이 낫다.

권장 포맷:

```text
HWPX Stack Status
- 상태: running
- 현재 단계: 문서/벤치마크/Discord 진행판 배치 마감
- 최근 완료: README/quickstart/index 정리, docx4j·pyhwp 벤치마크 추가, 핀 상태판 적용
- 다음 묶음: hwpx-mcp-server 문서 구획 강화, 다음 벤치마크 후보 확정
- blocker: 없음
- 검증: stack smoke ✅ / docs dummy ✅
- 변경: python-hwpx clean, hwpx-mcp-server clean, hwpx-skill clean
- 마지막 갱신: 2026-04-17 15:50 Asia/Seoul
```

운영 방식:
- 스레드에 상태 메시지는 **항상 1개만** 둔다.
- 새 메시지를 계속 쌓지 말고, 가능하면 **같은 메시지를 수정**한다.
- 자세한 내용은 이 문서에서 보고, Discord에는 요약만 남긴다.
- 배치가 끝날 때마다 이 문서와 고정 메시지를 같이 갱신한다.

## 11. 운영 규칙

이 문서는 매 배치 끝에 아래만 갱신한다.

1. `현재 단계`
2. `이미 끝난 묶음`
3. `지금 진행 중인 묶음`
4. `다음 한 묶음`
5. `결정/대기 사항`

세부 설계 변경은 아래로 보낸다.
- 아이디어/후보: `HWPX_STACK_BACKLOG.md`
- 레포별 실행 항목: `HWPX_STACK_ACTION_MAP.md`
- 장기 기준: `HWPX_STACK_OPERATING_PLAN.md`
- 검증 스냅샷: `HWPX_STACK_VALIDATION_*.md`

한 줄 원칙:

**무슨 일을 할지보다, 지금 어디까지 왔고 다음 한 방이 뭔지 바로 보이게 만든다.**
