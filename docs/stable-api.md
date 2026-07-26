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
major에서 제거합니다(경고 없는 즉시 제거 금지). 4.0.0에서 제거되는 이름은 **0개**
입니다 — 기존 최상위 이름은 전부 계속 import 가능하며, 비-stable 이름만 경고를 냅니다.

### 지원되지 않는(비공개) 표면

`hwpx.oxml.*`, `hwpx._document.*` 등 내부 XML/구현 모듈을 직접 import하는 것은
**공개 표면이 아닙니다**. 이 경로들은 예고 없이 바뀔 수 있으니 위 계층의 이름만
사용하세요.

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

## experimental (12)

`from hwpx.experimental import ...`로 사용하세요. 계약이 유동적입니다.

- **문서 ingestion 프레임워크**(임의 포맷 → HWPX): `DocumentIngestor`,
  `DocumentConverter`, `DocumentIngestResult`, `DocumentSourceInfo`,
  `ConversionAttempt`, `DocumentIngestError`, `UnsupportedDocumentFormat`
- **레이아웃 프리뷰**(한컴 없는 정직 근사): `render_layout_preview`,
  `LayoutPreview`, `PreviewPage`
- **문서 프리뷰 뷰어**(3.8.0 신규): `render_document_viewer`, `DocumentViewer`

> `HwpxMarkdownConverter`(HWPX → Markdown 읽기)는 성숙한 경로라 **stable**입니다.
> 위 ingestion 프레임워크(임의 포맷 → HWPX)만 experimental입니다.

## 5.0에서 제거된 deprecated 표면 (4)

대체 = **구조적 form-fill 경로**(라이브러리 `hwpx.table_patch.fill_cells` 계열,
MCP `analyze_form_fill`/`apply_form_fill`/`verify_form_fill`).

- `analyze_template_formfit`, `apply_template_formfit`
- `TEMPLATE_FORMFIT_BASELINE_SCHEMA_VERSION`, `TEMPLATE_FORMFIT_PLAN_SCHEMA_VERSION`

## 오류 계약 (4.0.0 신규)

fail-closed 공개 경로가 던지는 예외는 `hwpx.errors.HwpxError`(최상위 `hwpx.HwpxError`
로도 import) 베이스를 상속합니다. 사람용 문장(`str(exc)`)은 그대로 두고, 세 가지
**기계가 읽는** 필드를 얹습니다:

| 속성 | 의미 |
|---|---|
| `code` | 실패 종류의 안정 식별자(kebab-case). 분기 가능하며 major 경계에서만 바뀜. |
| `context` | 실패를 유발한 **실측 값** 딕셔너리(오프닝 part·인덱스·개수…). 없으면 `{}`. |
| `suggestion` | 실행 가능한 다음 한 단계, 없으면 `None`. |

`exc.to_dict()`는 `{code, message, context, suggestion}` 봉투를 돌려줍니다.

### 상속으로 하위 호환 유지

구조화 이전에도 각 예외는 `ValueError`/`RuntimeError`/`Exception`이었고, 4.0.0에서도
그 관계를 유지합니다 — 기존 `except`가 깨지지 않습니다.

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
