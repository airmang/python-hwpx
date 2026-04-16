# Fixture Import Queue

## 완료

- [x] NAS 경로 확인
  - `private://hwpx_smoke`
- [x] editor-authored 원본 8개 확인
- [x] shared fixture 트리로 로컬 복사
- [x] 1차 manifest 작성
- [x] feature별 기본 분류 완료
- [x] imported 8개 metadata scrub 적용
- [x] editor-authored 세트를 stack smoke/read validation에 연결
- [x] expected text / expected tags / expected counts를 `fixture_matrix.json`으로 고정
- [x] validation report에 fixture 이름 포함

## 후속 작업

### 선택 과제
- [ ] dedicated history/version editor-authored fixture 새로 확보
- [ ] MCP/Skill 표면별로 fixture별 시나리오를 더 세분화
- [ ] public 배포용 fixture bundle 기준을 별도 문서로 분리

### 메모
- `hwpx_smoke`는 더 이상 blocker가 아니다.
- 현재 열린 갭은 접근이 아니라 **history/version 전용 fixture 부재**다.
