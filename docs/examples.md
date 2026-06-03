# 실전 예제

다음 예제는 python-hwpx의 주요 API를 조합해 실제 시나리오를 해결하는 방법을 보여 줍니다. `examples/` 디렉터리에 포함된 샘플 HWPX 파일(`FormattingShowcase.hwpx`)을 기준으로 작성되었으며, 해당 파일은 저장소를 직접 클론했을 때만 사용할 수 있습니다. PyPI로 설치했다면 보유 중인 HWPX 문서를 사용하거나, `hwpx.templates.blank_document_bytes()`로 임시 문서를 생성해 실습하세요.

## 0. 빈 문서를 생성해 실습 환경 만들기

```python
from io import BytesIO

from hwpx import HwpxDocument
from hwpx.templates import blank_document_bytes

document = HwpxDocument.open(BytesIO(blank_document_bytes()))
document.add_paragraph("첫 문단입니다.")
document.save_to_path("playground.hwpx")
```

## 1. 보고서 템플릿에 표와 개체 추가하기

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("examples/FormattingShowcase.hwpx")
section = document.sections[-1]

# 머리글 문단을 추가하고 강조 스타일을 적용합니다.
headline = document.add_paragraph(
    "분기별 요약",
    section=section,
    style_id_ref=1,
    char_pr_id_ref=6,
)
headline.text = "분기별 실적 요약"

# 2x3 표를 생성하고 헤더 행을 병합합니다.
table = document.add_table(
    rows=2,
    cols=3,
    section=section,
    border_fill_id_ref="3",
)
table.merge_cells(0, 0, 0, 2)

# 병합된 헤더 행은 논리 좌표를 기준으로 편집할 수 있습니다.
table.set_cell_text(0, 0, "Quarter", logical=True)
table.set_cell_text(0, 1, "Actual", logical=True)
table.set_cell_text(0, 2, "Forecast", logical=True)

# iter_grid()/get_cell_map()으로 병합 구조를 확인하거나, 필요 시 병합을 해제할 수 있습니다.
header_map = table.get_cell_map()[0]
for entry in header_map:
    print(f"({entry.row}, {entry.column}) -> anchor={entry.anchor}, span={entry.span}")
# table.split_merged_cell(0, 1)  # 병합 해제가 필요하다면 사용

# 본문 행을 채우고 셀 크기를 조정합니다.
q1_label = table.cell(1, 0)
q1_label.text = "Q1"

actual_cell = table.cell(1, 1)
actual_cell.text = "42,000"
actual_cell.set_size(width=3600)

forecast_cell = table.cell(1, 2)
forecast_cell.text = "44,500"

# 강조 도형과 컨트롤을 문단으로 추가합니다.
shape = document.add_shape(
    "rect",
    section=section,
    attributes={"width": "9000", "height": "3500", "textWrap": "SQUARE"},
)
shape.set_attribute("width", "9600")

document.add_control(
    section=section,
    control_type="LINE",
    attributes={"id": "guideline-1", "type": "LINE"},
)

document.save_to_path("examples/FormattingShowcase-updated.hwpx")
```

## 2. 단락 삭제와 섹션 관리

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("examples/FormattingShowcase.hwpx")
section = document.sections[0]

# 빈 단락 제거
for para in list(section.paragraphs):
    if not para.text.strip() and len(section.paragraphs) > 1:
        para.remove()

# 새 섹션 추가 후 내용 작성
new_sec = document.add_section()
new_sec.add_paragraph("부록 A")
new_sec.add_paragraph("추가 데이터가 여기에 들어갑니다.")

print("섹션 수:", len(document.sections))

# 필요 없는 섹션 삭제
if len(document.sections) > 1:
    document.remove_section(len(document.sections) - 1)

document.save_to_path("examples/cleaned.hwpx")
```

## 3. 하이라이트와 주석을 포함한 텍스트 보고서 생성하기

```python
from hwpx.tools.text_extractor import AnnotationOptions, TextExtractor

template = "* {section}:{index} — {text}"

options = AnnotationOptions(
    highlight="markers",
    footnote="inline",
    endnote="inline",
    hyperlink="target",
    control="placeholder",
    control_placeholder="[CTRL:{name}]",
)

with TextExtractor("examples/FormattingShowcase.hwpx") as extractor:
    for paragraph in extractor.iter_document_paragraphs():
        text = paragraph.text(annotations=options)
        if not text.strip():
            continue
        print(
            template.format(
                section=paragraph.section.index,
                index=paragraph.index,
                text=text.replace("\n", " "),
            )
        )
```

`AnnotationOptions`를 활용하면 하이라이트 구간이 `[HIGHLIGHT color=#ffff00]텍스트[/HIGHLIGHT]` 형태로 출력되고, 각주와 미주 내용은 인라인으로 삽입됩니다. 하이퍼링크는 실제 URL을 포함하며, 컨트롤은 `control_placeholder` 형식에 따라 자리표시자로 치환됩니다.

## 4. 특정 태그를 검색해 요약 정보 만들기

```python
from hwpx.tools.object_finder import ObjectFinder

finder = ObjectFinder("examples/FormattingShowcase.hwpx")

# 문서 내 모든 각주 요소를 찾습니다.
notes = finder.find_all(tag="hp:footNote")
print("Found", len(notes), "footnotes")

# 책갈피 ID로 시작하는 문단만 가져옵니다.
bookmarked = finder.find_all(
    tag="hp:p",
    attrs={"id": lambda value: value.startswith("bookmark")},
)
for element in bookmarked:
    print(element.section.name, element.path)
```

