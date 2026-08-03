# 안정 API 표면 (Stable API)

`from hwpx import ...` 최상위 표면은 세 계층으로 나뉩니다. 계층에 따라 계약의
강도와 변경 예고 방식이 다릅니다.

## 계층 정책

- **stable** — `hwpx.__all__`에 있는 이름. 계약(시그니처·동작·반환 스키마)이 굳어
  있고, **major 경계에서만** 깨질 수 있습니다. 접근 시 경고가 없습니다.
- **experimental** — 계약이 **유동적**입니다. minor 릴리스에서 변경될 수 있으므로
  `from hwpx.experimental import ...`로 import하세요. 최상위 `from hwpx import ...`
  경로도 하위 호환을 위해 유지하지만 접근 시 `DeprecationWarning`이 나며, **다음
  major에서 최상위 재내보내기가 제거**될 예정입니다(실제 구현 모듈·`hwpx.experimental`
  경로는 유지).
- **deprecated** — 대체 경로로 이전하세요. 접근 시 `DeprecationWarning`이 나고 경고
  메시지에 대체 경로가 포함됩니다. **다음 major에서 제거**될 예정입니다.

### 최소 deprecation window

이름을 제거하려면 **먼저 한 번의 major에서 `DeprecationWarning`을 낸 뒤** 그다음
major에서 제거합니다(경고 없는 즉시 제거 금지). 4.0.0은 이 창을 여는 major였고
제거된 이름이 **0개**였습니다. 5.0.0은 그 창을 닫는 major로, 4.x에서 경고를 내던
deprecated 표면 4종을 제거합니다(아래 「5.0에서 제거된 deprecated 표면」).
응용 계층으로 옮겨 간 이름은 제거가 아니라 **이동**이며, import하면 어디로 갔는지
알려 주는 오류가 납니다 — [5.0 마이그레이션 가이드](migration-5.0.md) 참조.

### 반환되는 객체 — `hwpx.model` 이 계약이다 (6.0)

5.x 의 이 절은 자기모순이었다. `hwpx.oxml.*` 을 "공개 표면이 아니다"라고
선언하면서, stable 로 선언한 `HwpxDocument` 의 메서드들이 `HwpxOxmlParagraph`·
`HwpxOxmlTable`·`HwpxOxmlSection` 등 **18종을 반환**했다. 사용자는
"비공개"라고 적힌 타입을 손에 쥐고 그것으로 일할 수밖에 없었다.

6.0 은 이렇게 정리한다.

**`hwpx.model` 이 계약이고, `hwpx.oxml` 은 그것이 사는 곳이다.**

```python
from hwpx import model
from hwpx.oxml.paragraph import HwpxOxmlParagraph

assert model.Paragraph is HwpxOxmlParagraph   # 래퍼가 아니라 별칭이다
```

래퍼를 만들지 않은 이유: 객체 모델이 두 벌이 되고, 래퍼는 결국 `.oxml` 을
노출해야 하므로 같은 누출에 코드만 두 배가 된다. 반대로 `hwpx.oxml` 전체를
stable 로 올리면 24개 모듈 수백 멤버가 major 에서만 바뀔 수 있게 되어, 바로 그
클래스들에 요소를 더해야 하는 포맷 깊이 작업이 멈춘다.

**계약은 클래스가 아니라 멤버 목록이다.** `tests/data/model_surface.json` 이
클래스별로 stable 멤버를 정확히 나열한다 — 현재 **18개 클래스 / 171개
멤버**.

- 목록 **안**의 멤버 → stable. major 경계에서만 바뀐다.
- 목록 **밖**의 멤버(79개 — `apply_model`·`mark_dirty`·`remove_stale_layout_caches`
  등) → 구현 세부. minor 에서 바뀔 수 있다.

`hwpx.oxml.*` import 경로는 그대로 살아 있다. 옮기지도, deprecate 하지도 않는다.

