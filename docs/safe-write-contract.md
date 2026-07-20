# 안전한 쓰기 계약 (Safe Write Contract)

`python-hwpx`의 모든 대표 저장 경로(`save_to_path` · `save_to_stream` · `to_bytes`)는
**요청한 보존 등급을 쓰기 전에 판정하고, 실제로 무엇을 바꿨는지 측정한 영수증을
돌려주는** 계약을 따른다. 이 계약의 이름은 `hwpx.mutation-report/v1`이며,
영수증 객체는 `hwpx.mutation_report.MutationReport`다.

핵심 원칙은 두 가지다.

- **Fail-Closed** — `mode="patch"` + `fallback="error"`(기본값)로 요청했는데
  미수정 part를 바이트 동일하게 유지할 수 없으면, **아무것도 쓰지 않고**
  `PreservationDowngradeError`를 던진다. 사용자 동의 없는 무음 rebuild는 없다.
- **Measured, not asserted** — 영수증의 보존 수치는 주장이 아니라, 빌드된 아카이브를
  저장 직전 part 페이로드와 비교해 **측정**한 결과다. "byte-preserving"이라는 한
  단어로 뭉개지 않고 세 층으로 분리해 보고한다.

## 파라미터

세 저장 메서드 모두 같은 시그니처를 공유한다.

```python
doc.save_to_path(path, *, mode="auto", fallback="error", return_report=False)
doc.save_to_stream(stream, *, mode="auto", fallback="error", return_report=False)
doc.to_bytes(*, mode="auto", fallback="error")   # bytes 반환, return_report 없음
```

### `mode` — 요청 보존 등급

| 값 | 의미 |
|---|---|
| `"patch"` | 지원되는 국소 mutation만 허용한다. 미수정 part는 전부 바이트 동일하게 유지돼야 한다. |
| `"rebuild"` | 변경된 part의 재직렬화를 명시적으로 허용한다. |
| `"auto"` (기본값) | 사전 측정에서 **달성 가능한 가장 강한 등급**을 자동 선택한다. 절대 예외를 던지지 않는다. |

### `fallback` — 보존 등급 미달 시 동작 (`mode="patch"`에서만 의미 있음)

| 값 | 의미 |
|---|---|
| `"error"` (기본값) | 요청한 patch 등급을 만족하지 못하면 **출력하지 않고** `PreservationDowngradeError`를 던진다. |
| `"rebuild"` | 명시적으로 허용한 경우에만 rebuild로 강등하고, 그 사실을 영수증의 `fallbackUsed=true`로 남긴다. |

> `mode="auto"`는 달성 가능한 등급을 그대로 채택하므로 `fallback`과 무관하게 예외를
> 던지지 않는다. fail-closed 강제가 필요하면 `mode="patch"`를 명시하라.

### `return_report` — 영수증 반환

`True`이면 저장 경로(또는 스트림)를 반환하는 대신 `MutationReport`를 돌려준다.
`to_bytes`는 항상 bytes를 반환하므로 이 파라미터가 없다.

## 사용 예

```python
from hwpx import HwpxDocument
from hwpx.mutation_report import PreservationDowngradeError

doc = HwpxDocument.open("신청서.hwpx")
doc.fill_by_path({"성명 > right": "홍길동"})

# 1) 영수증과 함께 저장 (달성 가능한 최강 등급 자동 선택)
report = doc.save_to_path("신청서-완료.hwpx", return_report=True)
print(report.actual_mode)          # "patch" 또는 "rebuild"
print(report.preservation.untouched_part_payloads.to_dict())
#   → {"verified": 17, "changed": 0}

# 2) patch 등급을 강제 — 미달이면 아무것도 쓰지 않고 예외
try:
    doc.save_to_path("신청서-완료.hwpx", mode="patch", fallback="error")
except PreservationDowngradeError as exc:
    print(exc.offending_parts)     # 바이트 동일성을 깨는 part 목록
    print(exc.suggestion)          # 어떻게 patch 경로로 우회할지 제안
```

## `MutationReport`

`report.to_dict()`는 `hwpx.mutation-report/v1` JSON을 그대로 반환한다.

