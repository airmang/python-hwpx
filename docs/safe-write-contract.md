# 안전한 쓰기 계약 (Safe Write Contract)

`python-hwpx`의 모든 대표 저장 경로(`save` · `to_bytes`)는
**요청한 보존 등급을 쓰기 전에 판정하고, 실제로 무엇을 바꿨는지 측정한 영수증을
돌려주는** 계약을 따른다. 이 계약의 이름은 `hwpx.mutation-report/v1`이며,
영수증 객체는 `hwpx.mutation_report.MutationReport`다.

> **Python 블록 판정:** [실행 분류 ledger](python-example-ledger.json)가 이
> current manual의 모든 Python 블록을 동결합니다. **독립 실행 예제** 표시가
> 없는 블록은 API 표기, 기존 입력 파일, 또는 앞 문맥이 필요한 조각입니다.

핵심 원칙은 두 가지다.

- **Fail-Closed** — `mode="patch"` + `fallback="error"`(기본값)로 요청했는데
  미수정 part를 바이트 동일하게 유지할 수 없으면, **아무것도 쓰지 않고**
  `PreservationDowngradeError`를 던진다. 사용자 동의 없는 무음 rebuild는 없다.
- **Measured, not asserted** — 영수증의 보존 수치는 주장이 아니라, 빌드된 아카이브를
  저장 직전 part 페이로드와 비교해 **측정**한 결과다. "byte-preserving"이라는 한
  단어로 뭉개지 않고 세 층으로 분리해 보고한다.

> **이름 확정(7.0).** 저장은 `doc.save(target)` 하나다 — *target*은 경로나 쓰기 가능한
> 이진 스트림이고, 늘 영수증을 돌려준다. 바이트는 `to_bytes()`. 6.x의 `save_to_path` ·
> `save_to_stream` · `save_report`는 7.0에서 `save`로 합쳤다(부르면 새 자리를 알려 주는 오류가
> 난다). [7.0 마이그레이션](migration-7.0.md) 참조.

## 파라미터

두 저장 메서드가 같은 등급 인자를 받는다.

```python
def save(target, *, format=None, mode="auto", fallback="error", quality=None) -> MutationReport: ...
def to_bytes(*, mode="auto", fallback="error", format="hwpx"): ...   # bytes 반환
```

### `mode` — 요청 보존 등급

| 값 | 의미 |
|---|---|
| `"patch"` | 지원되는 국소 mutation만 허용한다. 미수정 part는 전부 바이트 동일하게 유지돼야 한다. |
| `"rebuild"` | 변경된 part의 재직렬화를 명시적으로 허용한다. |
| `"auto"` (기본값) | 사전 측정에서 **달성 가능한 가장 강한 등급**을 자동 선택한다. 보존 등급 미달 자체를 오류로 처리하지 않는다. |

### `fallback` — 보존 등급 미달 시 동작 (`mode="patch"`에서만 의미 있음)

| 값 | 의미 |
|---|---|
| `"error"` (기본값) | 요청한 patch 등급을 만족하지 못하면 **출력하지 않고** `PreservationDowngradeError`를 던진다. |
| `"rebuild"` | 명시적으로 허용한 경우에만 rebuild로 강등하고, 그 사실을 영수증의 `fallbackUsed=true`로 남긴다. |

> `mode="auto"`는 달성 가능한 등급을 채택하므로 등급 미달에 따른
> `PreservationDowngradeError`를 발생시키지 않는다. I/O 오류나 패키지·안전 검증
> 실패는 여전히 발생할 수 있다. patch 등급을 강제하려면 `mode="patch"`를 명시하라.

### 영수증과 `quality` — 품질 게이트