### 지원되지 않는(비공개) 표면

`hwpx._document.*` 등 구현 모듈을 직접 import 하는 것은 공개 표면이 아니다.
`hwpx.oxml.*` 은 위 규칙을 따른다 — 경로는 열려 있고, 계약은 `hwpx.model` 의
멤버 목록이 정한다.

### 6.0 파사드 표면

`HwpxDocument` 의 공개 멤버는 **34개**다(5.x 는 102개). 나머지 79개는 도메인
네임스페이스로 이동했고, 옛 이름은 `DeprecationWarning` 과 함께 계속 답한다 —
7.0 에서 제거된다. 대응표는 [6.0 이주 가이드](migration-6.0.md).

이동은 제거가 아니므로 따로 센다:

| | 수 | 락 |
|---|---:|---|
| 루트 공개 멤버 | 34 | `tests/data/document_facade_surface.json` |
| 위임 shim (7.0 제거) | 79 | `tests/data/document_legacy_shims.json` |
| 반환 객체 계약 | 171 | `tests/data/model_surface.json` |

설치본에 직접 물어볼 수도 있다:

```bash
python -m hwpx.capabilities --verify
```

## stable (34)

major 경계에서만 깨지는 이름들입니다.

### 문서 열기·저장·패키지
- `HwpxDocument`, `HwpxPackage`
- `SavePipeline`, `QualityPolicy`, `VisualCompleteReport`
- `MutationReport`, `PreservationDowngradeError`
- `HwpxError` (구조화 예외 베이스 — 아래 오류 계약 참조)
- `EditorOpenSafetyReport`, `PackageValidationReport`,
  `validate_editor_open_safety`, `validate_package`

### 바이트 보존 패치
- `BytePreservingPatchResult`, `ParagraphTextPatch`, `PatchApplied`,
  `PatchSkipped`, `paragraph_patch`

### 읽기·추출
- `TextExtractor`, `ParagraphInfo`, `SectionInfo`, `DEFAULT_NAMESPACES`
- `ObjectFinder`, `FoundElement`
- `HwpxMarkdownConverter`

### 비교·메일머지
- `doc_diff`, `diff_paragraphs`, `inspect_reference_consistency`
- `merge_template_rows`, `load_mail_merge_rows`, `inspect_mail_merge_placeholders`
- `DOC_DIFF_REPORT_VERSION`, `REFERENCE_CONSISTENCY_REPORT_VERSION`,
  `MAIL_MERGE_REPORT_VERSION`

### 메타
- `__version__`

## experimental (23)

`from hwpx.experimental import ...`로 사용하세요. 계약이 유동적입니다.

- **문서 ingestion 프레임워크**(임의 포맷 → HWPX): `DocumentIngestor`,
  `DocumentConverter`, `DocumentIngestResult`, `DocumentSourceInfo`,
  `ConversionAttempt`, `DocumentIngestError`, `UnsupportedDocumentFormat`
- **레이아웃 프리뷰**(한컴 없는 정직 근사): `render_layout_preview`,
  `LayoutPreview`, `PreviewPage`
- **문서 프리뷰 뷰어**(3.8.0 신규): `render_document_viewer`, `DocumentViewer`
- **수식 저작**(5.2.0 신규, LaTeX → EqEdit): `latex_to_eqedit`,
  `estimate_equation_size`, `UnsupportedLatexError`
  — 이 세 이름은 5.2.0부터 experimental이었으나 이 문서가 누락하고 있었다
  (자기서술 드리프트 — `describe_capabilities()`의 라이브 census가 이제 이런
  누락을 구조적으로 막는다)
- **편집 계획 실행기**(5.6.0 신규, `hwpx.plan`): `apply_edit_plan`,
  `validate_edit_plan`, `EditPlan`, `PlanReport`, `PlanValidationError`
- **기계가독 자기서술**(5.6.0 신규, `hwpx.capabilities`):
  `describe_capabilities`, `contract_document`, `contract_json_schema`

