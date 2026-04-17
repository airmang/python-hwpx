# HWPX Stack Shared Workspace

이 디렉토리는 `python-hwpx`, `hwpx-mcp-server`, `hwpx-skill`을 하나의 스택으로 운영할 때 쓰는 공통 기준점이다.

포함 내용:
- fixture 기준선과 manifest
- stack smoke/validation 스크립트
- 호환성/운영 계획 문서
- 벤치마크 메모와 작업 백로그

주요 진입점:
- `shared/hwpx/HWPX_STACK_MASTER_TASK.md`
- `shared/hwpx/scripts/run_stack_smoke_test.sh`
- `shared/hwpx/fixtures/README.md`
- `shared/hwpx/HWPX_STACK_OPERATING_PLAN.md`
- `shared/hwpx/HWPX_STACK_VALIDATION_2026-04-16.md`

Discord에서 확인할 때는 스레드에 아래처럼 물으면 된다.
- `상태`
- `다음`
- `완료`
- `검증`
- `변경`
- `요약`

추천:
- 스레드에는 **핀 고정 상태 메시지 1개**를 유지한다.
- 자세한 기준선은 `HWPX_STACK_MASTER_TASK.md`, Discord에는 짧은 상태판만 둔다.

참고:
- 이 폴더는 현재 `python-hwpx` 저장소 안에 두지만, 내용 자체는 스택 전체를 위한 공통 자산이다.
- sibling repo 기준 경로는 보통 `../hwpx-mcp-server`, `../hwpx-skill`를 가정한다.