```json
{
  "schemaVersion": "hwpx.mutation-report/v1",
  "ok": true,
  "path": "신청서-완료.hwpx",
  "requestedMode": "auto",
  "actualMode": "patch",
  "fallbackUsed": false,
  "changedParts": [
    {
      "path": "Contents/section0.xml",
      "reason": "dirty-part",
      "ranges": [
        {"start": 14402, "end": 14431, "coordinateSpace": "uncompressed-part-bytes"}
      ]
    }
  ],
  "preservation": {
    "untouchedPartPayloads": {"verified": 17, "changed": 0},
    "untouchedLocalZipRecords": {"verified": 17, "changed": 0},
    "wholePackageIdentical": false
  },
  "verification": {
    "package": "passed",
    "openSafety": "passed",
    "reopen": "passed",
    "visual": "not_performed"
  }
}
```

### 필드 의미

- `requestedMode` / `actualMode` — 요청한 등급과 실제 사용한 등급. 강등이 일어났다면
  둘이 다르고 `fallbackUsed=true`가 된다.
- `changedParts[].reason` — `"dirty-part"`(에디터가 사전 선언한 변경) 또는
  `"unexpected"`(선언하지 않았는데 바뀐 part). `unexpected`가 하나라도 있으면
  patch 등급이 아니다.
- `changedParts[].ranges` — byte-splice 경로에서만 채워지는 변경 스팬. rebuild 등급
  part는 페이로드 전체가 변경이므로 `null`이다. 좌표계는 항상
  `uncompressed-part-bytes`(압축 해제된 part 바이트)로 명시된다 — ZIP 압축 오프셋과
  혼동하지 않도록 계약에 고정돼 있다.

### 보존 3층 (`preservation`)

"byte-preserving"을 한 단어로 표현하면 fallback 동작과 충돌하므로, 서로 다른 세
보증을 분리해 보고한다.

- `untouchedPartPayloads` — 손대지 않은 part의 **압축 해제 페이로드 동일성**.
  이것이 바이트 보존 해자의 핵심 지표다.
- `untouchedLocalZipRecords` — 손대지 않은 part의 **ZIP local-record 메타데이터**
  (타임스탬프·압축 방식·플래그 등) 동일성. 내용 파생 필드(CRC·크기)는 제외한다.
- `wholePackageIdentical` — 전체 패키지 바이트 동일성. **no-op(변경 없음)일 때만**
  참이 될 수 있다. deflate·producer 차이 때문에 편집이 있으면 절대 보장하지 않는다.

### 검증 3항목 (`verification`)

각 항목은 `"passed"` / `"failed"` / `"not_performed"` 세 값만 가진다.
**렌더를 돌리지 않았으면 `not_performed`이지 무음 pass가 아니다**(No Silent True).

- `package` — 패키지 구조 검증 결과
- `openSafety` — 에디터 오픈 안전성 게이트 결과
- `reopen` — 저장 직후 재오픈 프로브 결과
- `visual` — 실한컴 렌더 비교 결과(오라클이 붙었을 때만 `passed`/`failed`)

`report.ok`는 위 네 항목 중 `"failed"`가 하나도 없을 때 참이다.

## `PreservationDowngradeError`

`mode="patch"` + `fallback="error"`에서 patch 등급을 달성할 수 없을 때, **출력 전에**
던져진다(specs/032 §1). 부착 속성:

- `requested_mode` — 요청 등급 (`"patch"`)
- `achieved_grade` — 실제 달성 가능했던 등급 (`"patch"` / `"rebuild"`)
- `offending_parts` — 바이트 동일성을 깨는 part 이름 튜플
- `suggestion` — byte-preserving 프리미티브(`hwpx.patch` · `hwpx.table_patch` ·
  `hwpx.body_patch`)로 우회하거나 `fallback="rebuild"`를 쓰라는 안내 문자열

## 관련 문서

- [실측 코퍼스 메트릭](corpus-metrics.md) — 바이트 보존 497/497(patch 경로) 실측
- [지원 매트릭스](support-matrix.md) — 능력별 Parse/Preserve/Edit/Create/Render 등급
