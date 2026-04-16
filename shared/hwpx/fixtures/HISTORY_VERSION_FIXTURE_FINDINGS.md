# History / Version fixture findings (2026-04-16)

대상:
- `history/60_history_version_min.hwpx`

## 확인 내용

1. `version.xml` 존재 여부 확인
   - 존재함
   - 하지만 이 파일은 다른 imported fixture에도 모두 존재한다.

2. history namespace element 확인
   - `hhs:*` 전용 element 없음

3. master-page namespace element 확인
   - `hm:*` 전용 element 없음

4. preview / text 관찰
   - preview: `test_test`
   - text chars: `9`
   - paragraphs: `1`
   - tables: `0`

## 결론

`60_history_version_min.hwpx`는 이름과 달리, 현재 분석 가능한 범위에서는
**history/version 전용 semantic fixture라고 보기 어렵다.**

따라서 현재 분류는 아래가 맞다.

- 유지: 구조 샘플
- 금지: dedicated history/version feature 검증

## 다음 권장안

history/version 기능을 정말 검증하려면 아래 중 하나가 필요하다.

1. 실제 편집기에서 history/version 관련 상태가 명확히 들어간 새 `.hwpx` 확보
2. 어떤 XML signal을 history/version의 ground truth로 볼지 먼저 정의
3. 그 signal을 포함하는 editor-authored fixture를 다시 수집
