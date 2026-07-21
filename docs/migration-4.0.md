# 4.0.0 마이그레이션 안내

4.0.0은 major 경계입니다. **제거된 공개 이름은 아래 표의 것들뿐이며**, 각 항목은
이미 여러 릴리스에서 `DeprecationWarning`을 달고 있던 것들입니다(최소 deprecation
window 준수 — 경고 없는 즉시 제거는 하지 않습니다). 최상위 표면(`from hwpx import
...`)에서 사라진 stable/experimental/deprecated 이름은 **0개**입니다 —
`docs/stable-api.md` 참조.

## 제거된 이름

| 제거 항목 | 경고 도입 | 대체 |
|---|---|---|
| `HwpxDocument.save(path_or_stream=None)` | v2.6 (2026-02-19, 커밋 `25c2ed7`)부터 `DeprecationWarning` | 목적지별 명시 메서드로 분리: 경로=`save_to_path(path)`, 스트림=`save_to_stream(stream)`, 바이트=`to_bytes()` |

### `save()` 이전 예시

```python
# 이전 (제거됨)
doc.save("out.hwpx")      # 경로
doc.save(stream)          # 스트림
data = doc.save()         # 바이트

# 4.0.0
doc.save_to_path("out.hwpx")
doc.save_to_stream(stream)
data = doc.to_bytes()
```

세 후속 메서드는 [안전한 쓰기 계약](safe-write-contract.md)을 따릅니다 —
`mode`/`fallback` 등급 제어와 `return_report=True` 영수증(`hwpx.mutation-report/v1`)을
지원하며, `save()`에는 없던 기능입니다.

## 유지된 장기-deprecated 항목

| 항목 | 경고 도입 | 4.0.0 처리 | 이유 |
|---|---|---|---|
| `hwpx.package` 모듈 (→ `hwpx.opc.package`) | v2.3.1 (2026-02-28) 직접 import 시 `DeprecationWarning` | **유지** | stable 공개 클래스 `HwpxPackage`의 역사적 import 경로. 재내보내기 shim이라 유지 비용 0이고 제거 blast radius(문서·직접 import)가 이득보다 큼. 다음 major에서 재검토. |

## 구조화 예외 (신규, 4.0.0)

fail-closed 공개 경로는 이제 [`HwpxError`](stable-api.md#오류-계약-4.0.0-신규) 베이스를
상속하는 예외를 던집니다 — `code`·`context`·`suggestion` 속성이 붙습니다. 기존
`except` 타입(`ValueError`/`RuntimeError`/`PreservationDowngradeError`)은 그대로
동작합니다(상속 관계 유지). 자세한 내용은 stable-api.md의 오류 계약 절을 보세요.