> `HwpxMarkdownConverter`(HWPX → Markdown 읽기)는 성숙한 경로라 **stable**입니다.
> 위 ingestion 프레임워크(임의 포맷 → HWPX)만 experimental입니다.

## 5.0에서 제거된 deprecated 표면 (4)

대체 = **구조적 form-fill 경로**(라이브러리 `hwpx.table_patch.fill_cells` 계열,
MCP `analyze_form_fill`/`apply_form_fill`/`verify_form_fill`).

- `analyze_template_formfit`, `apply_template_formfit`
- `TEMPLATE_FORMFIT_BASELINE_SCHEMA_VERSION`, `TEMPLATE_FORMFIT_PLAN_SCHEMA_VERSION`

## 오류 계약 (4.0.0 도입)

아래 표에 있는 예외 — 쓰기 보존 계약, 저장 경로 게이트, 표 구조 편집, 이동된 표면
안내 — 는 `hwpx.errors.HwpxError`(최상위 `hwpx.HwpxError`로도 import) 베이스를
상속합니다. 모든 호출을 감싸는 포괄 계약은 아닙니다: 없는 파일은
`FileNotFoundError`, HWPX 패키지가 아닌 입력은 `zipfile.BadZipFile`처럼 파이썬이
원래 내는 예외가 그대로 올라옵니다([지원 매트릭스](support-matrix.md) 참조).
구조화된 예외는 사람용 문장(`str(exc)`)을 그대로 두고, 세 가지 **기계가 읽는**
필드를 얹습니다:

| 속성 | 의미 |
|---|---|
| `code` | 실패 종류의 안정 식별자(kebab-case). 분기 가능하며 major 경계에서만 바뀜. |
| `context` | 실패를 유발한 **실측 값** 딕셔너리(오프닝 part·인덱스·개수…). 없으면 `{}`. |
| `suggestion` | 실행 가능한 다음 한 단계, 없으면 `None`. |

`exc.to_dict()`는 `{code, message, context, suggestion}` 봉투를 돌려줍니다.

### 상속으로 하위 호환 유지

구조화 이전에도 각 예외는 `ValueError`/`RuntimeError`/`Exception`이었고, 4.0.0과
5.0.0 모두 그 관계를 유지합니다 — 기존 `except`가 깨지지 않습니다.

| 예외 | `code` | 상속 | 발생 경로 |
|---|---|---|---|
| `PreservationDowngradeError` | `preservation-downgrade` | `HwpxError` | `save_to_path`/`save_to_stream`/`to_bytes`의 `mode="patch"` + `fallback="error"` 미달 |
| `hwpx.errors.SaveError` | `save-failed`(기본), `document-validation-failed`·`open-safety-failed`·`quality-gate-failed` | `HwpxError`, `ValueError` | 대표 저장 경로의 사전검증·open-safety·품질 게이트 실패 |
| `hwpx.table_patch.TableStructureError` | `table-structure` | `HwpxError`, `ValueError` | 표 구조 편집 거부(fail-closed)·미지원 |
| `hwpx.table_patch.RenderCheckRequired` | `render-check-required` | `HwpxError`, `RuntimeError` | `verify_fill(require=True)`인데 실한컴 오라클 미렌더 |

응용 계층의 agent·exam 오류 계약은 `python-hwpx-automation`이 소유합니다.
이 문서는 core에 실제로 남은 공개 예외만 기술합니다.

## 스키마 동결 정책

core가 발행하는 versioned contract(`hwpx.mutation-report/v1`)는 required 필드
집합이 **동결**됩니다. document-plan·agent-batch·mixed-form-plan 스키마는 5.0에서
`python-hwpx-automation`이 발행 주체가 됐으며 그쪽 계약 정책을 따릅니다. 정책·계약 테스트는 [스키마 동결](schema-freeze.md)을 보세요.