`save`는 늘 `MutationReport`를 돌려준다(저장한 경로는 `report.path`, 스트림이면 `None`).
`to_bytes`는 bytes를 돌려준다. `quality=`에 `QualityPolicy`(예: `QualityPolicy(require_visual_complete=False)`)를
주면 쓰기 전에 그 품질 게이트를 돌리고, 게이트의 `VisualCompleteReport`를 `report.quality`에
담는다. 게이트가 막으면 아무것도 쓰지 않고 `SaveError`(`quality-gate-failed`)를 던지며, 그
보고는 `exc.report`에 있다. `QualityPolicy.strict()`(=`QualityPolicy()`)는 렌더 확인까지 요구한다. 코어는 렌더하지
않으므로, 렌더러를 붙이지 않았으면 이 정책은 통과하지 못하고 오류가 그 이유를 말한다.

## 사용 예

```python
from hwpx import HwpxDocument
from hwpx.mutation_report import PreservationDowngradeError

doc = HwpxDocument.open("신청서.hwpx")
doc.tables[0].cell(0, 1).text = "홍길동"   # 표 지도(doc.tables.map())로 확인한 칸

# 1) 영수증과 함께 저장 (달성 가능한 최강 등급 자동 선택)
report = doc.save("신청서-완료.hwpx")
print(report.actual_mode)          # "patch" 또는 "rebuild"
print(report.preservation.untouched_part_payloads.to_dict())
#   → {"verified": 17, "changed": 0}

# 2) patch 등급을 강제 — 미달이면 아무것도 쓰지 않고 예외
try:
    doc.save("신청서-완료.hwpx", mode="patch", fallback="error")
except PreservationDowngradeError as exc:
    print(exc.offending_parts)     # 바이트 동일성을 깨는 part 목록
    print(exc.suggestion)          # 어떻게 patch 경로로 우회할지 제안
```

## `MutationReport`

### 기존 양식의 요청값까지 확인하고 발행하기

