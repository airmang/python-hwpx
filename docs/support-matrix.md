# 지원 매트릭스 (Support Matrix)

능력 영역별로 `python-hwpx` 코어가 실제로 무엇을 하는지, 그리고 그 상태가 어떤
증거에 근거하는지를 정리한다. 단순 "지원/미지원" 대신 아래 등급 어휘를 쓴다.

| 등급 | 의미 |
|---|---|
| **Parse** | 해당 요소를 읽어 구조로 노출한다. |
| **Preserve** | 손대지 않은 요소를 저장 시 바이트 그대로 보존한다(patch 경로). |
| **Edit** | 기존 요소를 편집한다. |
| **Create** | 새 요소를 밑바닥부터 생성한다. |
| **Render-verified** | 산출물이 실제 한컴 렌더 오라클로 검증됐다. |
| **Unsupported-but-preserved** | 생성·편집은 미지원이나, 기존 요소는 patch 저장 시 보존된다. |
| **Unsupported-and-rejected** | 미지원이며 입력 시 무음 처리 없이 예외로 거부한다(fail-closed). |

> **증거 축 주석.** 아래 수치는 전부 *생성물 수용률* 계열이며(동결 코퍼스 v2,
> 2026-07-19, 실한컴 12.0.0.3288 COM/GUI 오라클), 파서 프로젝트의 *파싱 recall*과는
> 다른 축이다. 상세는 [실측 코퍼스 메트릭](corpus-metrics.md) 참조.

## 매트릭스

