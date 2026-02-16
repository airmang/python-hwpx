# TBL-014 — 셀 범위 선택 + 글꼴 변경

## 목표

- 표 셀을 `Shift+클릭`으로 범위 선택할 수 있다.
- 선택된 셀 범위에 글꼴 변경이 적용된다.
- 저장 후 다시 열어도(직렬화/역직렬화) 글꼴 변경이 유지된다.

## 수동 테스트

### TBL-014-TC-001 (셀 범위 선택)

1. 표(예: 3x3)를 만든다.
2. (0,0) 셀을 클릭한다.
3. `Shift`를 누른 채 (1,1) 셀을 클릭한다.
4. 2x2 범위가 선택 상태(하이라이트)인지 확인한다.

### TBL-014-TC-002 (범위 글꼴 변경)

1. `TBL-014-TC-001` 상태에서, 우측 사이드바 > `글자` 탭의 `글꼴`을 다른 폰트로 변경한다.
2. 선택된 셀 범위 내 텍스트 글꼴이 변경되는지 확인한다.

### TBL-014-TC-003 (저장/재열기 유지)

1. `TBL-014-TC-002` 상태에서 저장한다.
2. 저장된 파일을 다시 열어 동일 범위 셀의 글꼴이 유지되는지 확인한다.

## 자동(Playwright)

- 실행: `pnpm test:feature-loop`
- 구현: `/Users/jskang/nomadlab/packages/hwpx-ts/packages/hwpx-editor/src/lib/feature-runner.ts` (`TBL-014`)
- 증빙: `/Users/jskang/nomadlab/packages/hwpx-ts/packages/hwpx-editor/features/evidence/playwright/TBL-014.png`