저장 성공만으로 과업 완료를 판단하지 않는다. 실행 가능한
[편집 예제](https://github.com/airmang/python-hwpx/blob/main/examples/edit_existing_form.py)의
`fill_existing_form(source, output, values)`는 **본문 표에서 글이 정확히 그 라벨인
유일한 칸의 오른쪽 셀**을 채우는 경로다. `values`는 `{"성명": "홍길동"}`처럼 라벨과
문자열 값을 받는다. 공백을 무시한 라벨 비교나 `라벨 > right > down` 같은 경로는
7.0에서 python-hwpx-automation(`hwpx_automation.forms`)으로 옮겼고, 이 예제는 엔진의
칸 읽기·쓰기만 쓴다.

1. 원본과 출력이 다른 파일인지 확인한다(심볼릭 링크·하드 링크 포함).
2. 요청한 모든 라벨이 유일한 대상 셀로 해석되는지 먼저 확인한다.
   `expected_values={"성명": "기존 이름"}`을 주면 수정 전 값도 전건 대조한다.
3. 채움 결과의 실패·적용 건수를 확인하고 `patch/error`로 임시 사본을 저장한다.
4. 임시 사본을 다시 열어 대상 위치와 값 전건을 확인한다.
5. 원본 변경 여부를 확인한 뒤 검증된 사본을 최종 출력으로 원자적으로 옮긴다.

실패 시 기존 출력은 교체되지 않는다. 이는 단일 작업용 예제이며, 동시 편집의
revision·session 제어는 automation workflow를 사용한다. 응답은 요청 반영,
저장 영수증, 수정 part 내부 보존 미검증, 시각 미검증을 분리한다.
긴 값으로 인한 줄바꿈·쪽수 변화는 한컴 재조판 확인이 필요하다. `patch`만으로
수정한 part 내부의 미수정 영역이나 페이지 배치까지 동일하다고 판단하지 않는다.

실제 기관 양식에는 라벨과 입력칸 사이에 좁은 빈 셀이 있을 수 있다.
`right`는 바로 다음 셀을 뜻하며 "사람이 의도한 입력칸"을 추측하지 않는다.
예상 기존 값이 어긋나면 표 지도(`doc.tables.map()`)를 다시 확인하고 채울 칸을
행·열로 직접 고른다(`doc.tables[0].cell(행, 열).text = 값`). 이 예제는 그런 경우
다른 셀을 자동으로 선택하지 않는다.

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
- `untouchedLocalZipRecords` — 손대지 않은 part의 **ZIP local record 전체**(로컬 머리·
  압축된 바이트·데이터 디스크립터)가 원본과 바이트째 같은지. 저장은 고치지 않은 항목의
  기록을 원본에서 그대로 옮기므로 Python의 zlib 구현에 달리지 않는다. 원본 바이트가 없는
  문서(`new()`, 변환한 `.hwp`)는 기록 메타데이터(타임스탬프·압축 방식·플래그 등)를 견준다.
- `wholePackageIdentical` — 쓴 파일이 원본 파일과 바이트째 같은지. **no-op(변경 없음)일
  때** 참이다(`mimetype`의 자리·압축과 폴더 항목도 원본 그대로 옮긴다). 편집이 있으면
  거짓이다. 손댄 파트의 압축된 바이트는 zlib 구현(zlib·zlib-ng)에 달린다. 다시 읽을 수 없는
  스트림에 저장하면 쓴 바이트를 확인하지 못했으므로 거짓이다(`outputReadBack`).
- `zipRecordsRewritten` — 원본 ZIP을 항목별로 옮길 수 없어(ZIP64·첫 항목 앞이나
  목록 뒤의 다른 바이트 등) 모든 항목을 다시 압축했을 때만 있는 키. 값은 그 까닭이다. 이때도
  중앙 디렉터리 차례·기록의 물리 차례·`mimetype`의 자리와 압축·아카이브 주석은 원본 그대로다.
  이름이 같은 항목이 둘 이상인 원본은 저장도 바이트 패치도 거부한다(`save-duplicate-entry-names`).
- `outputReadBack` — 저장한 스트림이 읽기를 거부해 쓴 내용을 다시 읽어 확인하지 못했을 때만
  있는 키(값 `false`, 이때 `wholePackageIdentical`도 거짓). 끝 위치만 확인했다는 뜻이다.

### 검증 4항목 (`verification`)

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

## 편집 계획 실행기와의 관계 (`hwpx.plan`, 5.6.0+)

다단 편집을 안전-쓰기 계약 위에서 합성하려면 `hwpx.plan.apply_edit_plan`을
사용한다. 계획의 각 step은 기존 바이트-스플라이스 op를 이름 그대로 지시하고,
실행기는:

1. **정적 선검증** — 파일을 열지 않고 스키마·op 어휘·인자 형상을 fail-closed로
   검증한다(미지 필드 즉시 거부).
2. **인메모리 체이닝** — 각 op를 `output_path` 없이 바이트→바이트로 연결한다.
   개별 op가 skip이 있어도 파일을 쓰는 동작을 실행기가 쓰기 소유로 차단한다
   (열기 안전 검사에 떨어진 결과는 개별 op도 쓰지 않는다).
3. **원자 쓰기** — 전 step 성공 + 최종 open-safety 검증 통과 후 단 한 번의
   `os.replace`로만 output을 쓴다. **그 전 어떤 실패에서도 output과 source는
   바이트 불변이다**(테스트가 바이트 비교로 증명).

결과 `hwpx.plan-report/v1`은 step별 `hwpx.mutation-report/v1` 사영(입력 바이트
스레딩 = 실측 등급)과 원본→최종 집계 사영을 싣는다 — step 합성 밖의 변경은
집계에서 `unexpected`로 드러난다. 보존 등급 플로어는 v1 어휘(전부 스플라이스)
에서 항상 `patch`다.

## 관련 문서

- [실측 코퍼스 메트릭](corpus-metrics.md) — 바이트 보존 497/497(patch 경로) 실측
- [지원 매트릭스](support-matrix.md) — 능력별 Parse/Preserve/Edit/Create/Render 등급