| 능력 영역 | 상태 | 증거 |
|---|---|---|
| 문단·표 저작/편집 | Parse·Preserve·Edit·Create·Render-verified | corpus-metrics「오픈 수용률」476/476, 「저작 품질 게이트」실저작 58/58, 「렌더 검증」416건. **6.5+**: `paragraph.add_run(text, expand_special_characters=True)`가 `hp:lineBreak`(줄바꿈)·`hp:nbSpace`(비분리공백)·`hp:fwSpace`(전각공백)를 저작한다 — 실코퍼스 3파일(`error__20230818__test.hwpx`/`error__20251107__test.hwpx`/`error__20250808__...hwpx`) 리버스로 셋 다 **단일 hp:t 안의 mixed content**임을 확인(`hp:tab`이 쓰는 "hp:run 형제" 형태와 다름 — 스키마는 둘 다 허용하나 실 산출물은 이 셋에 대해 전자만 씀). 같은 리버스 과정에서 텍스트 추출기(`TextExtractor`)가 이 세 원자(+`hp:hyphen`)를 `hp:t` 중첩 위치에서 못 읽던 결함도 함께 수리 — 수리 전엔 원자가 조용히 사라지며 앞뒤 텍스트가 구분자 없이 붙어 읽혔다(줄바꿈이 있었다는 사실 자체가 유실). 실한컴 렌더 검증: `docs/openrate/report-v9.json` authored-inlineatoms 스트라텀(3원자의 0공백 순서조합 15종 전량), macOS Hancom GUI 오라클 15/15 render_checked·0 render_failed(2026-08-07 측정) |
| 표 구조 변경(행·열·표 삭제/삽입, 열 오토핏) | Preserve·Edit | `hwpx.table_patch`; corpus-metrics「바이트 보존」497/497(patch 경로) |
| 표 생성(병합·중첩 포함) | Create·Render-verified | `add_table`·`merge_cells`(피복 셀 제거+cellSpan — 실한컴 병합 의미론과 동형, 3종 병합 렌더 픽셀 확인)·셀 문단 `add_table`(중첩). 기본값은 5.4.0에서 실한컴에 맞췄다: 셀 안여백 510/510/141/141, 기본 표 폭은 본문 폭, 중첩 표는 부모 셀 사용 폭. **남은 갭**: 선 종류는 raw 전용. **6.7+**: `table.label`/`.set_label()`/`.remove_label()`(`hp:label`, Avery형 라벨시트/명패 인쇄 레이아웃) — 사설 코퍼스 75건·436건 리버스(DEV-023, 스키마와 완전 일치), 항상 표의 마지막 자식으로 배치. **Render-verified(6.8, 트레인㉘)**: openrate v11 실한컴 배치(macOS GUI 오라클) 15/15 render-checked·음성대조 3/3 — 관측 2클러스터(2×9 소형시트·1×2 대형 정사각 명패)와 관측 밖 조합(3×6 미관측 그리드·landscape=NARROWLY·partial 속성) 전부 수용, 수용 경계가 관측 분포보다 넓다 |
| 양식 채움(byte-splice) | Preserve·Edit | `hwpx.patch`·`table_patch`·`body_patch`; corpus-metrics「바이트 보존」497/497. wild 공개 양식의 서식 충실은 2차 실측 후 **산출분 pass 82.1%(23/28)·산출+fail 7.6%(5/66)** — 불가능 타깃은 typed 거부 35건(전수 감별 과잉거부 0). 잔존은 페이지 리플 5건(4건 typed 경고 동반·완전 무음 1건, 「구조결함 2차 실측」절), 표 shape 부류는 측정 인공물로 판명·판정기 교정 |
| 편집 계획 실행(edit plan) | Preserve·Edit | `hwpx.plan.apply_edit_plan`(experimental, 5.6.0+): 바이트-스플라이스 op 7종을 계획 1파일로 합성 — 정적 선검증→전 체인 인메모리 실행→최종 open-safety 검증→단 1회 원자 쓰기. 중간 실패 시 output·source 바이트 불변(테스트가 바이트 비교로 증명), step별+원본→최종 `hwpx.mutation-report/v1` 실측 사영 |
| 도형 저작(선·사각형·타원) | Parse·Preserve·Edit·Create·Render-verified | 전용 `add_line`·`add_rectangle`·`add_ellipse`. 5.0.0에서 기하 네임스페이스(`hc:`)·선 bounding box·`resize()`의 기하 반영을 수정한 뒤 실한컴 12.30.0(build 6446)에서 **개봉 7/7**(선 수평·대각·수직, 사각형, 타원, resize 후 혼합, 그림). 렌더로 사각형 144×72pt+`#CCE5FF`, 타원 100×60pt+`#FFD9CC`, 대각선이 요청 박스를 실제 span, `resize(14400,7200)` 후 새 크기·DASH 반영까지 확인 |
| 저수준 도형·컨트롤 탈출구 | Edit | `add_shape`·`add_control`은 건네받은 요소와 속성만 쓰고 OWPML 필수 하위 요소(`offset`·`orgSz`·`curSz`·`sz`·`pos`·유형별 기하)는 만들지 않는다. 그대로 저장한 문서는 실한컴 12.30.0이 **거부**한다(음성 대조로 확인). 생성 시점의 `UserWarning`은 여전히 하나뿐이지만(휘발성 — 호출 스택에만 남고 파일엔 안 남음), **6.6 트레인㉒**부터 `validate_package`·`validate_editor_open_safety`가 이 위험을 저장 이후에도 검증 결과에 명시적 `warning`으로 남긴다(fail-closed 아님 — `ok`는 그대로 `True`, 정직한 신호만 추가). `hp:container` 부재는 오탐 안 됨(부재는 이 5종을 원래 안 가짐, DEV-016). 도형은 위의 전용 헬퍼를 쓸 것(전용 헬퍼는 경고하지 않는다) |
| arc·polygon·curve·connectLine | Parse·Preserve·Create(arc·polygon, experimental)·Unsupported-but-preserved(curve·connectLine) | 전용 `add_polygon`(6.4+, `doc.shapes`): 실코퍼스(`hwpxlib_corpus/reader_writer__SimplePolygon.hwpx`) 리버스 — 꼭짓점은 `hc:pt`(core 네임스페이스, rect/ellipse와 같은 기하 네임스페이스 계약: 5.0.0 도형 네임스페이스 결함 수리와 동일 축), 자기 bbox 좌상단 원점 로컬 좌표계(정점 목록이 그 자기 `orgSz`와 정확히 일치, 실측). `resize()`는 이미 범용(`pt` 로컬명 스캔)이라 변경 없이 다각형에도 적용된다. 전용 `add_arc`(6.4+, `doc.shapes`): 실코퍼스(`SimpleArc.hwpx`) 리버스 — 스키마상 `hp:arc`는 좌표 3점(`center`/`ax1`/`ax2`)뿐 각도 필드가 아예 없다. 유일한 실 예시는 center가 자기 bbox 모서리에 앉고 ax1이 그 바로 아래, ax2가 그 바로 오른쪽인 사분원 하나뿐이라 그 한 배치만 점 단위로 실측 검증됐고, 나머지 세 모서리는 다른 모든 도형이 이미 쓰는 `hp:flip` 미러링으로 얻는다(새 점 계산 없음 — `corner` 인자, `TOP_LEFT`만 실측·나머지 3개는 유도). `arc_type`(NORMAL/PIE/CHORD)은 스키마 열거값 그대로 통과. **curve는 이번 사이클 정직 보류**: 유일한 실 예시(`SimpleCurve.hwpx`)에서 곡선의 `orgSz`가 꼭짓점(`hp:seg` 앵커점) bbox보다 뚜렷이 크다(폭 16636 vs 앵커점 bbox 15225·높이 21360 vs 20500) — 스플라인이 자기 앵커점 밖으로 부풀어 오르는 실측이며, 한컴의 정확한 곡선 적합 알고리즘 근거 없이 bbox를 추정하면 침묵 오류가 된다. **connectLine도 정직 보류**: 유일한 "Simple" 정본 예시(`SimpleConnectLine.hwpx`)는 자유선이 아니라 `subjectIDRef`로 다른 두 도형(rect·ellipse)을 잇는 "스마트 연결선"이고, `offset`이 음수(부호 없는 32비트로 직렬화된 것을 실측 확인)·`curSz`가 `orgSz`와 다르며·`scaMatrix`가 평행이동까지 얹은 비항등 행렬이라 그 관계식 근거가 없다. 다른 예시(`error__20230818__test.hwpx`, 미부착 `subjectIDRef=0`)는 파일명이 스스로 결함 사례임을 밝히고 `scaMatrix`가 e1=0인 퇴화 행렬이라 정본으로 못 쓴다. `startPt`/`endPt`가 `hp:connectLine`에서는 `hp:` 네임스페이스(`hp:line`의 `hc:startPt`와 다름, 실측 확인)라는 점만 확정 — 도형마다 기하 네임스페이스를 개별 검증해야 한다는 교훈 재확인 |
| 그룹 개체(컨테이너) | Parse·Create(experimental)·Render-verified | 전용 `add_container`(6.5+, `doc.shapes`): 실코퍼스(`hwpxlib_corpus/reader_writer__SimpleContainer.hwpx` 3부재 + 실문서 2종 71개 컨테이너, 총 74개 표본) 리버스 — 부재는 독립 도형과 완전히 같은 구조(offset/orgSz/curSz/flip/rotationInfo/renderingInfo + 도형별 기하)를 유지하되 `AbstractShapeObjectType` 꼬리(sz/pos/outMargin/shapeComment — 그룹만 가짐)는 없고 `groupLevel="1"`(그룹 자신은 `"0"`), `renderingInfo`의 `transMatrix` 이동성분이 자기 `offset`과 일치, `numberingType="PICTURE"` 전량 관측. `ContainerMember.rect`/`.ellipse`/`.polygon`으로 부재를 그룹 로컬 좌표에 배치 — **`pic`/`arc`/`line`/`connectLine`/중첩 `container` 부재와 이미 배치된 도형의 재그룹은 이번 사이클 범위 밖**(전자는 같은 패턴으로 자연 확장 가능, `pic`은 media 배선이 추가로 필요). **알려진 한계**: `resize()`는 컨테이너 자신의 크기만 갱신하고 부재를 비례 재배치하지 않는다(직속 자식 스캔이 부재 도형 전체를 보지, 그 안의 점 좌표를 안 봄) — 부재별로 개별 `resize()`를 부를 것. 실한컴 렌더 검증: `docs/openrate/report-v9.json` authored-container 스트라텀(2~4부재·rect/ellipse/polygon 슬롯별 회전), macOS Hancom GUI 오라클 15/15 render_checked·0 render_failed(2026-08-07 측정) |
| 그림 삽입/치환 | Edit·Create | `add_picture`·`add_image`·`replace_picture`. 단순 그림 개체 자동 생성은 지원하며 실한컴 개봉을 확인했다(실한컴 코퍼스와 자식 요소 단위 대조). 효과 있는 복잡 개체 생성은 미지원. 그림을 포함한 그룹 생성은 위 "그룹 개체(컨테이너)" 참조(현재 그림 부재는 미지원) |
| 차트 | Create(experimental)·Preserve | `add_chart`(5.3.0+): 데이터·계열·축 레이블에서 차트 개체를 생성한다. 기존 차트 part는 patch 저장 시 바이트 보존(497/497). 생성 어휘 밖의 차트 종류·서식은 미지원이며 기존 개체 보존으로만 다룬다 |
| 수식 | Parse·Create(experimental)·Render-verified | `add_equation`(EqEdit script 삽입, 5.2.0+)과 `hwpx.equation.latex_to_eqedit`(렌더 검증 토큰셋만 변환, 밖은 `UnsupportedLatexError`로 typed 거부). 저작 어휘 전 토큰을 실한컴 렌더 오라클 픽셀 실측(60수식 배터리)으로 확정했고, 기존 수식 개체는 파싱·patch 보존됨(미리보기 MathML 렌더는 뷰어/플러그인 계층) |
| 변경추적(redline) | Edit·Create | `add_tracked_insert`·`add_tracked_delete`·`add_tracked_replace`; 실 Windows 한컴 COM `IsTrackChange=1`·검토 리본 수락/거부 스파이크. **렌더 주의**: 한컴이 변경추적 문서의 PDF export 자체를 거부 → corpus-metrics「렌더 검증」에서 `render_unavailable`로 정직 집계(결함 아님, 한컴 제약) |
| 메모(코멘트) | Edit·Create·Render-verified | `add_memo`·`add_memo_with_anchor`; subList 코멘트 텍스트 + `MemoShapeIDRef` 버그 수정을 실 Windows 한컴에서 검증(CHANGELOG). `doc.styles.ensure_memo_shape`(6.2+)로 `hh:memoPr` 모양 정의(선 두께·색·채움색·활성색)를 새로 만들어 `add_memo(memo_shape_id_ref=)`로 바로 연결 — 이전엔 기존 문서의 memoPr에만 의존했다. 기본값은 실코퍼스(hwpxlib_corpus, 6파일) 최빈 프로파일 |
| 각주/미주 | Edit·Create·Render-verified | `add_footnote`·`add_endnote`; M6 읽기 경로에서 note 노출. 5.5.0에서 실한컴 gold 계약으로 방출 수리(본문 run 내 `hp:ctrl` 래핑·`number`/`suffixChar`·각주 본문 `autoNum`+스타일 15/16) — 옛 방출이 각주를 그리지 않던 실결함 종결, 리더는 실한컴산·구식 양형상 모두 수용(CHANGELOG [5.5.0]) |
| 네이티브 목차(TOC)/상호참조 | Create·Render-verified | `hwpx.tools.toc_author.add_native_toc`·`mark_toc_dirty`·`toc_verify`; corpus-metrics「네이티브 목차」구조 15/15, 실한컴 재계산 후 페이지 정합 5/5 |
| 암호화 HWPX | Unsupported-and-rejected | 복호화 API 없음. 암호화된 content part는 파싱 단계에서 예외(`XMLSyntaxError`)로 거부 — 무음으로 잘못된 문서를 만들지 않음(fail-closed) |
| HWP 5.x 바이너리 | Unsupported-and-rejected | HWP v5는 ZIP이 아니므로 열기 시 `BadZipFile` 예외. OLE2/CFBF 시그니처를 확인하면 예외 메시지가 HWPX 변환을 안내한다(예외 타입은 그대로) |
| 누름틀(form field) 생성 | Parse·Edit·Create(experimental) | `list_form_fields`·`fill_form_field`로 조회·서식 보존 채움에 더해, `add_form_field`(5.1.0+)가 실한컴 CLICKHERE 계약 그대로 신규 누름틀을 생성한다(표 셀 배치 포함). 만든 필드는 기존 list/fill과 실제 한컴이 특수분기 없이 소비 |
| 체크박스 양식개체 | Create·Render-verified | `add_check_box`·`list_check_boxes`·`set_check_box`(5.7.0+). 실한컴 실측 계약: `value` CHECKED=☑ / UNCHECKED=□, `<hp:formCharPr>`는 **필수 자식**(없으면 한컴이 문서를 거부하는데 우리 open-safety·ID 무결성은 통과한다 — 실한컴이 유일한 판정자다). 라디오(`hp:radioBtn`)·명령단추(`hp:btn`)는 읽기·보존만 하고 저작 API 없음 |
| 형광펜(하이라이트) | Parse·Create(experimental)·Render-verified | `doc.text.highlight`·`doc.text.highlights`(6.2+). 실코퍼스(`hwpxlib_corpus/error__20251107__test*.hwpx`)와 OWPML 스키마(`ParaList XML schema.xml`) 리버스: `markpenBegin`/`markpenEnd`는 단일 `hp:t` 안에서 위치로 짝짓는다(id 없음) — `add_tracked_delete`와 같은 단일-run 매치 제약을 그대로 따른다. 색은 `#RRGGBB` 6자리 16진만 허용(typed 거부). 실한컴 렌더 검증: `docs/openrate/report-v6.json` authored-highlight 스트라텀, macOS Hancom GUI 오라클 15/15 render_checked·0 render_failed(2026-08-06 측정) |
| 테두리 채우기(이미지·그라데이션) | Parse·Create(experimental)·Render-verified | `doc.styles.ensure_border_fill(fill_image=/fill_gradient=)`·`HwpxOxmlTable.set_cell_fill_image`/`set_cell_fill_gradient`(6.2+). 실코퍼스(`hwpxlib_corpus`, imgBrush 5파일·gradation 2파일) 리버스: `hc:fillBrush`는 `winBrush`/`imgBrush`/`gradation` 중 하나만 허용하는 선택형(Core XML schema.xml:650) — 상호 배타 typed 거부. `fill_image`는 `doc.media.add_image`가 등록한 이진 항목을 `mode`(관측 전량 `TOTAL`)로 참조하고, `fill_gradient`는 색 목록(≥2)·`type`(관측 전량 `LINEAR`)·`angle` 등을 받는다. 실한컴 렌더 검증: `docs/openrate/report-v6.json` authored-fill 스트라텀, macOS Hancom GUI 오라클 15/15 render_checked·0 render_failed(2026-08-06 측정) |
| 문서 옵션·호환성 | Parse·Preserve·Edit·Render-verified | `doc.parts.set_compatible_document_target_program`·`set_layout_compatibility_flags`·`set_doc_option_link_info`·`set_paragraph_auto_spacing`(6.6+). 읽기는 5.x부터(`hh:compatibleDocument`/`docOption`, cycle 6.1 `settings.py`/`header.py`) — 6.6이 쓰기 쪽. 실코퍼스 47/47 리버스로 계약 확정: `compatibleDocument@targetProgram`은 `"HWP201X"`만 관측·`layoutCompatibility`는 플래그 0개(스키마 48종 선언 대비)·`docOption/linkinfo`는 `path` 항상 빈 문자열·`footnoteInherit` 항상 `"0"`·`pageInherit`만 실제로 갈림(8/47 `"1"`). `hh:paraPr/hh:autoSpacing`은 `_apply_paragraph_margins`/`_apply_paragraph_line_spacing`이 이미 쓰는 자손-순회 관용구를 재사용하지만, 그 둘과 달리 실 autoSpacing은 `hp:switch`로 안 감싸인다(1832/1832 직속 자식, DEV-018과 대조 확인). 불리언은 전부 `"0"`/`"1"`(DEV-006과 같은 관례, `"true"`/`"false"` 0건). `HwpxOxmlHeader`의 owner 파일(`header_part.py`)이 1600줄 캡에 헤드룸이 없어(1599/1600) 새 모듈(`oxml/header_compat.py`)의 자유함수로 산다. 실한컴 렌더 검증: `docs/openrate/report-v10.json` authored-compat 스트라텀, macOS Hancom GUI 오라클 15/15 render_checked·0 render_failed(2026-08-07 측정) — **관측 밖 조합(targetProgram=HWP2018·실제 layoutCompatibility 플래그·footnoteInherit=1·비어있지 않은 linkinfo path) 전부 포함해서도 15/15 수용**, 즉 실한컴의 실제 수용 경계가 실코퍼스 관측 분포보다 넓다는 게 확인됐다(모든 프로브 축에서 거부 0건) |

