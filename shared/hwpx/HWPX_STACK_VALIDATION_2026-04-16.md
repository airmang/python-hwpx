# HWPX Stack Validation Report (2026-04-16)

검증 목적:
- release-facing 문서 정리 후, `python-hwpx`, `hwpx-mcp-server`, `hwpx-skill` 3개 레이어를 한 번에 다시 확인한다.
- generated smoke만이 아니라, **editor-authored sanitized fixture baseline**까지 같이 고정한다.

## 1. 실행 경로

메인 스크립트:
- `shared/hwpx/scripts/run_stack_smoke_test.sh`

보조 스크립트:
- `shared/hwpx/scripts/core_stack_smoke.py`
- `shared/hwpx/scripts/fixture_smoke_matrix.py`
- `shared/hwpx/scripts/sanitize_fixture_metadata.py`

fixture 기준점:
- `shared/hwpx/fixtures/README.md`
- `shared/hwpx/fixtures/fixture_matrix.json`

로그:
- `shared/hwpx/tmp/smoke/stack_smoke.log`

## 2. 이번 배치에서 추가한 것

1. NAS의 editor-authored 원본 세트 확인
   - `private://hwpx_smoke`
2. editor-authored `.hwpx` 8개를 shared fixture 트리로 복사
3. `Contents/content.hpf` 기준 metadata scrub 적용
4. fixture matrix(`fixture_matrix.json`) 작성
5. `fixture_smoke_matrix.py`로 expected text/paragraph/table/tag 검증 연결
6. `run_stack_smoke_test.sh`에 editor-authored fixture smoke를 편입

## 3. 수행 내용

이번 스모크 경로는 아래를 순서대로 수행한다.

1. shared venv 준비/동기화
2. `python-hwpx` editable install
3. `hwpx-mcp-server[test]` editable install
4. editor-authored fixture smoke matrix 실행
5. `hwpx-skill` text extract를 `core/00_smoke_min.hwpx`에 대해 실행
6. `python-hwpx`로 새 `.hwpx` 문서 생성, 저장, 재열기 검증
7. `hwpx-mcp-server` focused smoke
   - `tests/test_contract.py`
   - `tests/test_mcp_end_to_end.py`
8. `hwpx-skill` text extract smoke
9. `hwpx-skill` replace + namespace normalize smoke
10. 치환 결과 재검증

## 4. 결과

### Fixture metadata scrub
- imported 8개 모두 scrub 완료
- 정규화 항목:
  - `creator` → `fixture`
  - `lastsaveby` → `fixture`
  - `CreatedDate` / `ModifiedDate` / `date` → 고정 sentinel
- scrub 후 `kokyu` 문자열 잔존 없음 확인

### Editor-authored fixture matrix
- 대상:
  - `00_smoke_min`
  - `10_fieldcodes_min`
  - `20_formcontrols_min`
  - `30_table_merge_min`
  - `40_trackchange_min`
  - `50_master_min`
  - `60_history_version_min`
  - `99_all_in_one_stress`
- 결과: 전 항목 통과

### Fixture extract smoke
- `hwpx-skill/scripts/text_extract.py`를 `core/00_smoke_min.hwpx`에 실행
- `SMOKE_01` 토큰 확인 성공

### Core
- `core_stack_smoke.py`로 `core_created.hwpx` 생성 성공
- 텍스트 재추출 성공
- 표 개수 `1`
- 참고: manifest에서 master/history/version 파트 fallback 로그가 있었지만, smoke 자체는 정상 통과

### MCP
- focused smoke 테스트 통과
- 출력: `......... [100%]`

### Skill
- generated smoke 문서에 대한 텍스트 추출 성공
- 치환 + namespace 정리 성공
- 결과 문서 재검증 성공
- 최종 치환 문구 `스모크테스트` 확인

## 5. semantic finding: history/version fixture

`60_history_version_min.hwpx`는 이름과 달리, 현재 분석 가능한 범위에서
**dedicated history/version semantic fixture로는 인정하지 않았다.**

근거:
- `version.xml`은 모든 imported fixture에 공통으로 존재
- `hhs:*` 전용 element 없음
- 전용 history signal이 구조적으로 보이지 않음

따라서 현재 분류는:
- 유지: 구조 샘플
- 금지: history/version feature 검증 기준선

참고 문서:
- `shared/hwpx/fixtures/HISTORY_VERSION_FIXTURE_FINDINGS.md`

## 6. 산출물

fixture 관련:
- `shared/hwpx/fixtures/README.md`
- `shared/hwpx/fixtures/fixture_matrix.json`
- `shared/hwpx/fixtures/EDITOR_AUTHORED_IMPORT_2026-04-16.md`
- `shared/hwpx/fixtures/HISTORY_VERSION_FIXTURE_FINDINGS.md`
- `shared/hwpx/fixtures/manifests/*.yml`

smoke 산출물:
- `shared/hwpx/tmp/smoke/fixture_extract.txt`
- `shared/hwpx/tmp/smoke/core_created.hwpx`
- `shared/hwpx/tmp/smoke/core_replaced.hwpx`
- `shared/hwpx/tmp/smoke/skill_extract.txt`
- `shared/hwpx/tmp/smoke/skill_inspect.txt`
- `shared/hwpx/tmp/smoke/stack_smoke.log`

## 7. 판단

- 현재 로컬 기준에서 HWPX 스택 smoke path는 정상 통과했다.
- generated smoke만 쓰던 상태에서 벗어나, **editor-authored sanitized fixture baseline**이 스택 기준선에 편입됐다.
- dedicated history/version fixture는 아직 비어 있으므로, 그 기능을 본격 검증하려면 별도 editor-authored 원본을 새로 확보해야 한다.

한 줄 결론:

**2026-04-16 기준, HWPX 스택은 editor-authored sanitized fixture baseline까지 포함한 자동화 smoke 경로로 다시 통과했다.**
