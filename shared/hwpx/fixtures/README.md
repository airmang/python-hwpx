# HWPX Stack Fixtures

이 디렉토리는 `python-hwpx`, `hwpx-mcp-server`, `hwpx-skill`이 같이 보는 fixture 기준점이다.

## 핵심 정책

1. canonical 기준선은 **실제 편집기에서 만든 `.hwpx` 원본**을 우선한다.
2. agent나 라이브러리가 만든 `.hwpx`는 **supplemental**로만 쓴다.
3. 외부에서 가져온 원본은 **metadata/privacy 점검** 전에는 public fixture로 승격하지 않는다.
4. smoke, README, validation report는 같은 fixture 이름을 공유한다.

## 현재 기준선 (2026-04-16)

### editor-authored sanitized baseline

원본:
- `private://hwpx_smoke`

로컬 기준선:
- `shared/hwpx/fixtures/`

가져오고 scrub까지 끝낸 세트:
- `core/00_smoke_min.hwpx`
- `fields/10_fieldcodes_min.hwpx`
- `forms/20_formcontrols_min.hwpx`
- `tables/30_table_merge_min.hwpx`
- `change-tracking/40_trackchange_min.hwpx`
- `sections/50_master_min.hwpx`
- `history/60_history_version_min.hwpx`
- `stress/99_all_in_one_stress.hwpx`

metadata scrub 결과:
- `creator` → `fixture`
- `lastsaveby` → `fixture`
- date 계열 → 고정 sentinel 값
- 원본 NAS 세트는 유지되고, local copy만 정규화했다.

### 현재 판정

- `00_smoke_min` → minimal baseline
- `10_fieldcodes_min` → field / hyperlink / page number baseline
- `20_formcontrols_min` → checkbox / radio / edit baseline
- `30_table_merge_min` → merged table baseline
- `40_trackchange_min` → track-change insertion baseline
- `50_master_min` → header/footer baseline
- `99_all_in_one_stress` → 통합 회귀/stress baseline

### 중요한 결론: `60_history_version_min`

이 파일은 import와 scrub는 끝났지만, **history/version 전용 fixture로는 판정하지 않았다.**

확인 결과:
- 모든 fixture에 `version.xml`이 공통으로 존재한다.
- `60_history_version_min`의 `version.xml`은 다른 fixture와 구별되지 않는다.
- 전용 history namespace element (`hhs:*`)는 확인되지 않았다.
- 전용 master-page namespace element (`hm:*`)도 확인되지 않았다.

따라서 현재 용도는:
- **basic single-paragraph structural sample**
- history/version semantic baseline으로는 사용 금지

즉, dedicated history fixture가 필요하면 **별도 editor-authored 원본을 새로 확보해야 한다.**

### secondary asset

repo 내부 자산은 여전히 보조로 유용하다.

- `examples/FormattingShowcase.hwpx`
- `examples/note_example.hwpx`
- `../hwpx-mcp-server/tests/hwpx_mcp_test.hwpx`
- `../hwpx-mcp-server/tests/sample.hwpx` (`supplemental only`)

## 운영 규칙

- editor-authored sanitized 세트를 먼저 본다.
- generated writer smoke는 허용하지만 canonical이라고 부르지 않는다.
- import된 원본은 manifest와 matrix와 함께 관리한다.
- public 승격 전에는 creator/metadata/privacy를 다시 본다.

## 연결된 파일

- fixture matrix:
  - `shared/hwpx/fixtures/fixture_matrix.json`
- metadata scrub script:
  - `shared/hwpx/scripts/sanitize_fixture_metadata.py`
- fixture smoke matrix:
  - `shared/hwpx/scripts/fixture_smoke_matrix.py`
- import report:
  - `shared/hwpx/fixtures/EDITOR_AUTHORED_IMPORT_2026-04-16.md`
- history finding:
  - `shared/hwpx/fixtures/HISTORY_VERSION_FIXTURE_FINDINGS.md`

## 현재 상태 한 줄

**editor-authored sanitized fixture baseline은 확정됐다. 다만 history/version 전용 fixture는 아직 비어 있다.**