## 6.0 표면 위치

능력 영역이 `HwpxDocument` 의 어느 자리에 사는지. 이 표는 능력 레지스트리
(`hwpx.capabilities._CAPABILITY_AREAS`)의 `namespace` 필드에서 생성되며,
`python -m hwpx.capabilities --verify` 가 그 자리가 실재하는지 검사한다.

| 능력 영역 | 6.0 위치 |
|---|---|
| 문단·표 저작/편집 | 루트 — `doc.add_paragraph` · `doc.add_heading` · `doc.add_section` |
| 표 구조 변경(행·열·표 삭제/삽입, 열 오토핏) | `doc.tables` |
| 표 생성(병합·중첩 포함) | 루트 — `doc.add_table` |
| 양식 채움(byte-splice) | `doc.tables` |
| 편집 계획 실행(edit plan) | 모듈 — `hwpx.plan` |
| 도형 저작(선·사각형·타원) | `doc.shapes` |
| 저수준 도형·컨트롤 탈출구 | `doc.shapes` |
| arc·polygon·curve·connectLine | `doc.shapes` |
| 그룹 개체(컨테이너) | `doc.shapes` |
| 그림 삽입/치환 | 루트 `doc.add_picture` + `doc.media` (이진 항목) |
| 차트 | `doc.shapes` |
| 수식 | `doc.shapes` |
| 변경추적(redline) | `doc.tracking` |
| 메모(코멘트) | `doc.notes` |
| 각주/미주 | `doc.notes` |
| 네이티브 목차(TOC)/상호참조 | `doc.refs` |
| 암호화 HWPX | 미지원 |
| HWP 5.x 바이너리 | 미지원 |
| 누름틀(form field) 생성 | `doc.fields` |
| 체크박스 양식개체 | `doc.fields` |
| 형광펜(하이라이트) | `doc.text` |
| 테두리 채우기(이미지·그라데이션) | `doc.styles` |
| 문서 옵션·호환성 | `doc.parts` |

