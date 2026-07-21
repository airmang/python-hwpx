# 스키마 동결 정책 (4.0.0)

python-hwpx가 발행하는 versioned contract는 4.0.0에서 **required 필드 집합이
동결**됩니다. 목적은 한 가지 — 이미 나간 payload가 앞으로도 계속 검증을 통과하게
하는 것입니다.

## 동결 대상

| 스키마 | 동결된 required |
|---|---|
| `hwpx.mutation-report/v1` | `schemaVersion`, `ok`, `path`, `requestedMode`, `actualMode`, `fallbackUsed`, `changedParts`, `preservation`, `verification` |
| `hwpx.document_plan.v1` / `v2` | 봉투 `schemaVersion`·`blocks`; 각 block은 `type`만 |
| `hwpx.agent-batch/v1` | `schemaVersion`, `input`, `output`, `commands`, `expectedRevision`, `idempotencyKey`, `dryRun`, `quality`, `verificationRequirements` |
| `hwpx.mixed-form-plan/v1`(공개 plan) | `schemaVersion`, `source`, `output`, `expectedRevision`, `idempotencyKey`, `dryRun`, `overwrite`, `quality`, `verificationRequirements`, `operations` |

## 규칙 (additive-only)

1. **필드 추가는 허용, 단 Optional이어야 함.** 새 필드는 생략 가능해야 하며, 없을 때
   기존 동작이 유지돼야 합니다. 옛 payload가 그대로 통과합니다.
2. **required 승격 금지.** 기존 Optional 필드를 required로 올리거나 새 required 필드를
   추가하는 것은 **파괴 변경**입니다.
3. **파괴 변경은 새 major + 새 스키마 버전 문자열**로만. 예: `hwpx.document_plan.v3`,
   `hwpx.mutation-report/v2`. 같은 버전 문자열의 의미를 바꾸지 않습니다.

## 강제 방법

`tests/test_schema_freeze.py`가 각 스키마의 최소-유효 fixture(정확히 동결된 키만
가진)를 검증하고, required 키를 하나씩 제거하면 거부됨을 확인합니다. 미래에 required
필드가 추가되면 이 fixture가 검증을 통과하지 못해 테스트가 실패합니다 — 변경을
Optional로 만들거나 스키마 버전을 의도적으로 올리도록 강제합니다.

동결된 스키마는 대부분 **닫힌**(closed) 형태라 알 수 없는 키도 거부합니다. 따라서 새
Optional 필드도 검증기(또는 JSON 스키마 `properties`)에 명시적으로 추가해야 하며, 이때
`required`에는 넣지 않습니다.