`ObjectFinder`는 XPath 표현식, 태그/속성 매칭, 주석 전용 이터레이터(`iter_annotations`)를 모두 지원하므로 문서 내부 구조를 탐색하거나 특정 개체만 선별하는 자동화 스크립트를 쉽게 작성할 수 있습니다.

## 5. 선언형 document plan에서 HWPX 생성하기

```python
from hwpx import create_document_from_plan, inspect_document_authoring_quality, validate_document_plan

plan = {
    "schemaVersion": "hwpx.document_plan.v1",
    "title": "2026 AI Education Operating Plan",
    "blocks": [
        {"type": "heading", "level": 1, "text": "Executive Summary"},
        {"type": "paragraph", "text": "Agent-authored content is rendered through public python-hwpx APIs."},
        {
            "type": "table",
            "caption": "Budget",
            "columns": [
                {"key": "item", "label": "Item"},
                {"key": "amount", "label": "Amount"},
            ],
            "rows": [{"item": "AI devices", "amount": "5,000,000 KRW"}],
        },
    ],
    "qualityGates": {
        "validatePackage": True,
        "validateDocument": True,
        "reopen": True,
        "minTableCount": 1,
        "requiredText": ["Executive Summary", "Budget"],
        "visualReviewRequired": True,
    },
}

validation = validate_document_plan(plan)
if not validation.ok:
    for issue in validation.to_dict()["issues"]:
        print(issue["code"], issue["path"], issue["message"])
    raise SystemExit(1)

document = create_document_from_plan(plan)
document.save_to_path("examples/AgentDocumentPlan.hwpx")
document.close()

report = inspect_document_authoring_quality("examples/AgentDocumentPlan.hwpx", plan=plan)
print(report["pass"], report["visual_review_required"])
```

`validate_document_plan()`은 기존 문자열 `errors`/`warnings`와 함께
`issues[]`(`code`, `path`, `severity`, `suggestion`) 및 `repairHints[]`를
반환합니다. table row 오류, 알 수 없는 style token, package/schema 검증
오류가 있으면 이 필드를 기준으로 plan을 수정하고 다시 검증합니다.

운영 계획서 후보는 별도 프로필을 켜서 제출 후보로서의 결손을 확인할 수
있습니다.

```python
report = inspect_document_authoring_quality(
    "examples/AgentDocumentPlan.hwpx",
    plan=plan,
    quality_profile="operating_plan",
)
operating = report["profiles"]["operating_plan"]
print(operating["score"], operating["gaps"], operating["repair_hints"])
```

`operating-plan-quality-v1` 프로필은 앞표지/메타데이터, 필수 목차, 추진
일정표, 사업비·자원 근거, 기대 효과, 제출·확인 마감 문구, 빈칸/작성표시
잔여물을 검사합니다. 이 검사는 구조와 텍스트/표 증거 기반이며, 최종 양식
맞춤은 렌더링 또는 사람의 시각 검토가 필요합니다.

`inspect_operating_plan_quality(path).status == "ready"`는 파일 기반 품질
판정입니다. `visual_review_required`가 true이면 최종 handoff에는 열린 문서
증거가 필요합니다. 이 세 레포 스택에서는
`../hwpx-skill/scripts/visual_review.py`로 `hwpx.visual-review.v1` 증거를
기록하고 `current.status="observed_pass"`를 확인하거나, viewer가 없는
환경에서는 `blocked`로 기록해 잔여 위험을 남깁니다.

위 코드는 document-plan 품질 게이트의 핵심 흐름을 보여 주는 예시입니다.

## 6. 승인된 양식을 보존하며 채우기

이 코드는 흐름을 설명하는 schematic 예시입니다. 바로 실행하려면 사용자가
보유한 실제 승인 HWPX 양식과 그 양식에서 만든
`hwpx.template-formfit.baseline.v1` baseline JSON이 전제되어야 합니다. 로컬
quickcheck 경로가 필요하면 `hwpx-skill`의 template-formfit 예제를 참고하세요.

```python
from hwpx import analyze_template_formfit, apply_template_formfit

analysis = analyze_template_formfit(
    "template.hwpx",
    baseline="template-formfit-baseline.json",
    content={
        "school": {"name": "광교고등학교"},
        "sections": {
            "background_purpose": [
                "AI 융합형 교육실 구축으로 학생 맞춤형 탐구 수업을 확대한다.",
                "교원 공동 설계와 지역 연계를 통해 지속 가능한 운영 체계를 만든다.",
            ],
            "timeline": {
                "rows": [
                    {"월": "3월", "추진 내용": "운영 협의체 구성"},
                    {"월": "4월", "추진 내용": "공간 설계 및 기자재 선정"},
                ]
            },
        },
    },
    destination="filled.hwpx",
)

if analysis["unresolved_count"]:
    print(analysis["unresolved"])
    raise SystemExit(1)

result = apply_template_formfit(analysis=analysis, confirm=True)
assert result["handoff_status"] == "ready"
assert result["source"]["preserved"] is True
```

`analyze_template_formfit()`은 원본을 변경하지 않고, 필수 anchor가 없거나
둘 이상이면 `unresolved[]`로 막습니다. `apply_template_formfit()`은 원본과
다른 destination에 복사한 뒤 적용하며, source hash/mtime 보존과
package/schema validation, residual marker 결과를 반환합니다.