5.x 의 옛 이름은 6.x 동안 계속 답하되 `DeprecationWarning` 을 내고 7.0 에서
사라진다 — 대응표는 `docs/migration-6.0.md`.

## 상태 판정 근거 요약

- **Render-verified**는 실제 한컴 렌더 오라클(Windows COM `SaveAs("PDF")` 또는 Mac GUI
  refresh→render)이 붙어 pass가 나온 능력에만 붙인다. 렌더를 돌리지 않았거나 한컴이
  export를 거부한 경우는 `not_performed`/`render_unavailable`로 정직 집계하고 이 등급을
  주지 않는다.
- **Preserve**는 [Safe Write Contract](safe-write-contract.md)의 `untouchedPartPayloads`
  측정에 근거한다. 손대지 않은 part는 patch 경로에서 압축 해제 페이로드가 바이트
  동일하게 유지되며, 코퍼스 v2에서 497/497로 실측됐다.
- **Unsupported-and-rejected**는 입력을 무음 처리하지 않고 예외로 거부함을 확인한
  경로에만 붙인다(암호화 content, HWP 5.x 바이너리). 두 경로 모두 실제 예외를 관찰해
  판정했다.
- **Unsupported-but-preserved**는 생성/편집 API가 없지만 기존 요소가 patch 저장에서
  보존됨을 뜻한다(차트). 새로 만들거나 편집하는 기능은 제공하지 않는다.

## 관련 문서

- [실측 코퍼스 메트릭](corpus-metrics.md) — 각 수치의 분모·판정자·측정 방법론
- [안전한 쓰기 계약](safe-write-contract.md) — 보존 등급과 `MutationReport` 영수증
