# Editor-authored HWPX fixture import report (2026-04-16)

원본:
- `private://hwpx_smoke`

복사 위치:
- `shared/hwpx/fixtures/`

## 요약

- 총 8개 `.hwpx` import 완료
- 모두 실제 편집기에서 만든 최소 재현용 세트로 분류
- local copy 기준 metadata scrub 완료
- editor-authored baseline smoke matrix 연결 완료

## scrub 결과

`Contents/content.hpf` 기준으로 아래를 정규화했다.

- `creator` → `fixture`
- `lastsaveby` → `fixture`
- `CreatedDate` → `1970-01-01T00:00:00Z`
- `ModifiedDate` → `1970-01-01T00:00:00Z`
- `date` → `1970-01-01T00:00:00Z`

원본 NAS 세트는 그대로 두고, shared fixture copy만 수정했다.

## 인벤토리

### 00_smoke_min.hwpx
- path: `core/00_smoke_min.hwpx`
- text chars: 59
- paragraphs: 3
- tables: 0
- preview: `제목입니다. <<SMOKE_01>> / 본문입니다. <<SMOKE_01>>`
- 판단: 가장 기본적인 read/open baseline

### 10_fieldcodes_min.hwpx
- path: `fields/10_fieldcodes_min.hwpx`
- text chars: 58
- paragraphs: 3
- tables: 0
- preview: `2026년 2월 24일 ... / 하이퍼링크입니다 / <<FIELD_MIN_CASE_01>>`
- 확인 신호:
  - `fieldBegin`
  - `fieldEnd`
  - `pageNum`
- 판단: field/hyperlink baseline

### 20_formcontrols_min.hwpx
- path: `forms/20_formcontrols_min.hwpx`
- text chars: 20
- paragraphs: 4
- tables: 0
- preview: `<<FORM_MIN_CASE_01>>`
- 확인 신호:
  - `checkBtn`
  - `radioBtn`
  - `edit`
- 판단: form control baseline

### 30_table_merge_min.hwpx
- path: `tables/30_table_merge_min.hwpx`
- text chars: 18
- paragraphs: 10
- tables: 1
- preview: `<<TABLE_MERGE_01>>`
- 확인 신호:
  - `tbl`
  - `tr`
  - `tc`
  - `cellSpan`
- 판단: merged table baseline

### 40_trackchange_min.hwpx
- path: `change-tracking/40_trackchange_min.hwpx`
- text chars: 20
- paragraphs: 2
- tables: 0
- preview: `NEW_LINE_1 / <<TC_01>>`
- 확인 신호:
  - `insertBegin`
  - `insertEnd`
- 판단: track change baseline

### 50_master_min.hwpx
- path: `sections/50_master_min.hwpx`
- text chars: 83
- paragraphs: 6
- tables: 0
- preview: preview text 비어 있음
- 확인 신호:
  - `header`
  - `footer`
- 판단: header/footer baseline

### 60_history_version_min.hwpx
- path: `history/60_history_version_min.hwpx`
- text chars: 9
- paragraphs: 1
- tables: 0
- preview: `test_test`
- 확인 결과:
  - `version.xml`은 존재하지만 모든 fixture에 공통이다
  - 전용 history namespace element는 확인되지 않았다
- 최종 판정:
  - dedicated history/version fixture로는 부적합
  - 단순 구조 샘플로만 유지

### 99_all_in_one_stress.hwpx
- path: `stress/99_all_in_one_stress.hwpx`
- text chars: 55
- paragraphs: 28
- tables: 2
- preview: `TEST ... <><><>`
- 확인 신호:
  - `fieldBegin`
  - `checkBtn`
  - `header`
  - `footer`
  - `tbl`
- 판단: 통합 회귀/stress baseline
