# 변경 로그

모든 중요한 변경 사항은 이 문서에 기록됩니다. 형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)과 [Semantic Versioning](https://semver.org/lang/ko/)을 따릅니다.

## [Unreleased]

### 더함

- **`HwpxOxmlParagraph.add_index_mark(first, second=)`** — 색인 표시
  (`hp:indexmark`) 저작. 실한컴 GUI 프로브 gold 2건 역설계. `add_title_mark`와
  타겟팅 계약은 같으나(호출자가 대상 문단을 직접 지정 = 편집기의 캐럿 문단)
  배치가 다르다 — titleMark는 `hp:t` **안**, indexmark는 같은 run 안의
  `hp:ctrl` 형제로 텍스트 **앞**. 스키마는 `firstKey`/`secondKey`를 둘 다
  필수 시퀀스로 선언하지만 실물은 1단계 색인에서 `secondKey`를 생략하므로
  실측을 따랐다(`add_new_num`의 `autoNumFormat` 생략과 같은 부류).
- **`HwpxOxmlParagraph.add_mail_merge_field(name, cached_text=)`** — 메일머지
  표시 필드(`hp:fieldBegin type="MAILMERGE"`) 저작. 기존
  `hwpx.tools.mail_merge.merge_template_rows`가 **기존 텍스트를 치환**하는
  Edit인 것과 달리 필드 컨트롤 자체를 만드는 Create다. 파라미터 이름
  `Fiexde`는 실물·한컴 공식 문서 공통의 오타 철자라 그대로 쓴다. 캐시 텍스트
  기본값 `{{이름}}`은 그 배치 생성기가 인식하는 플레이스홀더 문법이라 이
  필드로 저작한 템플릿이 곧바로 물린다.
- **`doc.parts.set_license_mark(...)`/`.remove_license_mark()`** — 문서 수준
  라이선스 레코드(`hh:licensemark`) 저작. "입력 > CCL 넣기…"가 남기는 그
  레코드이며, 눈에 보이는 배지는 별개(라이선스 증서 URL을 `href`로 단 그림).

### 고침

- **`LicenseMark.type`이 `int` → `str`** — 스키마(`Header XML schema.xml`의
  `DocOptionType`)가 `xs:unsignedInt use="required"`로 선언해 그대로 믿었으나
  실한컴이 실제로 쓰는 값은 문자열 `"CCL"`이다. 그래서 실한컴이 만든 CCL
  문서를 `to_model()`로 읽으면 `ValueError: Invalid integer value: 'CCL'`로
  터졌다 — 위 저작 표면을 열면서 실측으로 드러났다. `flag`/`lang`은 관측값이
  정수라 그대로다.

## [6.1.0] - 2026-08-15

15개 작업 사이클(6.1~6.15)을 하나의 트레인으로 묶어 발행한다. 완전성 감사
(2026-08-04)가 지목한 갭을 순서대로 닫아나가면서, 그 과정에서 두 개의 새
계측기(편집기 표면 인벤토리·편집기 메뉴 역방향 지도)를 만들어 남은 갭을
스스로 찾아내는 체제로 전환했다. 저작 표면 하나하나는 실코퍼스 리버스가
먼저이고, 실한컴 오라클(Windows COM 또는 macOS GUI) 렌더 검증이 뒤따르는
원칙을 전 트레인에서 유지했다 — 아래 각 항목은 그 순서를 따라 서술한다.
이 트레인은 이 브랜치가 갈라져 나온 뒤 별도로 발행된 **6.0.3의 보안 수정
(GHSA-8g8m-xpm4-wxvx, 아래 [6.0.3] 항목)을 그대로 포함한다** — 병합으로
합류했을 뿐 내용은 손대지 않았다.

### 더함

- **`doc.styles.ensure_font`** — 폰트 선언·치환 저작. 완전성 감사가 지목한
  최대 갭(#1): 모든 실문서가 `hh:fontfaces`를 갖는데도 이제까지 그 블록은
  frozen 스켈레톤 출력이었다. 언어 블록 7종을 기본 등록하고 `ensure_style`과
  같은 dedupe 관용구를 따르며, `substFont`는 실코퍼스 그대로 — 임베딩이
  아니면 `binaryItemIDRef` 속성 자체를 쓰지 않고(1682/1682 관측)
  `substFont` 값은 항상 빈 문자열(284/284), `isEmbedded`는 "0"/"1" 스펠링
  (6741 관측). `fontface` id 번호가 언어 블록마다 독립적으로 매겨진다는
  실측도 고정했다.
- **탭 정지 저작·읽기** — `apply_paragraph_format(tab_stops=...)`. 감사 갭
  #2. 스키마는 `tabPr`당 `tabItem` 최대 1개를 암시하지만 실 정부 문서는
  위치정렬 최대 4개를 한 `tabPr`에 담는다 — 코퍼스가 스키마를 이겼고
  저작은 문서를 따른다. auto-tab 불리언도 같은 "0"/"1" 스펠링.
- **`layoutCompatibility`·`compatibleDocument`·`settings.xml` 읽기 표면** —
  감사의 R1 반박(모든 실문서에 있는데도 코드가 전혀 못 읽던 `hh:
  layoutCompatibility`)을 닫는다. `settings.xml`은 벤더드 스키마 어디에도
  선언이 없어 177개 실문서로 구조를 역설계했고(`config:config-item` 어휘는
  OASIS ODF 1.0을 그대로 재사용), `layoutCompatibility`는 스키마가 48개
  플래그를 선언하지만 실문서 전부 비어 있어 관찰된 자식 이름 집합만
  보존한다. 의도적으로 읽기 전용 — 쓰기 API가 없으므로 OPC 계층의 무손실
  바이트 보존이 그대로 적용된다(3개 실픽스처로 확인).
- **도형 텍스트(draw-text)·개체 캡션** — 감사 갭 #3·#4. `.draw_text`/
  `.set_draw_text`(rect·ellipse 호스트, 스키마가 도형 개체로만 제한)와
  표·그림·도형이 공유하는 `.caption`/`.set_caption`/`.remove_caption`.
  실코퍼스는 스키마와 반대로 `shadow`가 `drawText`보다 먼저 오고, 캡션
  배치는 호스트에 관계없이 "outMargin 다음"으로 일관됐다.
- **하이라이트(형광펜)** — `doc.text.highlight`/`.highlights`.
  `markpenBegin`/`End`를 LIFO로 페어링해 `hp:t` 내부에 삽입한다. 벤더드
  코퍼스의 유일한 실 예시가 스키마상 잘못된 위치(hwpxlib 오류-회귀
  사례)이므로 그 기형 원본은 "읽기-비어있음"으로 그대로 두고 신규 저작
  경로만 정상 계약으로 검증했다.
- **이미지·그라디언트 채우기** — `ensure_border_fill`이 스키마의 `fillBrush`
  선택지(`winBrush`/`gradation`/`imgBrush`) 전부를 커버하게 됐다.
  `fill_image=`(`doc.media` 경유, 실측 전량 `TOTAL` 모드)·`fill_gradient=`
  (`LINEAR` 기본, alpha "0" 관측)가 `fill_color=`와 상호배타 옵션으로
  합류했고, 표 셀 배경 `set_cell_fill_image`/`set_cell_fill_gradient`까지
  실제 소비 경로가 이어진다.
- **메모 도형 저작** — `ensure_memo_shape`. `hh:memoPr`을 find-or-create
  dedupe로 등록한다. 실코퍼스 다수 기본값(폭 15591·SOLID·공유 3색
  프로필)을 따르고, id는 1부터 시작(`borderFill`의 0과 다름), `memoType`은
  "NOMAL" 스펠링을 스키마·실문서 그대로 유지한다.
- **페이지 번호 재시작·페이지별 요소 숨기기** — `restart_page_number`
  (`hp:newNum`)·`hide_page_elements`(`hp:pageHiding`). `newNum`은 스키마가
  요구하는 `autoNumFormat` 자식 없이 자기닫힘으로 실코퍼스 그대로
  방출한다(편차 등재).
- **위·아래 첨자 실요소, 양각·음각, 외곽선** — `ensure_run` 확장. hwpxlib
  실코퍼스(오류 문서 charPr id=513)에서 실한컴이 위첨자를 `relSz`/`offset`
  수치가 아니라 `hh:supscript` 플래그 요소만으로 판정함을 확인해, 기존
  offset 부호 계약(실한컴 렌더 검증으로 이미 확정됨)은 그대로 두고 실요소를
  병행 방출한다. emboss·engrave·outline은 스키마 근거로 추가.
- **필드 매개변수 일반 모델(`ParameterList`)·타입 있는 콤보박스
  `listItem`** — `hp:parameters`(필드 클릭 액션)와 `hp:parameterset`(도형
  확장 속성)가 스키마상 같은 재사용 타입임을 실코퍼스로 확인하고 범용
  파서·직렬화기로 승격했다(불리언·정수·실수·문자열·리스트 매개변수 재귀
  포함). 처음엔 읽기 모델만 있고 실제 문서 dispatch에 연결이 안 돼 있던
  진짜 갭이었음이 이후 사이클에서 드러나 바로 이어붙였다(아래 고침 참조).
- **`hp:compose`(글자 겹치기·원문자)·재귀 `InlineObject` 승격** —
  `ComposedCharacter`가 `GenericElement` 대신 타입 있는 필드로 노출된다.
  실코퍼스로 위치가 스키마와 다름을 확정했고(`hp:t` 자식이 아니라 `hp:run`
  직속), 컨테이너 등 내부에 중첩된 도형도 재귀 깊이와 무관하게
  `InlineObject`로 인식되도록 확장했다.
- **`doc.shapes.add_polygon`** — 다각형 저작. 실코퍼스(`hwpxlib_corpus/
  reader_writer__SimplePolygon.hwpx`) 리버스: 꼭짓점은 `hc:pt`(core
  네임스페이스, rect·ellipse와 같은 기하 네임스페이스 계약)이고 자기 bbox
  좌상단 원점 로컬 좌표계에 산다(정점 목록이 그 자기 `orgSz`와 정확히
  일치, 실측) — `points_mm`로 받은 페이지-스페이스 좌표를 그 로컬 좌표계로
  평행이동한다. 기존 `resize()`는 이미 범용(`pt` 로컬명 스캔)이라 변경
  없이 다각형에도 적용된다. curve(`hp:curve`/`hp:seg`)는 정직 보류: 유일한
  실 예시에서 곡선의 `orgSz`가 앵커점 bbox보다 뚜렷이 크다(스플라인이
  앵커점 밖으로 부풀어 오르는 실측) — 한컴의 정확한 곡선 적합 알고리즘
  근거 없이 bbox를 추정하면 침묵 오류가 되므로 미룬다.
- **`doc.shapes.add_arc`** — 사분원(호) 저작. 실코퍼스(`hwpxlib_corpus/
  reader_writer__SimpleArc.hwpx`) 리버스: 스키마상 `hp:arc`는 좌표 3점
  (`center`/`ax1`/`ax2`)뿐 각도 필드가 없다. 유일한 실 예시는 `center`가
  자기 bbox 모서리에 앉고 `ax1`이 바로 아래, `ax2`가 바로 오른쪽인 사분원
  하나뿐이라 그 배치만 점 단위로 검증됐고, 나머지 세 모서리는 다른 도형이
  이미 쓰는 `hp:flip` 미러링으로 얻는다(`corner` 인자 — `TOP_LEFT`만 실측,
  나머지 3개는 유도). `arc_type`(NORMAL/PIE/CHORD)은 스키마 열거값 그대로
  통과한다. connectLine은 정직 보류: 유일한 정본 예시(`SimpleConnectLine.
  hwpx`)는 자유선이 아니라 `subjectIDRef`로 다른 두 도형을 잇는 "스마트
  연결선"이고, `offset`이 음수·`curSz`≠`orgSz`·`scaMatrix`가 평행이동까지
  얹은 비항등 행렬이라 관계식을 재현할 근거가 없다.
- **파트 계층 읽기 모델** — `version.xml`(`HcfVersion`)·`masterpage.xml`
  (`MasterPage`)·`history.xml`(`History`) 읽기 승격(감사 갭 #15).
  `settings.xml` 관용구 그대로: `doc.parts.*`가 돌려주는 `HwpxOxml
  {Version,MasterPage,History}`에 `.to_model()` 추가. 실 산출물
  47/47(version)·다수(masterpage, 서로 다른 두 문서 계열 110건) 전수가
  벤더드 2024 초안 스키마와 루트 이름·네임스페이스가 다르다는 걸
  재확인했다(스키마가 아니라 실코퍼스가 진실 원천 — `version.xml` 루트는
  `hv:HCFVersion`이고 오탈자 `tagetApplication`을 그대로 쓴다,
  `masterpage.xml` 루트 `masterPage`는 네임스페이스가 없다). `history.xml`은
  실 예시가 하나도 없어(코퍼스+개인 실문서 6,262건 전수) 스키마 전용으로
  표기 — 평평한 리비전 메타데이터만 타입 있는 필드로 옮기고, 재귀
  중첩되는 diff 본문은 `DiffNode`로 원문 구조 그대로 보존한다.
- **그룹 개체(컨테이너) 저작** — `doc.shapes.add_container`. 실코퍼스 74개
  컨테이너(벤더드 3개 + 오류-회귀 픽스처 71개) 리버스: 멤버는 독립 도형과
  동일한 offset/orgSz/curSz/flip/renderingInfo 계약을 갖되
  `AbstractShapeObjectType` 꼬리(sz/pos/outMargin/shapeComment)를 그룹이
  대신 갖고 `groupLevel="1"`이 된다. 컨테이너 자신의 `orgSz`는 멤버들의
  합집합 bbox. 알려진 한계도 그대로 문서화했다: `resize()`가 컨테이너
  자신의 크기만 갱신하고 멤버 좌표는 안 건드린다.
- **특수 인라인 텍스트 원자(줄바꿈·전각공백·고정폭공백)** —
  `add_run(expand_special_characters=True)`. 세 마커 모두 `hp:t` 내부
  혼합 콘텐츠로 중첩되는 실코퍼스 관용구를 그대로 재현한다(스키마가
  허용하는 `hp:run` 형제 배치는 실사용 0건). 저작과 별개로 읽기 쪽 실버그도
  같은 트레인에서 발견·수리했다(아래 고침 참조).
- **`hp:switch`/`case`/`default` 읽기 모델** — 스키마 선언이 전혀 없는데도
  실코퍼스 236/237이 쓰는 버전-호환 래퍼. `paraPr`의 `margin`/`lineSpacing`이
  이 래퍼 안에 있으면 `None`으로 읽히던 실버그를 `hp:case`-우선/`hp:default`-
  폴백 읽기로 수리했다(아래 고침 참조). `tabPr` 쪽은 두 분기가 서로 다른
  값(정확히 2배 관계)을 가져 정반대로 `hp:default`를 우선해야 한다는 것도
  별도로 확정했다.
- **저수준 도형·컨트롤 이스케이프 해치의 정직한 검증 신호** —
  `add_shape`/`add_control`로 필수 자식이 빠진 도형이나 빈 `hp:ctrl`을
  만들면 실한컴이 열지 못하는데도 `validate_package`/
  `validate_editor_open_safety` 둘 다 통과시키던 갭. 경고 레벨 신호를
  추가했다(오류로 만들지 않음 — 여러 호출에 걸친 점진적 조립이라는 이
  이스케이프 해치의 문서화된 사용법을 깨지 않기 위해서다). 컨테이너
  멤버는 이 5개 자식이 없는 게 정상이라 스캔에서 제외한다.
- **문서 옵션·호환성 설정 저작** — `hh:compatibleDocument/@targetProgram`
  (실측 47/47 "HWP201X" 고정)·`layoutCompatibility` 플래그·`hh:docOption/
  linkinfo`·`hh:paraPr/autoSpacing`까지 쓰기 경로를 열었다. 모든 불리언은
  "0"/"1" 관용구(다른 OWPML 불리언 계열과 동일).
- **`hp:label`(양식 라벨·명패) 읽기+쓰기** — 개인 실문서(학교 행정서식) 75건
  리버스: 항상 `hp:tbl`의 마지막 자식, 스키마 11개 속성 전부 사용, 실측은
  정확히 2가지 조합(2×9 소형 라벨시트 325건/1×2 대형 명패 111건)으로
  수렴하지만 저작은 그 두 조합에 값을 제한하지 않는다(실증 없는 값을
  기계적으로 금지하지 않는다는 원칙).
- **문서 삽입·병합(`append_document`/`insert_document`)** — 다른 HWPX
  문서의 본문을 열린 문서에 복사하면서 헤더 소유 공유 자원(charPr/paraPr/
  style/borderFill/tabPr/numbering/bullet/memoPr/fontfaces)마다 새 대상
  id로 재매핑해, 대상이 이미 그 번호에 갖고 있던 값에 조용히 앨리어싱되지
  않도록 한다. v2에서 실측된 한컴 자신의 "문서 끼워 넣기" 4축 정책(글자
  모양·스타일·문단 모양·쪽 모양 유지)을 named parameter로 노출한다
  (기본값=v1의 이미 실한컴 검증된 동작, 비기본값은 타입 오류로 거부) —
  KeepStyle 축이 동일-이름 스타일 충돌 해소 규칙임을, KeepSection 축이
  별도 섹션 파트 생성 여부임을 실 골드 2라운드로 확정했다. MEMO 병합
  지원도 추가됐다(`hp:memogroup`이 문단이 아니라 섹션의 형제임을 확인
  후). 이 저작 표면을 만드는 과정에서 여러 실결함을 발견해 고쳤다(아래
  고침 참조).
- **덧말·글자 겹치기(`add_dutmal`/`add_composed_character`) 정식 완결** —
  구현 자체는 앞서 들어와 있었고, 이번에 capability 영역 등록·편차 등재·
  정식 테스트로 마무리했다.
- **문서정보(document metadata)** — `doc.parts.set_document_metadata`/
  `document_metadata()`. 실문서 67픽스처 전수 조사: title/creator/subject/
  keyword/lastsaveby는 요소는 있지만 대개 비어 있고, `CreatedDate`/
  `ModifiedDate`는 65/65 단일 ISO-8601 포맷(저작 대상)인 반면 자유형식
  `date` 필드는 한컴 버전·로캘에 따라 5가지 이상 서로 다른 포맷이 관측돼
  정직하게 저작을 보류한다(불투명 문자열 보존만, curve·connectLine과 같은
  원칙).
- **드롭캡** — `doc.shapes.add_drop_cap`. `dropcapstyle`이 `hh:paraPr`이
  아니라 `AbstractShapeObjectType`(모든 임베드 가능 도형의 공유 속성)에
  있다는 걸 스키마 대조로 발견했다. 67개 픽스처 중 유일한 실사용 예시
  (TripleLine)를 구조까지 리버스했고(투명 `hp:rect`가 확대 글자를 감싼
  `drawText`/`subList`, `horzRelTo=PARA`/`flowWithText=1`, `curSz`가 항상
  0/0인 센티널), DoubleLine·Margin은 표본이 없어 타입 오류로 거부한다.
- **글자 방향(세로쓰기)** — `doc.page.text_direction`/`set_text_direction`.
  `hp:secPr`의 `textDirection`(HORIZONTAL/VERTICAL/VERTICALALL)·
  `textVerticalWidthHead`를 노출한다. 67픽스처 74개 `secPr` 전부
  HORIZONTAL이라 VERTICAL 계열은 실사용 전례가 없지만, 이 프로젝트
  최초로 VERTICAL/VERTICALALL을 실제로 실한컴 렌더 검증까지 통과시켰다.
- **단 나누기** — `apply_paragraph_format(column_break=...)`. `hp:p` 자신의
  `columnBreak` 속성으로, 기존 `page_break_before`(`hh:breakSetting`이라는
  공유 스타일 속성)와는 메커니즘이 다른 별개의 문단-인스턴스 속성임을
  확인한 뒤 저작했다(실 73건 `pageBreak="1"` 계열로 동일 어휘 계약 확인).
- **표 나누기·붙이기** — `apply_table_ops`의 `split_table`·`merge_table`.
  전용 OWPML 어휘가 없어 `hp:tr`/`hp:tc`/`cellAddr`/`cellSpan` 순수 구조
  편집으로 구현했고, 병합 셀이 분할 경계를 가로지르면 실패 폐쇄로
  거부한다. 표 뒤집기는 정의가 불가능하다는 판단으로(병합 셀이 있을 때
  어느 쪽이 내용을 갖는지 정할 근거가 스키마·코퍼스 어디에도 없음) 정직
  보류한다.
- **셀 균등화(행 높이·열 너비)** — `equalize_column_widths()`/
  `equalize_row_heights()`. 이미 있던 `set_column_widths`/셀별 `set_size`를
  "균등화"라는 이름 있는 연산으로 노출했다. 병합 셀은 자신이 걸친
  행·열의 합을 받는다.
- **개요 번호매기기** — `ensure_numbering`/`apply_list_format`의 세 번째
  kind, `"outline"`. `hh:heading type="OUTLINE"`이 리스트 서식과 같은
  `hh:numbering`/`hh:paraHead` id-공간을 공유한다는 사실을 활용해 커스텀
  번호 형식·시작값을 지정할 수 있게 했다.
- **바탕쪽(master page) 쓰기 경로** — `doc.parts.add_master_page` +
  `doc.page.set_master_page`/`.master_page_refs`. 유일한 실 샘플에서 파트
  파일명·매니페스트 `opf:item` id·`masterPage` 루트 자신의 id·섹션의
  `hp:masterPage/@idRef`가 모두 같은 문자열("masterpageN")을 공유함을
  직접 확인해 재현했다. 마스터 페이지는 `opf:item`은 받지만 spine
  `itemref`는 받지 않는다(읽기-순서 파트가 아니므로).
- **날짜·교정 부호 필드** — `add_date_field(type="DATE")`·
  `add_proofreading_mark(type="PROOFREADING_MARKS_SIGN")`(DEV-043). 실한컴
  macOS GUI 프로브 골드(`date_and_proofreading_mark.hwpx`) 리버스. 스키마는
  `PROOFREADING_MARKS`를 선언하지만 실측은 열거형에 아예 없는 값
  `PROOFREADING_MARKS_SIGN`이다.
- **PATH 필드** — `add_path_field(type="PATH")`. GUI 프로브 없이 기존
  실코퍼스 샘플(파일 이름 필드, `Command=Format="$F"`)만으로 계약을
  확보했다. 이 저작을 붙이며 `fieldEnd`의 `@fieldid` 갱신 누락이라는
  실결함을 함께 발견해 DATE·교정 부호·PATH 세 필드 전부 소급 수리했다
  (아래 고침 참조).
- **titleMark(차례 숨기기·제목 차례 표시)** — `add_title_mark(*, in_toc:
  bool)`(DEV-044). macOS GUI 자동화로는 캐럿을 임의 문단에 놓을 수 없어
  한 사이클 넘게 저작이 보류돼 있었는데, Windows 박스 COM `SetPos` 3-
  variant 프로브로 캐럿-문단 타겟팅 규칙이 확정되며 열렸다. `in_toc=True`
  → `ignore="1"`, `False` → `ignore="0"`(이름의 직관과 반대인 극성을
  macOS GUI·Windows COM 양쪽에서 독립적으로 확인). 필드 래퍼가 전혀 없는
  유일한 마커 계열이라(DATE/교정 부호/PATH의 `ctrl`/`fieldBegin` 메커니즘과
  다름) 새 run을 만들지 않고 기존 run의 첫 `hp:t` 안에 바로 삽입한다.

### 고침

- **문서 병합의 `linkListIDRef` 과잉 거부 + 저장 경로 무결성 훼손** —
  `hp:subList`가 관용적으로 갖는 센티널 값("0", 벤더드 코퍼스 5,891/5,891)
  을 실제 연결된 텍스트박스 체인으로 오판해, 표를 가진 모든 문서(이
  라이브러리 자신이 생성한 문서 포함)를 병합 불가로 만들던 결함. 더
  심각한 두 번째 결함이 같은 트레인에서 함께 드러났다: 병합이 대상
  헤더 트리를 직접 변형하면서도 `target_header.mark_dirty()`를 호출하지
  않아, 그림이 껴 있지 않은 모든 병합이 메모리상 참조 무결성 검사는
  통과하면서 실제로는 손상된 파일을 저장하고 있었다(재오픈 전까지 안
  보임). 세 번째: `hp:secPr` 제거 로직이 같은 run에 얹혀 있던 표·텍스트
  까지 통째로 삭제하던 결함(빈 문서 스켈레톤으로만 테스트돼 있었다).
- **문서 병합의 `fieldEnd`/`@fieldid` 미갱신** — `hp:fieldBegin`·
  `hp:fieldEnd` 둘 다 생성 시 같은 `fieldid`를 갖지만, 병합 리프레시가
  `fieldBegin` 쪽 id/fieldid와 `fieldEnd`의 `beginIDRef`만 재발급하고
  `fieldEnd` 자신의 `fieldid`는 건드리지 않아 원본 `uuid4` 값이 복사된
  콘텐츠에 그대로 남아있던 결함. DATE·교정 부호·PATH 필드 저작에도 같은
  결함이 있어 함께 소급 수리했다.
- **문서 병합의 속성-클론 중첩 참조 앨리어싱** — `hh:paraPr` 내부 테두리의
  `borderFillIDRef`/`tabPrIDRef`, `hh:charPr`의 글자-테두리
  `borderFillIDRef`가 본문이 아니라 방금 복사된 헤더 항목 안에 살아있어
  임포트 스캔에 안 잡히던 결함(참조가 매달린 상태가 아니라서 참조
  무결성 검사도 통과했다). 무테두리 문서를 표 스타일(SOLID) 대상에
  병합하면 표지 전체가 박스로 렌더되는 것으로 실증(실한컴 A/B 대조)한
  뒤 수리했다.
- **변경추적(추적된 삽입·삭제·교체) 줄 겹침 렌더** — run 교체 경로
  (`apply_model`)가 문단의 lineseg 캐시를 지우지 않아 한컴이 옛
  줄배치를 재사용, 추가된 텍스트가 기존 줄 위에 겹쳐 렌더되던 실사용
  제보를 재현·수리했다. 실한컴 오라클로 수리 전후 렌더를 직접
  대조했다. 후속 감사로 문단 복제 경로 7종을 전수 지도화해 무방비
  2종(document-merge·공개 `insert_paragraphs`/`copy_paragraph_range`)의
  lineseg 캐시도 클론 시점에 제거하도록 정리했다(항상 새 위치의 새
  내용이므로 원본 절대좌표를 들고 있을 이유가 없다).
- **`hh:tabPr` 탭 정지가 `hp:switch`로 감싸이면 통째로 안 읽히던 결함
  (DEV-022)** — `parse_tab_definition`이 직계 자식만 스캔해 `hp:switch`
  안의 `hh:tabItem`(실코퍼스 449건)을 전부 놓치던 결함. `hp:case`/
  `hp:default` 두 분기가 실제로는 다른 값(정확히 2배 관계)을 갖는다는 걸
  확인해 `hp:default`를 우선하는 읽기 모델을 세웠다(같은 값을 공유하는
  `paraPr`의 case-우선 규칙과는 정반대). 저작 쪽의 자매 결함(`ensure_
  tab_definition`의 dedupe 비교가 같은 맹점으로 중복 `tabPr`을 만들던
  문제)도 같은 커밋에서 함께 수리했다.
- **`add_section()`이 메모가 앵커된 첫 문단에서 깨지던 결함** — `hp:secPr`
  이 항상 첫 문단의 물리적으로 첫 run에 있다고 가정하던 코드가, 메모(나
  다른 필드)가 앞에 붙으면 실제로 존재하는 `secPr`을 못 찾고 "양수 페이지
  크기를 가진 섹션이 없다"는 오류를 내던 결함.
- **`paraPr` 비중복화** — `ensure_paragraph_format`이 호출마다 동일 내용의
  `paraPr`을 새 id로 계속 발급하던 결함(실한컴은 저장 시점에 중복을 자체
  병합하지만 이 라이브러리는 하지 않고 있었다). 구조 비교 기반
  find-or-existing으로 수리했다.
- **특수 인라인 텍스트 원자 읽기 버그** — `TextExtractor`가 `lineBreak`/
  `nbSpace`/`fwSpace`를 재귀 순회에서 건너뛰기만 하고 대체 문자를 넣지
  않아, 줄바꿈이 조용히 사라지고 앞뒤 텍스트가 그대로 붙어버리던 결함.
  각 마커를 유니코드 대응(줄바꿈은 개행, 전각·고정폭 공백은 각각의
  전용 공백 문자, 하이픈은 소프트 하이픈)으로 치환하도록 고쳤다.
- **커버리지 원장(coverage ledger) 계측기 자체의 오분류 4종** — 독립
  완전성 감사(2026-08-04)가 판정한 오분류(주석·문서화 문자열을 코드로
  오인, 함수 인자로 전달된 태그를 못 따라감, 런타임 조립 마크에 근거
  없는 화이트리스트 등)를 tokenize+ast 기반 스캐너·고정점 인자 추적기·
  근거-필수 화이트리스트로 수리했다. 감사가 제시한 4개 오분류 사례 전부
  수리 전/후 재현으로 확인했다.

### 정리 (측정 인프라)

- **census 모집단 재구성** — 커버리지 원장의 census를 재현 불가능한
  옛 166파일 모집단에서 물러나, 벤더드 hwpxlib 코퍼스(47, 누구나 재현
  가능) + 관리자 개인 실문서 집계(190, 경로·이름·내용 없이 개수만) =
  237건으로 재구성했다. 두 모집단의 비대칭성을 census 문서 자체에
  명시한다.
- **편집기 표면 인벤토리(신규 계측기)** — coverage ledger가 재는 "요소
  축"과 별개로 "기능 축"(사용자가 실제로 에디터에서 클릭하는 모든
  기능)을 재는 새 문서(`docs/editor-surface-inventory.md`). capabilities
  등록 영역과 support-matrix 근거를 자동 교차해 `[엔진 상태]×[증거]×
  [실한컴 검증]`을 도출한다. 이 인벤토리 자체가 자기 스캔으로 8개
  실동작·미등록 기능(`doc.page`의 19개 메서드 전체 등)을 찾아냈고, 사이클
  진행에 따라 미실측 행을 하나씩 닫아 이번 릴리스 시점에는 구조적으로
  검증 불가능한 `shape-escape-hatch` 한 줄만 남았다(실한컴이 설계상 그
  입력을 거부하므로 "렌더 검증"이라는 개념 자체가 성립하지 않는다).
- **편집기 메뉴 역방향 지도(신규 계측기)** — "한컴 메뉴 항목 → 우리 엔진
  대응"이라는 반대 방향 질문에 답하는 새 문서(`docs/editor-menu-reverse-
  map.md`). macOS 9개 메뉴 128개 항목을 전수 판정했다([대응 영역]/
  [부분 대응]/[대응 없음=신규 갭]/[스코프 밖]/[미확인]). 여기서 나온
  "대응 없음" 목록이 이번 릴리스의 신규 저작 표면(문서정보·드롭캡·
  글자방향·단나누기·표나누기/붙이기·개요·바탕쪽·날짜/교정/PATH 필드·
  titleMark 등) 대다수의 최초 입력이 됐다.
- **openrate 코퍼스 v5~v21** — 사이클마다 새로 연 저작 표면을 실한컴
  오라클로(초기엔 Windows COM, v6부터는 macOS GUI) 배치 측정하는 시리즈를
  17회 더 이어갔다. 매 배치마다 결정론(독립 재생성 2회 바이트 동일)·
  정적 오픈-세이프티 사전필터·부정 대조군 거부를 확인했고, 6.11 사이클
  종료 시점에 인벤토리의 미실측 행을 한 차례 0으로 닫았다(이후 신규
  저작마다 다시 쌓이고 다시 닫히는 순환이 이어졌다).
- **편차 등재 DEV-002~044** — 스키마-대-실측 괴리를 재실행 가능한
  프로브와 함께 43건 추가 기록했다(예: `tabItem` 카디널리티, connectLine의
  `subjectIDRef`가 `id`가 아닌 `instid`로 해석되는 점, `hp:label`의 실측
  2-클러스터 수렴, `hp:switch`/`case`/`default`의 스키마 완전 부재,
  titleMark가 스키마에는 선언돼 있으나 문서화가 전무한 점). 별도로,
  이전 조사 회차에서 미병합 상태로 남아 있던 편차 16건도 재검증을 거쳐
  정식 등재했다.

## [6.0.3] - 2026-08-11

### 보안

- **신뢰할 수 없는 HWPX를 읽을 때의 자원 고갈을 수정합니다(GHSA-8g8m-xpm4-wxvx, HIGH).**
  405 KB짜리 조작 파일 하나로 `HwpxDocument.open()`이 830 MB를 할당할 수 있었고,
  비율은 공격자가 정합니다. 원인은 두 가지였습니다 — 멤버를 읽는 대부분의 경로가
  `guard_zip_file()`을 아예 호출하지 않았고, 가드가 도는 자리에서도 중앙 디렉터리에
  적힌 크기만 검사해 실제 할당량을 제한하지 못했습니다.
  - `read_member()`/`read_zip_members()`를 도입해 적힌 크기가 아니라 **실제로 읽힌
    바이트**를 64 KB 단위로 세며 한도를 넘으면 중단합니다. 이제 할당량이 저장량이
    아니라 선언 크기에 비례합니다.
  - 압축 데이터가 적힌 크기보다 큰 멤버(위조 크기), 데이터를 실은 디렉터리 엔트리,
    드라이브 경로(`C:/`·`D:\`·`//server/share`), STORED·DEFLATED 외 압축 방식
    (bzip2·lzma는 CPython이 청크 읽기로 bound하지 못함)을 거부합니다.
  - 패치 계열·아카이브 CLI·진단 도구 등 신뢰할 수 없는 아카이브를 읽는 모든 경로가
    첫 멤버를 읽기 전에 `guard_zip_file()`을 통과하도록 배선했습니다.
- **동작 변경**: 위 경로들에는 지금까지 크기 제한이 없었습니다. 그래서
  `HwpxDocument.open()`이 이미 거부하던 문서(멤버 128 MB 초과, 멤버 4096개 초과,
  압축비 1000:1 초과)가 이제 `paragraph_patch()`·`hwpx-unpack` 등에서도 거부됩니다.
  128 MB가 넘는 동영상·이미지를 담은 문서를 다루던 사용자는 영향을 받을 수 있으며,
  `guard_zip_file(limits=...)`로 조정할 수 있습니다.
- 신고 및 수정: [@Nekonic](https://github.com/Nekonic).

## [6.0.2] - 2026-08-04

`v6.0.1`도 보존된 실패 태그입니다 — 아무것도 게시되지 않았습니다. prepublish의
mypy 게이트가 Q3b 구역 서식 setter의 루프 변수 재사용 타입 충돌 4건을 적발해
업로드 전에 중단했습니다(로컬 태그-전 점검이 core에서 타입체커를 생략한 것이
원인 — 체크리스트에 core mypy+pyright를 명문화). 변수 분리로 고친 동일 내용이
6.0.2입니다. 삭제·이동·재사용하지 않습니다.

## [6.0.1] - 2026-08-04 (preserved failed tag — nothing published)

`v6.0.0`은 보존된 실패 태그입니다 — 아무것도 게시되지 않았습니다. prepublish의
공개 위생 게이트가 이번 트레인 신규 파일 3개(코퍼스 v4 생성기·왕복 하니스·
감사 판정문)에 유입된 내부 작업 코드네임을 적발해 업로드 전에 트레인을
중단했습니다. 코드네임을 공개 서술로 치환하고 동결 인벤토리를 75→74로 전진
(6.0 표면 재편으로 삭제된 파일의 역사 항목 1건 소멸)한 동일 내용이
6.0.1입니다. 삭제·이동·재사용하지 않습니다.

## [6.0.0] - 2026-08-04 (preserved failed tag — nothing published)

엔진 완전성 트레인의 major 경계입니다 — 표면을 도메인 네임스페이스로 재편하고,
완전성을 측정할 구조물(커버리지 원장·편차 레지스트리·왕복 하니스·코퍼스 v4)을
세웁니다. 독립 감사 판정: "완전성에 도달한 버전"이 아니라 "완전성을 측정하고
채워 나갈 구조물"이 정확한 서사입니다(`docs/2026-08-04-completeness-audit-verdict.md`).

### 바뀜 (파괴적 — major 근거)

- **루트 표면 102 → 34.** 이동한 79개 이름은 도메인 네임스페이스로:
  `doc.notes`(각주·미주·메모) · `doc.fields`(누름틀·체크박스·하이퍼링크) ·
  `doc.shapes`(도형·그림·수식·차트) · `doc.styles`(문자·문단 서식, 스타일) ·
  `doc.page`(용지·구역) · `doc.tracking`(변경추적) · `doc.text`(검색·치환) ·
  `doc.toc` · `doc.plan` · `doc.media` · `doc.parts`. 5.x 루트 이름 전부가
  행선지를 안내하는 `DeprecationWarning` shim으로 7.0까지 동작합니다.
- **반환 규약 단일화**: 저작 메서드는 라이브 도메인 객체를, 결과 페이로드는
  `frozen dataclass`(+`to_dict()`)를 반환합니다 — dict/tuple/스칼라 반환 0.
- **typed error**: 공개 경로 100%가 kebab `code`를 가진
  `HwpxValueError/TypeError/LookupError/StateError`로 던집니다(기존 builtin
  except 절과 이중상속 호환). 스타일 이름 오타는 호출 시점에
  `style-not-found`(+근접 제안)로, 없는 숫자 id도 저장 전에 거부됩니다.

### 추가됨

- `add_paragraph(style="개요 1")` 스타일 **이름** 해석과 `add_heading(level=)`
  (styleIDRef + `hh:heading` OUTLINE 이중 방출).
- Q3b 요소 개방: `pageBorderFill`(BOTH/EVEN/ODD 질의·저작),
  footnote/endnote 모양 5블록 부분 갱신, `ensure_style`(이름 기반 신규 스타일),
  `set_visibility`/`set_line_numbers`/`set_grid`.
- **커버리지 원장**(`docs/coverage-ledger.md`, 345 요소 기계 재산출 —
  ⚠알려진 측정 오차 절 필독) · **OWPML 편차 레지스트리** 17항목
  (`specs/063-owpml-deviations/`) · 왕복 충실도 하니스 · 코퍼스 v4
  (실한컴 12.0.0.3288에서 170/170 개봉·170/170 렌더 검증,
  `docs/openrate/report-v4.json`).
- 실측 비교표 `docs/comparison-python-docx.md`(대조군 리플렉션 실측,
  지는 칸 5행 포함) · 이주 가이드 `docs/migration-6.0.md` ·
  문서 예제 자립 실행 71/117.

### 제거 예고

- legacy shim 79종과 `section_index=` 파라미터는 **7.0.0에서 제거**됩니다.
  `python -m hwpx.capabilities`의 `surfaceShape`가 shim 수와 제거 시점을
  기계 판독 가능하게 노출합니다.

## [5.8.0] - 2026-08-03

정직성 트레인입니다 — 새 저작 표면 없이, 라이브러리가 하는 말을 전부 참으로
되돌립니다.

### 고쳐짐 (영수증 무결성)

- `SavePipeline`의 레이아웃 게이트가 꺼져 있거나 내부 예외로 못 돌았을 때
  `passed`를 돌려주던 것을 중단합니다. `LayoutReport`에 명시적
  `status`(`passed`/`warned`/`failed`/`unverified`)와 `unverified_reason`이
  추가되어, 끈 게이트·터진 게이트·진짜 통과가 영수증에서 구분됩니다.
  `ok`의 의미(저장 차단 여부)는 그대로라 동작은 바뀌지 않습니다.
- ID/참조 무결성 검사가 내부 예외를 삼킨 채 통과로 남던 것을 수리했습니다.
  `require_reference_integrity=True`인데 검사가 실행되지 못하면 이제
  실패입니다 — "확인 못 했음"을 "확인했고 정상"으로 세탁하지 않습니다.
- `paragraph_patch`가 전량 폐기된 편집을 `applied`에 싣던 것을 수리했습니다.
  이 계열은 all-or-nothing이므로, 매칭됐지만 버려진 편집은 신설된
  `discarded`로 보고되고 `applied`는 비웁니다. `output_path`가 원본 바이트
  사본을 받는 문서화된 경우는 신설 `outputIsSourceCopy`가 명시합니다(두 키
  모두 additive, 기본값 빈/false).

### 고쳐짐 (자기서술)

- 동봉 지원 매트릭스가 이미 출하된 기능을 부정하던 3곳을 정정했습니다:
  차트("생성 API 없음" → `add_chart`는 5.3.0부터 실재), 표 기본값("수리
  예정" → 5.4.0에서 수리 완료), 체크박스(행 부재 → 실한컴 계약과 함께 신설).
  이 문서는 휠에 동봉되고 MCP 리소스로 서빙되므로, 이를 읽는 에이전트가
  실재하는 기능을 회피하고 있었습니다.
- 능력 레지스트리 드리프트 가드를 문서↔문서 대조에서 **레지스트리↔실코드**
  대조로 뒤집었습니다. `HwpxDocument`의 모든 `add_*` 메서드는 정확히 한 능력
  영역에 귀속되어야 하며, 등재 없이는 새 저작 메서드를 출하할 수 없습니다
  (직전 릴리스에서 체크박스가 양쪽 문서에 다 없어 옛 가드를 통과한 실패의
  구조적 차단).

### 추가됨

- `hwpx.capabilities.verify_self_description()`과
  `python -m hwpx.capabilities --verify` — 설치된 휠에서 자기서술이 실표면과
  일치하는지 누구나 직접 검사할 수 있습니다. 선언 대신 검증기를 동봉합니다.
- 실측 코퍼스 v3 발행: 현행 스택이 만든 120문서(기준 스트라텀 + 각주·누름틀·
  수식·차트·체크박스·편집계획 6표면)를 실한컴 12.0.0.3288이 전건 개봉·렌더
  (120/120, rule-of-three 하한 97.5%). 영수증(`docs/openrate/verdicts_v3.jsonl`)
  은 행마다 `bucket`을 가져 분모 분해가 `jq` 한 줄로 재현됩니다. 축소 범위
  (497 전수 아님)는 매트릭스·README에 명시합니다.

### 문서

- README 헤드라인 수치에 측정 스택·일자를 병기합니다(측정 없는 "continuously
  verified" 문구 폐기).
- NOTICE에 한컴 파일 형식 공개 문서가 요구하는 고지 문구를 원문 그대로
  추가했습니다. 낡은 사내 라이선스 메타데이터 정책 문서(재라이선스 이전
  잔재)를 제거했습니다.

## [5.7.0] - 2026-08-03

### 추가
- **체크박스 양식개체 저작**(experimental): `add_check_box(caption, checked=…)`
  ·`list_check_boxes()`·`set_check_box(checked, index=|name=)`. 방출 형상은
  실한컴 실측 계약을 따릅니다 — `value="CHECKED"`가 ☑, `UNCHECKED`가 □로
  그려지고 caption은 렌더 텍스트 레이어에 나옵니다. **`<hp:formCharPr>`는
  필수 자식**이며(없으면 한컴이 문서를 거부합니다 — 단일 변인 프로브로 확정)
  `<hp:checkBtn>`은 누름틀과 달리 `<hp:ctrl>` 래핑 없이 run 직속입니다.
  표 셀 안 배치도 지원하며, 선택자 없는/모호한 `set_check_box`와 빈 caption은
  typed 거부입니다.

  참고: 한국 정부 공문서 서식은 이 양식개체가 아니라 텍스트 `[ ]`+√ 관례를
  규정합니다(시행규칙 별표 4 제10호). 이 프리미티브는 실제로 한컴 체크박스를
  쓰는 서식용입니다.

## [5.6.0] - 2026-08-03

### 추가
- **`hwpx.plan` 편집 계획 실행기** (experimental): 바이트-스플라이스 편집 op
  7종(`paragraph_patch`·`fill_cells`·`apply_table_ops`·`apply_body_ops`·
  `recolor_runs_by_color`·`strip_runs_by_color`·`strip_trailing_table_captions`)
  을 선언적 계획 1파일(`hwpx.edit-plan/v1`)로 합성해 *정적 선검증 → 전 체인
  인메모리 실행 → 최종 open-safety 검증 → 단 1회 원자 쓰기*로 실행합니다.
  중간 step이 실패하면 output·source가 바이트 불변임이 테스트로 증명되는
  all-or-nothing 계약이며, 결과는 step별 + 원본→최종 실측
  `hwpx.mutation-report/v1` 사영을 실은 `hwpx.plan-report/v1`입니다.
  dryRun은 동일 체인을 전부 실행하되 쓰기만 생략하고, `journalPath` 지정 시
  JSONL 저널(진단용, resume 계약 아님)을 남깁니다.
- **`hwpx.capabilities` 기계가독 자기서술** (experimental):
  `describe_capabilities()`가 설치 버전·extras 실측 프로브·라이브 표면
  census(stable/experimental)·편집 계획 op 어휘·능력 영역 레지스트리를
  보고합니다. `contract_document()`는 패키지 동봉 계약 문서 4종
  (support-matrix·recipes-traversal·mutation-semantics·known-traps 신규 저작)
  을, `contract_json_schema()`는 계약 JSON Schema 4종(edit-plan·plan-report·
  mutation-report·capabilities)을 서빙합니다. 드리프트 가드 테스트가
  레지스트리 진입점 해석·op 어휘 3자 일치·support-matrix 행 대조를
  강제합니다(core는 렌더 오라클 가용성을 주장하지 않습니다 — 그 보고는
  automation 계층 소유).

### 수정
- **support-matrix 각주/미주 행의 낡은 서술 정정**: 5.5.0이 각주 방출 계약을
  수리하고도 매트릭스 행은 `Render-unverified·honest-defer`(2026-08-01 문구)
  로 남아 출하됐습니다. 행을 실상태(Render-verified, 5.5.0 수리 근거)로
  갱신했고, 같은 부류의 드리프트를 `hwpx.capabilities` 가드 테스트가 이제
  구조적으로 막습니다. `docs/stable-api.md`의 experimental 목록도 5.2.0 수식
  3종 누락을 함께 정정(12→23).

## [5.5.0] - 2026-08-02

### 수정
- **각주/미주가 실한컴에서 렌더되도록 방출 계약 수리** (실한컴 gold
  리버스): 각주는 본문 run 안 `<hp:ctrl>` 래핑으로 삽입되고 `number`(유형별
  연속 번호)·`suffixChar`를 실으며, 각주 본문 문단은 각주/미주 스타일
  (헤더 이름 조회, 기본 15/16·paraPr 10·charPr 3)과 선행
  `<hp:autoNum>`(FOOTNOTE/ENDNOTE)을 갖습니다 — 기존 방출(run 직속·번호
  없음)은 실한컴이 각주를 그리지 않던 실결함(감사 실결함 3번). 리더
  (markdown [^fn] 부록·텍스트 추출 주석)는 실한컴 ctrl-래핑 형상과 구식
  자사 형상을 모두 읽습니다 — 실한컴산 문서의 진짜 각주를 그동안 리더가
  놓치고 있던 갭도 함께 수리. `note.text` setter는 gold 본문(autoNum·
  스타일)을 보존합니다.

## [5.4.0] - 2026-08-01

### 추가
- **`ensure_border_fill(border_type=…)`**: OWPML 선 종류 어휘(SOLID·DASH·
  DOT·DASH_DOT 등)를 검증해 테두리 모양을 지정합니다. 어휘 밖 값은 typed
  거부(ValueError).
- **`HwpxOxmlTable.set_cell_border_fill(row, col, border_fill_id_ref)`**:
  개별 셀의 테두리/배경 참조를 교체하는 표면(저작 충실도 감사에서 확인된
  B 표면갭 수리).
- **`ensure_run_style` 확장 7종**: `underline_shape`/`underline_color`(물결
  등 밑줄 모양·색), `strike_shape`(취소선 모양), `ratio`(장평 10–400),
  `letter_spacing`(자간 −50–100), `shadow`(그림자 색), `script`(`sup`/`sub`
  위·아래 첨자 — 실한컴 계약 relSz 67·offset ±30). 전부 감사에서 실한컴
  렌더로 검증된 charPr 자식 어휘이며, 범위·어휘 밖 값은 typed 거부.

### 수정
- **`add_hyperlink` 표시 텍스트가 실한컴 관례를 따름**: 파랑(#0000FF)
  텍스트 + 파랑 BOTTOM 밑줄(실코퍼스 하이퍼링크 최빈 서식). 서식은 표시
  런에만 실리며(fieldBegin/fieldEnd 런은 주변 서식 유지 — gold 계약)
  다음 문단으로 전염되지 않습니다. `char_pr_id_ref=`로 override 가능.
- **첨자 offset 부호 정정**: 실한컴 렌더 실측 결과 offset 양수=아래·
  음수=위 — `script="sup"`가 위로, `"sub"`가 아래로 정확히 그려지도록
  부호를 맞췄습니다.
- **밑줄 type 어휘 gold 일치**: `underline=True`가 방출하던
  `type="SOLID"`(비표준)를 실한컴 관례 위치 어휘 `BOTTOM`으로 수정.

### 변경
- **`add_table` 기본값이 실한컴 계약과 일치**: 셀 안여백 기본
  510/510/141/141(기존 0 — 한컴에서 만든 표와 여백이 달랐음), 기본 표
  폭은 본문 폭(용지 − 여백)으로, 셀 안에 만드는 중첩 표는 부모 셀 사용
  폭에 맞춤(기존 고정 7200/셀 기본값이 부모 셀보다 넓어 내용이 소리 없이
  잘려 보이던 감사 실결함 수리). 명시 `width=` 지정 시 동작 불변.
- **목록 문단 비상속**: 글머리표/번호 문단 뒤에 `add_paragraph`로 추가하는
  일반 문단이 목록 paraPr를 상속하지 않습니다(실한컴에서 프로그램적 추가
  문단은 본문 — 감사에서 모든 후속 문단이 목록화되던 실결함 수리). 명시
  `para_pr_id_ref` 지정 시 목록 계속 사용 가능.

## [5.3.0] - 2026-07-31

### 추가
- **차트 저작 `HwpxDocument.add_chart`** (experimental 계약): ECMA-376
  chartML(`c:chartSpace`)을 `Chart/chartN.xml` 파트로 저장하고 실한컴
  `<hp:chart chartIDRef=…>` 앵커를 방출합니다 — 실한컴 계약 그대로 파트는
  어느 manifest에도 등록하지 않으며(실측), 한컴은 chartML만으로 차트를
  그립니다(OLE 폴백·사전렌더 이미지 불요, 실한컴 렌더 픽셀 실측: 막대·
  꺾은선·원). chartML은 파싱·루트 검증 후에만 기록(typed 거부), 표 셀
  배치·인라인 배치 지원, 생성 직후 표준 섹션 스캔 재인식 실패 시 즉시
  실패합니다. 기존 차트 파트와의 경로 충돌 없이 순차 할당하며 무관 파트는
  바이트 보존됩니다.

## [5.2.0] - 2026-07-31

### 추가
- **수식 저작 `HwpxDocument.add_equation`** (experimental 계약): 실한컴이
  만드는 `<hp:equation>` 형상 그대로(EqEdit script는 `<hp:script>` 자식,
  `treatAsChar="1"` 인라인, lineseg 캐시 없이 — 한컴이 열 때 재조판) 수식을
  삽입합니다. 표 셀 내부 삽입을 지원하고, 생성 직후 표준 섹션 스캔으로
  재인식되지 않으면 즉시 실패합니다(특수분기 0). 계약은 실한컴 gold
  리버스(수식 계약 문서) 기준입니다.
- **LaTeX → EqEdit 변환기 `hwpx.equation.latex_to_eqedit`** (experimental):
  리더 방향(EqEdit → LaTeX)과 같은 토큰맵의 역방향입니다. 분수·근호/n제곱근·
  첨자·그리스·관계/이항연산·합/적분/극한 상하한·행렬(`pmatrix` 계열·`cases`)·
  `\left`/`\right`·accent·`\text` 리터럴·예약어 따옴표 보호(`T_{int}` →
  `T _{"int"}`)를 지원하며, **검증된 토큰셋 밖의 LaTeX는
  `UnsupportedLatexError`로 typed 거부**합니다(무음 근사 없음). 왕복
  property 테스트가 저작 EqEdit를 기존 리더로 복원해 고정점을 증명합니다.
  `estimate_equation_size` 휴리스틱이 `<hp:sz>` 자리표시 크기를 계산합니다
  (한컴이 열 때 실측 재계산).

## [5.1.1]

`v5.1.0`은 보존된 실패 태그입니다 — 아무것도 게시되지 않았습니다. 태그
워크플로의 공개 위생 게이트가 실한컴 gold 픽스처 2종의 OPF 메타데이터에
남은 사적 출처 마커(creator/lastsaveby)를 적발해 중단했고, 마커를 제거한
동일 내용이 5.1.1로 복구되었습니다. `v5.1.0`은 삭제·이동·재사용하지 않습니다.

## [5.1.0]

### 추가
- **누름틀 필드 저작 `HwpxDocument.add_form_field`** (experimental 계약):
  실한컴이 만드는 CLICKHERE 형상 그대로(필드 속성·`Prop`/`Command`/
  `Direction`/`HelpState` 파라미터·화면 전용 안내문 런·`fieldEnd` 쌍) 필드를
  생성합니다. 안내문 길이 직렬화는 문자 수 기준이며, 만든 필드는 기존
  `list_form_fields`/`fill_form_field`가 특수분기 없이 그대로 소비하고 실제
  한컴오피스가 열거·채움을 수행합니다(실한컴 gold pair 리버스 계약). 표 셀
  내부(중첩 포함) 삽입을 지원합니다.
- **필드 페이로드 확장**: `list_form_fields` 결과에 `memo`(HelpState)·
  `dirty`·`is_placeholder`가 추가되고, 실한컴 파라미터 이름
  `Direction`/`HelpState`가 `prompt`/`memo`로 매핑됩니다. `dirty != "1"`인
  동안 보이는 값은 사용자 값이 아니라 안내문입니다.

### 수정
- **채움이 한컴과 같은 흔적을 남깁니다**: `fill_form_field`가 값 기록 시
  `dirty="1"`을 설정하고, 안내문(placeholder) 상태의 필드를 채울 때 안내문
  전용 스타일(빨강·이탤릭)을 주변 스타일로 교체합니다. 종전에는 값이 안내문
  스타일을 그대로 물려받아 빨간 이탤릭으로 남는 무음 시각 결함이 있었습니다.

## [5.0.2]

### 수정
- **첫 실행이 조용해졌습니다**: 기본 템플릿으로 `new()`→`save_to_path()`만
  해도 `manifest에서 masterPage/history/version …` 경고가 15줄 출력되던 문제를
  고쳤습니다. 빈 문서에 masterPage/history가 없는 것과 version.xml이
  manifest 선언 없이 고정 경로에 있는 것은 실제 한컴 산출물과 동일한 정상
  상태입니다(실한컴 gold fixture 6종 대조로 확인). 이제 manifest가 실재
  파일을 놓친 경우에만 경고하며, 반환값은 변하지 않습니다.
- **릴리스 해시 검증기가 태그에서 버전을 유도합니다**: 종전에는 PyPI 조회
  URL의 버전이 스크립트 상수로 고정되어, v5.0.1 릴리스에서 존재할 수 없는
  5.0.0 JSON을 조회하다 404로 빨간 표시를 냈습니다(아티팩트는 건전, 독립
  readback으로 종결했던 그 건입니다). 이제 `--tag`에서 버전을 유도하고,
  매니페스트 파일명이 태그 버전을 담는지 교차 검증하며, 인덱스 전파 지연
  대비 재시도 예산을 60초에서 300초로 늘렸습니다.

### 추가
- **5분 퀵스타트 개편**: 읽기(텍스트 추출)와 저장 영수증(`MutationReport`)
  단계를 추가하고, 편집 예제를 복붙만으로 이어지는 완결 스크립트로
  재구성했습니다. 문서 예제 ledger 재생성 스크립트
  (`scripts/regenerate_example_ledger.py`)도 함께 추가했습니다.
- **과업 축 매뉴얼 2종**: [순회 레시피](docs/recipes-traversal.md)(문단·중첩
  표·각주·런·메모/누름틀)와 [편집 의미론](docs/mutation-semantics.md)(반환형·
  실패 모드·재실행 성질·저장 보증 — 전부 실측 확인) — 실행 ledger 게이트에
  편입.
- **llms.txt 발행**: 훈련 데이터에 이 라이브러리가 없는 AI 도구가 정확한
  API를 배우도록 `https://airmang.github.io/python-hwpx/llms.txt`(+ 매뉴얼
  병합본 `llms-full.txt`, 빌드 시 자동 생성)를 사이트 루트에 제공합니다.
  내용 계약은 테스트로 고정(버전 문자열 금지 포함).
- **채택·응답 지표 공개**: [채택 지표 페이지](docs/adoption-metrics.md)와
  기계 판독 이력(`adoption-metrics-history.json`, 사이트 루트)을 추가했습니다.
  수집은 `scripts/snapshot_adoption_metrics.py`(멱등 — 같은 날 재실행은
  교체)이며, 각 지표에 "이 숫자가 말해주지 않는 것" 캐비앗을 함께 둡니다.
- **Python 3.13·3.14 공식 지원**: CI 매트릭스와 trove classifier에 3.13/3.14를
  추가했습니다(전체 스위트 1376 passed를 양 버전에서 확인한 뒤 반영).
  지원 정책은 [설치 가이드](docs/installation.md)에 명문화했습니다.

## [5.0.1]

`v5.0.0` is a preserved failed tag: its release run stopped in prepublish
(the installed-wheel docs gate requires `uv`, which the workflow never
installed) and nothing was published to PyPI or GitHub. 5.0.1 is the same
train content plus the workflow fixes — `uv` is now bootstrapped in both
the test and release jobs, and the test job's `tee` pipe no longer masks
pytest's exit code. Never delete, move, or reuse `v5.0.0`.

## [5.0.0]

### Removed — BREAKING

`python-hwpx` is now the HWPX object model, OPC/OXML, and the format-native
primitives built on them. The application workflows that had grown inside the
library moved to `python-hwpx-automation`, which has owned their canonical
implementation since the 4.x line. **Nothing is discontinued** — every removed
import has a named replacement in
[the migration guide](docs/migration-5.0.md), and 4.x keeps all of it.

- `hwpx.agent` and the `hwpx` console command → `hwpx_automation.office.agent`.
  The automation package declares the `hwpx` name in the train that raises its core floor to 5.0,
  so no valid install ever has two declarers of it.
- `hwpx.authoring`, `hwpx.builder`, `hwpx.design`, `hwpx.presets` →
  `hwpx_automation.office.authoring`
- `hwpx.exam` → `hwpx_automation.office.exam`
- `hwpx.evalplan_fill` → `hwpx_automation.office.evalplan`
- `hwpx.form_fill`, `hwpx.formfill_quality`, `hwpx.fill_residue`,
  `hwpx.guidance_scan`, `hwpx.template_formfit` →
  `hwpx_automation.office.form_fill`
- `hwpx.tools.official_lint`, `hwpx.tools.pii`, `hwpx.tools.table_compute`,
  `hwpx.tools.style_profile`, `hwpx.tools.advanced_generators`,
  `hwpx.tools.report_parser` → `hwpx_automation.office.compliance` /
  `office.quality` / `office.utilities` / `office.authoring`
- `hwpx.tools.mail_merge.mail_merge` → `merge_template_rows`, which is now
  public. The removed wrapper masked by default and core no longer carries the
  detection rules; the generic function takes a `value_sanitizer` so the caller
  decides, and the decision is visible at the call site instead of implied by an
  omitted argument.
- `hwpx.tools.doc_diff.build_comparison_table_plan` →
  `hwpx_automation.office.document_ops`. Generic diff and reference-consistency
  stay here.
- The four `template_formfit` names that 4.x warned would go "in the next major"
  are gone. That was this major.
- `hwpx-conformance` console script: its package is repository QA and no longer
  ships, and a command that cannot start is worse than no command.

### Changed

- `HwpxDocument.add_table()` now creates a neutral table-anchor paragraph by
  default, so a preceding numbered heading/list no longer renders a stray
  number beside the table in Hancom. Pass `inherit_style=True` or explicit
  paragraph/style references when anchor-style inheritance is intentional.
- `HwpxDocument.add_tracked_replace()` now writes the inserted replacement at
  the deleted text's source position, preserves that run's character style,
  and leaves later tracked inserts in their original order.
- The product-boundary lazy-loader fingerprint now canonicalizes parser-only
  empty AST fields, so the same guarded source passes consistently on Python
  3.10–3.13 while real syntax changes still fail closed.
- `verify_redline` and `verify_fill` take an injected
  `hwpx.quality.rendering.RenderBackend`. Core does not look for a Hancom
  installation any more; without a backend the report is
  `render_checked=False` rather than a visual verdict it never earned.
- `toc_fidelity.heading_rendered_pages` takes a word-box extractor, and
  `heading_pages_from_word_boxes` is public for callers that already have boxes.
  Reading a PDF needs an imaging stack; matching headings does not.
- `hwpx.oxml.color.color_family` is public. Both core's run rewriting and the
  application-side guidance scanner classify colour the same way, so there is
  one implementation of what counts as red.

### Packaging

- `hwpx.benchmark` and `hwpx.conformance` are excluded from the wheel. They are
  things this project runs on itself, not things a library user installs.
- The fuzz harness moved to `scripts/fuzz/`, outside the package, because it
  builds documents through the MCP owner's builder and core must never import a
  companion layer.

### Migration

`pip install python-hwpx-automation` and follow [docs/migration-5.0.md](docs/migration-5.0.md).
`pip install "python-hwpx<5"` rolls back; the 4.x line is not a dead end.


### Documentation
- 4.x compatibility/deprecation 관찰 정책을 공개했습니다. 8개 runtime family,
  3개 CLI, 공개 스키마/리포트 projection은 2026-10-31까지 모두 `extend`하며
  제거는 0건입니다. 신규 코드를 위한 MCP canonical 경로, side-by-side 이행,
  rollback, 별도 next-major 승인 조건을
  [4.x 호환 표면 관찰 정책](docs/compatibility-observation-4.x.md)에 기록했습니다.

## [4.2.0] - 2026-07-22

### Added — 평가계획(교수학습운영·평가계획) 실채움 엔진 확장
- `fill_evalplan`에 `phase="clean"`을 추가했습니다 — 기존 `"all"`(채움) 뒤에 core의
  결정론적 양식 정리(제목·교사·정의적 표 채움, 양식 지시문·외래 샘플 소제목·고아
  헤딩 prune, 빨강 지시 run 제거, 슬롯-파랑→본문 검정 재색, 표 꼬리 캡션 strip)를
  한 경로로 수행해, 별도 정리 스크립트 없이 실제 도교육청 양식을 잔존물 없이
  채웁니다. 기본값 `"all"`은 기존 동작 그대로입니다(비파괴).
- `finalize_evalplan`(위 정리 오케스트레이션)과 프리미티브 2종
  (`table_patch.strip_trailing_table_captions`, `guidance_scan.is_form_instruction`)을
  추가했습니다. 전부 패턴·구조 기반이며 과목·학년 문자열 하드코딩이 없습니다.

### Fixed — 평가계획 표 파싱·채움
- 성취기준별 §4가 성취수준 표(A~E 또는 상/중/하)를 파싱·채우지 못하던 문제를
  고쳤습니다. 콘텐츠의 성취수준 단계 수를 읽어 표 구조에 맞춰 채웁니다.
- 도너 스케줄 표의 병합이 일부 주차 행을 흡수하던 문제를 고쳤습니다(병합 분리).
- §7 수행평가 세부기준 상세 배점 루브릭(평가요소·수행수준·배점, 세부 영역 가/나/다)을
  파싱·채우도록 확장했습니다.

## [4.1.1] - 2026-07-21

### Fixed
- 4.1.0 태그의 발행이 공개 위생 게이트(워크스테이션 경로 검사)에 걸려 중단됐습니다
  — 내부 개발용 rhwp 트리아지 스크립트가 공개 레포에 포함돼 있었고, 해당 도구는
  공개 표면이 아니므로 저장소에서 제거했습니다. 라이브러리 코드는 4.1.0과
  동일합니다. (`v4.1.0`은 보존된 실패 태그이며 PyPI 산출물이 없습니다.)

## [4.1.0] - 2026-07-21

### Fixed — form-fill 차등 판정기 교정 (verify 신호 신뢰성)
- `hwpx.form_fit.wordbox`의 표 구조 지문(`extract_layout_signature`)과 overflow
  클립(`extract_cell_clips`)이 fitz `find_tables()` 기본 전략(글리프 스냅) 대신
  **그려진 테두리 전용**(`lines_strict`)을 쓰도록 교정했습니다. 종전에는 빈 셀을
  채우면 그려진 격자가 그대로인데도 유령 표·허위 overflow가 검출되어
  `verify_form_fill` 계열 게이트가 허위 실패를 냈습니다. wild 코퍼스 실측:
  허위 shape 실패 6건·허위 overflow 3건 해소, 회귀 0, 산출분 pass 17/28→23/28.
  **제품 산출물(채움 바이트)은 변경되지 않았습니다** — 판정만 정확해졌습니다.

### Docs — 정직 실측 갱신
- [실측 코퍼스 메트릭](docs/corpus-metrics.md)에 「구조결함 2차 실측」 추가:
  잔존은 페이지 리플 5건(4건 typed 경고 동반·완전 무음 1건)이며, typed 거부
  35건 전수 감별 결과 과잉거부 0. 지원 매트릭스 양식 채움 행 동기화.

## [4.0.0] - 2026-07-21

### Removed — deprecation window 준수 정리 (major 경계)
- **`HwpxDocument.save()` 제거**: v2.6(2026-02-19)부터 5개월간 `DeprecationWarning`을
  달고 있던 호환 래퍼를 제거했습니다. 목적지별 명시 메서드를 쓰세요 —
  경로 `save_to_path(path)` · 스트림 `save_to_stream(stream)` · 바이트 `to_bytes()`.
  이 셋은 [안전한 쓰기 계약](docs/safe-write-contract.md)(`mode`/`fallback` 등급 +
  `return_report`)을 지원하며, 제거된 `save()`에는 없던 기능입니다.
- `hwpx.package` 모듈(→`hwpx.opc.package`)은 경고 이력이 있지만 stable
  `HwpxPackage`의 역사적 import 경로라 **유지**합니다(shim, 비용 0). 전체 표·이유는
  [4.0.0 마이그레이션](docs/migration-4.0.md).

### Added — 구조화 예외 베이스 (오류 계약 통일)
- `hwpx.errors.HwpxError`(최상위 `hwpx.HwpxError`로도 import) 도입 — fail-closed 공개
  경로 예외의 베이스. 사람용 `str(exc)`는 그대로 두고 기계가 읽는 `code`(kebab
  안정 식별자)·`context`(실측 값 dict)·`suggestion`(다음 행동)을 얹으며 `to_dict()`로
  봉투를 냅니다. **공개 계약 경로부터** 이행: `PreservationDowngradeError`
  (`preservation-downgrade`), 신규 `SaveError`(대표 저장 경로의 사전검증·open-safety·
  품질 게이트 실패), `TableStructureError`(`table-structure`),
  `RenderCheckRequired`(`render-check-required`). 기존 `except`
  타입(`ValueError`/`RuntimeError`/`Exception`)은 상속으로 그대로 동작합니다.
  전체 표는 [stable-api.md 오류 계약](docs/stable-api.md).
- `HwpxError`가 stable 표면에 추가되어 `hwpx.__all__`은 **stable 67개**가 됩니다.

### Changed — 스키마 동결 + mutation 반환형 통일
- **스키마 동결**: `hwpx.mutation-report/v1`·`hwpx.document_plan.v1`/`v2`·
  `hwpx.agent-batch/v1`·`hwpx.mixed-form-plan/v1`의 required 필드 집합을 동결하고
  계약 테스트(`tests/test_schema_freeze.py`)로 고정했습니다. 정책은 additive-only —
  신규 필드는 Optional, 파괴 변경은 새 major + 새 스키마 버전 문자열
  ([schema-freeze.md](docs/schema-freeze.md)).
- **mutation 반환형 통일**: 공개 mutation-write 경로가 전부 `hwpx.mutation-report/v1`로
  사영 가능함을 계약 테스트(`tests/test_mutation_contract_unification.py`)로 고정
  했습니다(byte-write 결과모델 4종 + 네이티브 `save_to_path` 영수증). 사영 없는 신규
  byte-write 모델이 추가되면 구조 가드가 실패합니다.
- `save_to_path`/`save_to_stream`/`to_bytes` 이름을 **장기 확정**으로 명문화(개명 재론
  종결, [safe-write-contract.md](docs/safe-write-contract.md)).

### Changed — 최상위 API 표면 3계층화 (major 경계 준비)
- `from hwpx import ...` 표면을 **stable / experimental / deprecated** 3계층으로
  분류했습니다. `hwpx.__all__`에는 **stable 67개만** 남깁니다(P1의 66 + P2 `HwpxError`).
  계층·정책 전수 목록은 `docs/stable-api.md`.
- **experimental(12)** — ingestion 프레임워크·레이아웃 프리뷰·문서 프리뷰 뷰어.
  `from hwpx.experimental import ...`로 사용하세요. 최상위 재내보내기는 하위 호환을
  위해 유지하되 접근 시 `DeprecationWarning`이 나며 다음 major에서 최상위 경로가
  제거될 예정입니다(구현 모듈·`hwpx.experimental` 경로는 유지).
- **deprecated(4)** — `analyze_template_formfit`/`apply_template_formfit`와
  `TEMPLATE_FORMFIT_*_SCHEMA_VERSION` 상수 2개. 대체 = 구조적 form-fill 경로
  (`hwpx.table_patch.fill_cells` 계열 + MCP `analyze_form_fill`/`apply_form_fill`/
  `verify_form_fill`).
- **최상위에서 제거된 이름 0개**: 기존 최상위 이름 82개는 전부 계속 import 가능합니다
  (최소 deprecation window 준수 — 경고 없는 즉시 제거 금지). `HwpxDocument.save()`는
  최상위 표면 이름이 아니라 메서드로, 위 Removed 절에 따라 제거됐습니다.

## [3.8.0] - 2026-07-21

### Added — 문서 프리뷰 뷰어
- `render_document_viewer`: 한컴 없이 문서를 **스크롤 통독**하는 self-contained
  HTML 뷰어(상단바·현재 페이지 표시·키보드 탐색·외부 리소스 0). 충실도 배지가
  한계를 정직하게 표시합니다(텍스트 근사·페이지네이션은 한컴과 다를 수 있음).
- **수식 실제 렌더**: `hwpx.equation` — `<hp:equation>`의 EqEdit 스크립트를
  clean-room 토큰맵으로 LaTeX로 변환해 MathML로 렌더합니다(선택 extra
  `python-hwpx[preview]` = latex2mathml). 실한컴 ground-truth와 시각 대조로
  검증(specs 증거). 변환 불가/라이브러리 부재 시 **빈칸 대신** 원문·LaTeX
  코드블록으로 정직 표시하고, 그림·도형은 자리표시 마커로 보입니다 — 기존
  프리뷰가 수식을 조용히 빈 문단으로 떨구던 동작은 제거됐습니다.

### Internal
- MCP 경계 타이핑 정밀화를 위한 evalplan 경로 Path/str 유니온(순수 어노테이션).
- 복잡도 3물결: 최상위 15개 함수 분해(C901 115→100), characterization 39건 추가.


## [3.7.0] - 2026-07-21

### Added — Safe Write Contract
- 일반 저장 경로가 **명시적 쓰기 모드**를 받습니다:
  `save_to_path(path, mode="patch"|"rebuild"|"auto", fallback="error"|"rebuild",
  return_report=True)`. 반환 기본값은 기존과 동일(경로)이며 `return_report=True`
  일 때만 스키마버전드 **`hwpx.mutation-report/v1`** 영수증을 반환합니다 —
  요청/실제 모드, 변경 part 목록(+가능한 경우 실제 범위, coordinate space 명시),
  보존 보증 3계층(미수정 part payload / zip local record / whole package),
  수행한 검증의 3값 기록(passed/failed/not_performed).
- **무음 강등 없음**: `mode="patch"`에서 요청 보존 등급을 만족하지 못하면
  출력 파일을 쓰지 않고 typed `PreservationDowngradeError`를 던집니다.
  `fallback="rebuild"`로 명시 동의한 경우에만 진행하며 영수증에
  `fallbackUsed: true`가 남습니다. 보존은 단언이 아니라 **open-시점 기준선
  대비 실측**입니다(발행 성공 시 기준선 전진).
- 기존 쓰기 결과 4종(BytePreservingPatchResult·CellFillResult·BodyOpsResult·
  AgentBatchResult)에 `as_mutation_report()` 사영 추가 — byte-splice 계열은
  `source=`(bytes/str/Path) 제공 시 보존 3계층과 실제 스플라이스 범위를
  실측 보고, 미제공 시 정직 강등. 기존 필드·to_dict 출력은 불변(additive).

### Docs
- README 포지셔닝 개정(§안전 자동화 계층+검증된 저작), **지원 매트릭스**
  공개(docs/support-matrix.md — Parse/Preserve/Edit/Create/Render-verified/
  Unsupported-but-preserved/Unsupported-and-rejected, 셀별 증거 링크),
  docs/safe-write-contract.md 신설, 헤드라인 지표에 corpus·분모·측정일·
  assurance 병기(오픈 수용률 하한 표기를 rule-of-three 99.37%로 정밀화).


## [3.6.0] - 2026-07-20

### Fixed
- **양식 채움 무음 서식파괴의 지배 원인 픽스**: fit 슬롯이 셀 안 인라인
  treat-as-char 객체(체크박스·폼컨트롤·그림)의 선언 폭(`hp:sz/@width`)을
  가용폭에서 차감합니다. 이전에는 이를 비모델링해 "맞음"으로 오판한 채움이
  실한컴에서 줄바꿈·행 성장을 일으켜 다중 페이지 양식 전체를 밀었습니다
  (실측: 3글자 채움이 10페이지 양식을 11페이지로). 이제 그런 채움은 **typed
  FIELD_OVERFLOW 거부**(컨트롤 동거 경고 포함)가 됩니다. 실한컴 재측정에서
  판정 조합 전체의 무음 서식파괴가 47%→16.7%로 감소했습니다.
- 레이아웃 캐시 무효화를 편집 스코프로 축소: 편집한 문단의 캐시만 제거하고
  저장 시 전량 제거(2개 레이어) 대신 증명 가능한 stale만 걷어냅니다. 채움
  바이트 델타가 −133,651자에서 −170자로 줄어 바이트 보존 계열과 정합합니다.

### Added
- `SlotMetrics.inline_object_width`/`inline_object_count` — 슬롯 진단 표면.


## [3.5.0] - 2026-07-20

### Added
- 양식 채움 fit 판정에 **수직(행 높이) 예산**을 도입합니다. 이전에는 셀의 가로
  폭만 측정해 세로로 100줄까지 "맞음"으로 판정, 축소도 거부도 발동하지 않고 행이
  조용히 자라 페이지를 밀었습니다. 이제 `available_height`(셀 높이 − 상하 마진)와
  글꼴별 라인하이트로 세로 예산을 재서, `wrap_then_shrink`는 값을 예산 안으로
  축소하고, 최소 글꼴에서도 안 들어가는 과대 입력은 `overflow="fail"`에서 **typed
  거부**(FIELD_OVERFLOW)로 돌려줍니다. `allow_row_expand`/`expand_row`는 명시적
  opt-out입니다. `FitPolicy.keep()`과 폭-only 경로는 바이트 불변입니다.

### Measured (정직 발견)
- wild 공개 양식 전수 재측정(실한컴): 양식 채움 차등이 fit-on 32/63 = 50.8%
  (fit-off 31/63 = 49.2%). 기대-통과 층(short+medium)은 61.4%로 **이동 없음** —
  fit은 wild 실패의 지배 레버가 아니며, 지배 원인은 구조적 3부류(채움-겹침·다중
  페이지 경계 밀림·표 구조 민감도)임이 측정됐습니다. 상세는 `docs/corpus-metrics.md`
  및 leap 데모 `demo/S-085-wild-formfill/`.


## [3.4.1] - 2026-07-19

### Note
- 복구 릴리스. `v3.4.0` 태그는 prepublish 공개 위생 게이트에서 실패했고
  (테스트 픽스처의 워크스테이션형 경로 문자열 — `/home/...` 패턴), PyPI
  아티팩트나 GitHub Release는 만들어지지 않았습니다. 실패 태그는 이력으로
  보존하며 3.4.1이 실제 공개 릴리스입니다. 기능 내용은 아래 3.4.0 항목과
  동일합니다.

## [3.4.0] - 2026-07-19 (tag preserved; not published)

### Added
- 선언형 문서 계획(plan-v2)에 네이티브 자동 목차 옵션(`native: true`)을 추가합니다.
  정적 목차를 내려쓴 뒤 한컴이 열기 시점에 재계산하는 TABLEOFCONTENTS 필드로
  승격하며, 본문 스타일 수집 가드(바탕글-수집 함정)를 포함합니다.
- M9 출판 코퍼스 도구를 추가합니다: 코퍼스 v2 additive 생성기, 무인 실한컴 박스
  판정(오픈/파싱·스케일 렌더 배치·redline InitScan 프로브), 축별 검증 드라이버
  (byte-identity·PII 0-leak·저작 품질·양식 채움 차등·TOC 검증)와 결합 집계기
  (provenance 이중 발행·redline-aware parsed·렌더 티어).
- 실측 결과를 문서로 발행합니다: `docs/corpus-metrics.md`(축 주석 포함)와
  릴리스별 기계 판독 히스토리 `docs/corpus-metrics-history.json`.

### Fixed
- 오픈레이트 박스 러너의 재개 키를 basename에서 전체 경로로 바꿔, 중복 파일명을
  가진 코퍼스에서 파일이 조용히 건너뛰어지던 문제를 고칩니다.
- Windows PowerShell 5.1에서 렌더 잡 배열이 1개 객체로 접히던 열거 함정을 고칩니다.

### Internal
- `HwpxDocument` facade를 도메인 owner 8모듈로 행동 보존 분해합니다
  (2,961→1,777줄; 공개 표면 97멤버 characterization 스냅샷으로 동결).
- 복잡도 상위 함수 5종+1을 분해해 C901 초과를 120→114로 낮추고, owner 모듈을
  mypy/pyright 점진 게이트에 편입합니다(40파일 clean).


## [3.3.1] - 2026-07-18

### Internal
- 최악 복잡도 검증기 2종을 행동 보존 분해합니다:
  `validate_blueprint_manifest`(C901 60→1, 헬퍼 14개)와
  `validate_package`(53→10, 헬퍼 12개). 에러 문자열·검사 순서·manifest 불변성은
  기준선과 verbatim 동일하며 테스트 델타 0으로 실증했습니다.
- 공개 표면·계약 변화는 없습니다. S-083 릴리스 트레인(hwpx-mcp-server 4.3.0 ·
  hwpx-plugin 0.6.0)과 좌표를 맞추는 릴리스입니다.

## [3.3.0] - 2026-07-18

### 추가
- 선택적 Mac GUI 오라클(`MacHancomOracle`)에 도달성 프로브를 추가했습니다. 한컴 앱이
  설치돼 있어도 GUI 세션·Automation(TCC) 권한이 없으면 5초 이내에 `available() == False`로
  정직하게 강등되며(프로세스 수명 캐시), 기존 구조 검증 경로가 그대로 동작합니다.
- 렌더 오라클에 단일 외부 예산 전파를 추가했습니다. `budget_seconds`(생성자·
  `resolve_oracle`)가 지정되면 내부의 모든 subprocess 타임아웃이 남은 예산으로
  clamp되고, 예산 소진 시 subprocess를 생성하지 않고 즉시 강등합니다.
- `HWPX_ORACLE_STRUCTURAL_ONLY` 환경변수를 추가했습니다. 설정 시 `resolve_oracle()`은
  `NullOracle`을 반환하고 Mac GUI 백엔드는 어떤 경로로도 GUI 자동화에 진입하지
  않습니다(구조 판정 전용 모드).
- `HWPX_ORACLE_BUDGET_SECONDS` 환경변수를 추가했습니다. 호스팅 프로세스가 한 번
  선언한 외부 deadline이 `resolve_oracle()`의 모든 호출 지점(코어 verify·MCP 핸들러)에
  자동 전파됩니다. 명시적 `budget_seconds` 파라미터가 env보다 우선합니다.

### 변경
- `src/hwpx/visual/oracle.py`를 mypy·pyright 점진적 게이트에 편입하고 기존 타입 오류
  2건(textLength 협소화, 검증 항목 변수 재사용)을 수정했습니다.

## [3.2.0] - 2026-07-17

### 추가
- 기존 섹션 머리글을 네이티브 ID 또는 페이지 유형으로 지정해 본문·표 셀과 같은
  `hwpx.agent-batch/v1` 트랜잭션에서 편집하는 타입드 story 경로를 추가했습니다. dry-run,
  revision 및 idempotency 검사, 오류 시 rollback, 저장 후 story identity·구조 보존 확인을
  동일한 단일 직렬화 경로에서 수행합니다.

### 변경
- 비대해진 OXML 문서 구현을 문서 프리미티브, 패키지/구역 관리, 구역 서식과 story 등
  책임별 런타임 모듈로 분리했습니다. 기존 공개 facade와 import 경로는 유지하면서 수정된
  소유 모듈 전부를 Ruff·mypy·pyright 점진적 게이트에 포함했습니다.

### 수정
- `add_section()`이 인접 구역의 렌더 가능한 페이지·단 설정을 복제하되 머리글·바닥글
  story는 복제하지 않고, manifest/spine 순서와 `hh:head/@secCnt`를 함께 갱신하도록
  수정했습니다. 음수 `after` 인덱스, 범위 오류, 불완전 패키지, 상대 manifest href를
  원자적으로 처리하며 `remove_section()`과 패키지 열기 안전성 검증도 같은 구역 수
  불변식을 확인합니다.

### 검증
- 2개 구역 합성 fixture의 결정적 재생성, 저장·재열기, 패키지 바이트 보존, 오류 주입
  rollback 및 한컴오피스 2/2쪽·2/2구역 경고 없는 열기 회귀를 고정했습니다.

## [3.1.0] - 2026-07-16

### 추가
- **타입드 혼합 양식 계획기**: `hwpx.mixed-form-plan/v1`이 네이티브 필드, 고유 라벨 셀,
  revision-bound canonical path, 본문 직접 단일-run anchor를 하나의 엄격한 계획으로 받습니다.
  모든 대상을 먼저 canonical path로 해석한 뒤 기존 `hwpx.agent-batch/v1` 한 건으로 컴파일하며,
  `apply_document_commands`만 실행기로 사용해 dry-run·rollback·idempotency·단일 저장 게이트를
  그대로 보장합니다.
- 병합 셀의 논리 좌표를 실제 `cellAddr` 앵커로 정규화하는 비변형 `resolve_cell_target` 계획
  프리미티브와 공개 plan/compiled-plan JSON Schema를 추가했습니다.

### 변경
- 에이전트 batch JSON Schema를 정본 카탈로그에 추가하고 quality 객체의 enum·boolean 필드를
  엄격하게 검증해 알 수 없는 값이 실행 단계까지 전달되지 않도록 했습니다.
- 혼합 양식 출력이 입력과 동일한 resolved path·symlink·hardlink인 경우 계획과 적용 직전에
  거부하고, 셀 라벨은 정규화된 정확 일치만 허용합니다. 컴파일 계획은 locator별 node/path/
  section/좌표 불변식을 검증하며, 멱등성 식별자에 공개 locator 요청 hash를 포함합니다.

### 검증
- 합성 1쪽 한국어 혼합 양식으로 네 locator 동시 적용, 드라이런 무출력, 주입 실패 rollback,
  idempotent replay/conflict, 미변경 OPC member 바이트 보존, 재열기와 `openSafety.ok`를 고정했습니다.
  `evalplan` 회귀는 유지하며 `exam` 모듈은 혼합 양식 경로에 가져오지 않습니다.

## [3.0.0] - 2026-07-16

### 변경
- 공개 배포에서 내부 품질 검증용 `hwpx.practice` 런타임과 관련 Python API를 제거했습니다.
  문서 작성·편집·검증, 시험지, 평가계획, 범용 양식 채움 기능과 공개 conformance 흐름은
  그대로 유지됩니다.

### 수정
- 높이가 서로 다른 물리 행을 삭제할 때 병합 셀 높이를 평균값으로 줄이던 문제를 수정했습니다.
  이제 삭제 행의 실제 최대 높이를 사용해 평가계획 표를 다시 배치해도 병합 높이 합과 한컴
  편집기 열기 안전성이 유지됩니다.

### 보안
- 소스·wheel·sdist·import 표면에 내부 품질 검증 런타임이 다시 포함되지 않도록 공개 위생과
  패키징 회귀 게이트를 추가했습니다.

## [2.29.2] - 2026-07-15

### 수정
- 공개 저장소의 운영 기록·생성 산출물·workstation 경로를 제거하고, 실제 회귀 입력은 명시적인
  합성 fixture 디렉터리로 이동했습니다. 패키지에 포함되는 HWPX 예제와 conformance corpus의
  작성자 메타데이터도 합성 값으로 정규화했습니다.
- 치명적 정적 오류를 차단하는 Ruff `E9,F` 및 텍스트/HWPX/wheel 공개 위생 게이트를 추가하고,
  기존에 이름이 겹쳐 실행되지 않던 builder 회귀 테스트를 고유 이름으로 복구했습니다.

### 보안
- GitHub Actions를 불변 커밋으로 고정하고 CodeQL, dependency review, Dependabot, CycloneDX SBOM,
  SECURITY/CODEOWNERS 정책을 릴리스 표면에 추가했습니다.

## [2.29.1] - 2026-07-15

### 수정
- 릴리스 prepublish가 시각 fixture 테스트를 실행하면서도 Pillow와 NumPy를 설치하지 않아
  `v2.29.0` 태그의 게시 작업이 중단된 문제를 수정했습니다. `test` extra에 두 의존성을 포함해
  clean CI에서도 동일한 테스트 계약을 결정적으로 재현합니다.

### 비고
- `v2.29.0` 태그는 prepublish 실패 이력으로 보존되며 PyPI 패키지와 GitHub Release는 생성되지
  않았습니다. 기능 내용은 아래 2.29.0 항목과 동일하고, 실제 공개 패키지는 2.29.1입니다.

## [2.29.0] - 2026-07-15

### 추가
- **타입드 에이전트 문서 인터페이스와 블루프린트 재생**: 안정적인 semantic path/query, revision-bound
  atomic command, 통합 `hwpx` CLI, deterministic `.hwpxbp` dump와 strict portable/source-bound replay를
  추가했습니다. 스타일·번호·리소스·참조는 typed semantic signature로 매핑하고, raw XML 없이
  fidelity/identity/dependency/lossless/openSafety 영수증을 반환합니다.
- **내구성 렌더·시각 QA**: supervised Hancom render worker, resumable queue/poison-session 처리와
  fixture 기반 page QA·blind evaluation 계약을 추가했습니다.

### 수정
- 블루프린트 replay가 병합 표 grid와 한컴 네이티브 control을 보존하도록 보강했습니다.
- 공개 2.24.1의 안전 동작을 유지해, 실제로 변경된 비어 있지 않은 `lineWrap="SQUEEZE"` 셀만
  `BREAK`로 전환하고 no-op·지우기·미편집 셀은 원래 모드를 보존합니다.

### 비고
- 2.25.0–2.28.0은 공개 배포가 아니라 단계별 로컬 후보였으며, 그 누적 변경을 이 2.29.0 공개
  항목으로 통합합니다.

## [2.24.1] - 2026-07-14
### 수정
- 표 셀의 `lineWrap="SQUEEZE"`가 긴 신규 값을 한 줄 폭에 강제 압축해 글자가 포개지던 문제를 수정했습니다. 바이트보존 `fill_cells`/`apply_table_ops(fill_cell)`와 일반 `set_cell_text` 모두 실제로 변경된 비어 있지 않은 셀만 `BREAK`로 전환하고, 미편집 셀·no-op·지우기 작업의 원래 모드는 보존합니다.

## [2.24.0] - 2026-07-08
### 추가
- **Stage 3 범용 form-fill 프리미티브 (universal form-fill goal)**: 임의 양식을 제출본급으로 채우는 동적 파이프라인의 손. `hwpx.guidance_scan.scan_form_guidance`(비변형 정찰: 셀·캡션 포함 색 신호/범례/placeholder/빈 셀 후보). `hwpx.body_patch`(표 밖 문단 바이트보존 op: replace_text·delete_paragraph·insert_paragraph_by_clone·reorder_paragraphs·restyle_text·set_paragraph_text + 문서전체 `strip_runs_by_color`(범례 "이 색=삭제" 구동)·`recolor_runs_by_color`(슬롯색→본문색)). `hwpx.table_patch` 신규 op: `split_cell_vertical`(병합 셀 N그룹 분할)·`clone_table`(표 복제)·`set_row_heights`·`set_cell_line_spacing` + `apply_table_ops(dry_run=)` transcript. `hwpx.fill_residue.inspect_fill_residue`(채움본 잔존물 zero-체크 게이트).
### 비고
- 평가계획 3학년 실양식을 처음부터 끝까지(삭제·재구성·채움·청소·recolor) 범용 프리미티브만으로 완성, 실한컴 렌더 + 오너 실물 검수 PASS로 검증(도메인 전용 코드 0줄).


## [2.23.0] - 2026-07-03
### 추가
- **폰트 shrink-to-fit (M10 후속, S-064)**: `hwpx.table_patch.fill_cells`에 `fit_max_lines`(+ 셀별 `max_lines`) — 셀 텍스트가 템플릿 폰트로 목표 줄수를 넘겨 wrap되면 `form_fit` FitEngine이 확신을 갖고 들어가는 가장 큰 폰트(≥ `min_font_pt`)를 골라 **실제 `<hh:charPr>`로 재료화**(base charPr 복제·height 변경)하고 셀 run을 그 charPr로 재지정. byte-preserving(header.xml의 새 charPr + 해당 섹션만 변경, opt-in이라 목표 없는 채움은 바이트 동일). FitEngine 정직 게이트가 borderline shrink는 거부(확실히 들어갈 때만 축소).
### 비고
- 오라클 실증: 실제 3학년 양식 성취기준 셀을 긴 텍스트 + `max_lines=4`로 채우니 9pt→6.5pt 축소, 실한컴 clean 렌더(나머지 표는 9pt 유지). 정직: 도교육청 폼은 base 9pt라 축소 여지(→8pt)가 작아 `autofit_columns`(가로)가 주력이고 폰트 축소는 보조; base 폰트 큰 폼엔 효과적. README 3스택 정비(python-hwpx 425→171·mcp 599→184·skill 471→178줄) 동반.

## [2.22.0] - 2026-07-03
### 추가
- **열 너비 조정 (M10 후속, S-064)**: `hwpx.table_patch.apply_table_ops` 새 op 2종 — `set_column_widths(table_index, widths)`(명시적 논리 열너비; 각 셀 cellSz.width = 걸친 열들의 합, 병합 인식)·`autofit_columns(table_index)`(내용에 맞춰 열너비 재균형: demand = 최장 단일-span 셀 텍스트폭[`form_fit` 어드밴스 모델], sqrt-damped로 문단 열 폭주 방지, 열별 최소폭 floor, 표 총폭 보존). 둘 다 **byte-preserving**(cellSz만 편집, charPr/header 불변)이며 grid 검증. 배경: 텍스트가 길어지면 한컴이 행 높이를 자동으로 늘려 넘침은 없으나 좁은 열은 촘촘히 wrap됨 — autofit이 내용 많은 열을 넓혀 완화한다(오라클 실증: 운영계획 성취기준 열 14186→16441, wrap 약 16→9줄, 총폭 보존).

## [2.21.0] - 2026-07-03
### 추가
- **M10 바이트보존 구조적 양식채움 (S-064)**: `hwpx.table_patch` — 2026-07-03 실전 실패(도교육청 평가계획 양식을 재생성으로 채워 서식 파괴)를 드라이버로, S-052 바이트 코어 위에 "양식 채움 층"을 완성. `fill_cells(source, cells)` — `(table_index, row, col)` 주소로 셀 텍스트를 바이트보존 splice(빈/self-closing 셀 삽입, 다중 문단 셀 전체 교체, 병합 앵커 해석). 미변경 셀·표·섹션은 **바이트 동일**(원칙 VII), no-op=바이트동일, 미해결 주소는 mutate 없이 `skipped`.
- **표 구조 프리미티브** `apply_table_ops(source, ops)`: `delete_column`(자유폭 재분배 + 열삭제로 빈 행 생기면 캐스케이드 삭제·rowSpan 붕괴)·`delete_row`·`delete_table`·`insert_row_by_clone`(rowSpan==1 참조행 복제, 서식보존·문단 id 리프레시 — 균등 재생성 금지). 각 편집 후 `build_grid` 검증(overlap/hole/oob)으로 무효면 거부(fail-closed, 원칙 VI). 중첩표 거부.
- **실한컴 오라클 게이트** `verify_fill(before, after, require=)`: `resolve_oracle`+`visual_check`로 before/after를 실제 한컴 렌더 대조 → `render_checked`·overflow·overlap(글자겹침)·page_count. 오라클 없으면 정직 degrade(`render_checked=False`), `require=True`면 fail-closed. open-safety/HTML 프리뷰를 한컴 수용으로 오인 금지.
### 비고
- 오라클 실증: 실제 3학년 양식에서 `delete_column`(반영비율 7→5열 캐스케이드)·`insert_row_by_clone`(세부기준 +행, 85병합 표)·content-complete 운영계획 채움이 실한컴에서 서식보존·clean 렌더. MCP 표면(`apply_table_ops`·`verify_form_fill`)은 hwpx-mcp-server 2.13.0에서 합류.

## [2.20.0] - 2026-07-02
### 추가
- **M7 네이티브 자동 차례·상호참조 (S-062)**: `hwpx.tools.toc_author` — `add_native_toc`(한컴 네이티브 `TABLEOFCONTENTS` 필드영역 + Command DSL, `dirty=1` 기본 = 한컴이 처음 여는 순간 항목·차례 스타일·쪽번호를 재계산), `add_page_crossref`(쪽 번호 `CROSSREF` 필드 + 캐시 결과런 — 한컴이 편집/저장 시 자동 재계산), `mark_toc_dirty`(편집 후 재번호 재트리거), `ensure_paragraph_anchor_id`/`outline_heading_paragraphs`. 계약은 실제 한컴 저작 gold pair에서 리버스엔지니어링(`tests/fixtures/m7_toc_gold/`).
- **차례 충실도 하니스**: `hwpx.tools.toc_fidelity` — `parse_toc_model`(하이퍼링크·평문 재생성 항목 모두), `structural_report`(오라클 없이도 CROSSREF↔차례 캐시 모순으로 stale 탐지), `toc_verify`(한컴 렌더 대조 `toc_correctness_ratio`, 무오라클 시 정직 `unverified`), `grow_paragraph`.
- **Mac 오라클 새로고침 레그**: `MacHancomOracle.refresh_document`(+`_refresh_hwpx_mac.applescript`) — 열기→dirty 필드 재생성→제자리 저장→닫기. dirty-재생성 직후 같은 세션 PDF export가 이 한컴 빌드를 크래시시키는 실측 때문에 refresh와 render는 의도적으로 별도 세션.
### 수정
- Mac 렌더 스크립트 `waitForFile`이 `%%EOF` 트레일러를 요구 — size>0만으로는 비동기 export 도중의 잘린 PDF를 캡처했다(실측).
### 비고
- E2E 오라클 증명: 저작→새로고침→ratio 1.0(2/5/8쪽) → 재페이지네이션+`mark_toc_dirty`→새로고침→ratio 1.0 + 페이지 SHIFT(2/7/10). 실측 수집 규칙: `ContentsStyles:0:`이 바탕글(스타일 0) 문단도 차례 항목으로 수집 — 본문은 본문(스타일 1) 등 비수집 스타일 권장. MCP 표면(`add_toc`·`add_cross_reference`·`verify_toc`)은 hwpx-mcp-server 2.12.0에서 합류.

## [2.19.0] - 2026-07-02
### 추가
- **M6 런서식 충실 읽기 하니스 (S-060)**: `hwpx.tools.read_fidelity` — `resolve_run_spans`(런별 bold/italic/underline/strikeout/color/size_pt/font/super-subscript를 charPr+fontface 해석), `collect_notes`(각주/미주 본문 + 본문 서식), `roundtrip_fidelity`/`corpus_fidelity`(콘텐츠-레벨 라운드트립 충실도), `spans_fidelity`/`notes_fidelity` 비교기, 공개 `fontface_maps`/`run_span`. 요소-카운트만 재던 `roundtrip_diff`와 달리 charPr-해석 런-스팬 및 각주 본문의 무손실을 측정한다.
- `strikeout`은 shape 속성으로 정규화(항상 존재하는 `<hh:strikeout shape="NONE"/>`가 상시-on으로 오독되던 문제 회피), `underline` type `NONE`→`None` 정규화.
### 비고
- 코퍼스 런서식 라운드트립 충실도 1.0(4075 런 / hwpxlib 47편). reading 차원 4→5(구조적 corpus-scale, 오라클 불요). 설치 MCP 표면 노출은 hwpx-mcp-server 2.11.0에서 합류.

## [2.18.0] - 2026-07-01
### 추가
- **M5 개인정보(PII) 마스킹 엔진 (S-059)**: `hwpx.tools.pii` — `detect_pii` / `mask_pii` / `mask_value` / `PIIPolicy`. 기계검증 세트(주민등록번호·휴대폰·이메일·카드+Luhn)는 항상-on high-confidence, 맥락형(계좌·주소·이름)은 라벨 게이트 low-confidence(과마스킹 방지). 필드 최소화 `minimize_fields`, 가명 `Pseudonymizer`(결정적 토큰맵), 비식별 `deidentify`(불가역 salted-SHA256), 로그 위생 `PiiLogFilter` / `scrub_exception_message`.
- **메일머지·추출 경로 마스킹**: `mail_merge(masking_policy=DEFAULT_POLICY)` 기본 ON — 명부 산출물의 기계검증 PII 자동 마스킹(마스킹 길이로 FitPolicy 재측정). `export_text` / `export_html` / `export_markdown(masking_policy=...)` opt-in 추출 마스킹(기본 `None` = 내부 placeholder 탐지 보존).
### 비고
- 폼필(form-fill) 경로 마스킹·`scan_personal_info`·전 경로 0-누출 게이트는 MCP 표면(hwpx-mcp-server) 단계에서 합류합니다.

## [2.17.0] - 2026-06-30
### 추가
- **M4 변경추적(redline) 저작 (S-058)**: `HwpxDocument.add_tracked_insert` / `add_tracked_delete` / `add_tracked_replace` — 에이전트가 변경추적(삽입/삭제/치환)을 작성자·일자와 함께 저작하고, 사람이 한컴 검토 리본에서 개별 수락/거부할 수 있습니다. 헤더 `trackChanges`/`trackChangeAuthors` surgical splice(작성자 dedup·표시 플래그) + 본문 `insertBegin/End`·`deleteBegin/End` 마크(charPrIDRef 상속, paraend=0). 한컴 수용성은 measure-first 스파이크로 입증(실 Windows 한컴 COM `IsTrackChange=1`·opens-clean·roundtrip + 검토 리본 수락→반영/거부→취소 확인).
- `hwpx.tools.redline.verify_redline(before, after, *, oracle=None)` — 구조 검증(변경 수·TcId 마크 연결·표시 플래그·opens-clean) + `visual_check` `render_checked` 를 정직하게 fold(오라클 없으면 `unverified`, 거짓 통과 없음).
### 수정
- **메모(코멘트) 본문이 숫자로 표시되던 버그**: `attach_memo_field` 가 MEMO 필드 subList에 코멘트 내용 대신 메모 ID(숫자)를 넣어, 한컴이 메모 박스에 숫자를 렌더했습니다. 한컴 오라클 구조에 맞춰 subList에 코멘트 텍스트를 넣고 `MemoShapeIDRef`(기본 65535)로 박스를 연결하도록 수정했습니다(실 Windows 한컴 검증).
### 비고
- 수락/거부는 사람이 한컴 검토 리본에서 수행합니다(COM accept 액션 미노출 — 정석 워크플로).
- byte-identity: 미수정 part(ZIP 엔트리)는 byte-identical. 수정 섹션 내부의 문단단위 완전 byte-identical(surgical splice)은 stretch로 연기(한컴 렌더·수용엔 무영향).

## [2.16.0] - 2026-06-29
### 추가
- **M3 문서 작성 (S-057)**: `create_document_from_plan` 이 `document_type`(공문/보고서/가정통신문)을 보고 실제 한컴-harvest 프로파일(`hwpx.design.compose`)로 라우팅합니다. 미매칭 유형은 기존 제로베이스 경로를 유지하고 `-> HwpxDocument` 반환 계약을 보존합니다. 공문은 결문 메타 `document_plan.gyeolmun = {issuer, productionNumber, enforcementDate, disclosure}` 를 지원합니다.
- `hwpx.design.profiles.home_notice` — 실제 가정통신문에서 harvest한 디자인 프로파일.
- **공문 구조 hard-gate**: `inspect_official_document_style(source, *, document_type="공문")` 이 시행문 척추(수신·발신명의·시행·공개구분·끝.)를 ERROR 심각도로 검사하고 `structure_pass` 를 반환합니다. 표 셀까지 읽는 table-aware 텍스트 추출(실 시행문의 두문/결문은 표 안에 있음)을 추가했고, 진짜 시행문(`tests/fixtures/m3_gongmun_gold/seoul_sihaengmun.hwpx`)을 앵커로 삼습니다.
- `inspect_document_authoring_quality` 에 `korean_proofing_status`(정직 `unverified` / `llm_proofed_not_oracle_verified`, 거짓 통과 없음)와 `verify_render=True` 시 실제 한컴 렌더 영수증 `render_checked`/`visual_complete` 를 추가했습니다.
### 비고
- 각주(footnote) 작성은 한컴 렌더가 확인되지 않아 honest-deferred(`unverified`) 상태입니다.

## [2.15.0] - 2026-06-27
### 추가
- `HwpxDocument.set_paragraph_format(keep_with_next=, keep_lines=, page_break_before=)` — 문단 keep-together 플래그를 엔진 `ensure_paragraph_format(break_setting=)`로 전달한다(새 paraPr 발행, 기존 paraPr 미수정 = 무손실). 시험지 조판 등에서 한 문항이 단/쪽 경계에서 잘리지 않게 묶을 때 쓴다.
- `hwpx.exam`: re-typeset an authored exam (Markdown) into a school form `.hwpx`
  — Exam IR + strict md parser, form profiler (role→existing form style),
  keep-together body composition (insert into the form's body region, never
  append; 관리박스 + footer preserved byte-identical), and an oracle convergence
  driver `compose_exam_into_form`. The driver renders via Hancom and, when the
  composed 문항 are in the extractable text layer, verifies 문항-split / overflow
  / placeholder integrity (inserting column/page breaks to converge); when they
  are not (forms whose body Hancom exports as vector curves) or no oracle is
  available, it returns `render_checked`/`splits=None` + `needs_review` rather
  than a silent pass (Constitution V — honest unverified).
- `find_seal_anchor` — 발신명의가 좁은 표 셀에서 **여러 줄로 wrap**된 경우도 앵커를 찾는 fallback(연속 줄 윈도우, 최대 3줄). 단일 줄 매칭이 우선이라 기존 동작 불변; spurious 다중줄 매칭은 윈도우·동일페이지로 차단.
### 수정
- `paragraph.add_picture` — `treat_as_char=True`(inline)인데 `pos_overrides`(PAPER relTo/offset)를 주면 모순된 inline/floating `<hp:pos>`를 방출하던 것을 `ValueError`로 fail-fast. floating 배치는 `treat_as_char=False`에서만.

## [2.14.0] - 2026-06-25
### 추가
- `hwpx.form_fit.seal` — 직인/관인 배치 + 규정 검사(M2 P3). `find_seal_anchor`(발신명의 줄의 끝글자=도장 중심), `check_seal_placement`(중심 tol·가림 글자 차별 pass/fail), `seal_pos_offsets`(PDF pt 앵커→PAPER HWPUNIT offset), `place_seal`(발신명의 소스 문단—표 셀까지 탐색—에 직인을 floating 스탬프; 오라클 검증 0.12pt, fail-closed, page/clamp 정직신호).
- `hwpx.form_fit.wordbox.extract_image_boxes` — 렌더된 PDF에서 임베디드 이미지(직인) rect 추출. 직인은 글자가 아니라 그림이라 `get_text`로 안 잡힘.
- `add_picture(treat_as_char=False, pos_overrides=, text_wrap=)` — floating 그림 경로. PAPER 상대 `<hp:pos>`(offset은 xs:nonNegativeInteger로 coerce) + `textWrap`(직인은 `IN_FRONT_OF_TEXT`로 텍스트 안 밀고 위에 스탬프).
- `mail_merge(fit_policy=, max_lines=)` — fit-aware 배치(M2 P4 / FR-004). 각 placeholder 슬롯을 템플릿에서 한 번 측정(template-once-measure, advance-model·오라클 불필요)하고 레코드별로 fit. 넘침/결측 행을 `needsReview[]`/`skipped[]`(reason 코드 + retry advice)로 격리—자동 truncate 없음. `[xlsx]` extra(openpyxl)로 Excel/명부(.xlsx/.xlsm) 수용.
### 수정
- 임베디드 이미지 manifest `<opf:item>`에 `isEmbeded="1"`(OWPML 단일-d 철자) 방출 — 없으면 한컴이 `add_picture`로 넣은 **모든 그림을 렌더 드롭**하던 잠복 버그(한컴 GUI 렌더로 확정).
- `mail_merge`가 **표 셀** 안 placeholder도 치환 — `replace_text_in_runs`(본문 전용)가 셀 런에 안 닿아 발신·결재/안내 표 안 `{{토큰}}`이 미치환으로 남던 버그.

## [2.13.0] - 2026-06-24
### 추가
- `hwpx.conformance` — VisualComplete 적합성 코퍼스 + 배지 등급(plan §2 Phase G). `hwpx-conformance run`이 코퍼스를 4개 배지 등급(Open-Safe/Semantic-Safe/Form-Safe/VisualComplete)으로 채점하고 등급별 통과율을 산출합니다. 임계값은 엄격 기본값(구조 등급 100%, 폼셋 overflow 0%, VisualComplete ≥95%). golden 베이스라인(`tests/conformance/golden/structural.json`) 대비 회귀를 숫자로 감지하며(`--check`), CI가 구조 등급을 추적합니다. 어슈어런스 등급은 절대 섞지 않습니다(§0.0): 한컴이 없는 구조 실행은 VisualComplete를 `unverified`로 보고하고, 오라클 실행(도달 가능한 한컴 백엔드)만 VisualComplete를 검증합니다. 케이스에 `before`(+선택적 `editMask`)를 선언하면 VisualComplete가 오라클의 **before/after diff 경로**로 게이트됩니다(마스크 밖 변경·글자 겹침을 잡음). `expectVisualDefect`는 일부러 깨뜨린 쌍을 positive control로 삼아 게이트가 결함을 실제로 잡는지 검증합니다. (실측: 실제 한컴-저장 코퍼스에서 clean 쌍은 통과, out-of-slot 변경은 catch.)

## [2.12.0] - 2026-06-24
### 추가
- `hwpx.quality` — 단일 저장 게이트 `SavePipeline`, `QualityPolicy`, `VisualCompleteReport`. 모든 직렬화 출력이 이 게이트를 통과합니다(무결성·XML·OPC/ID·열림안전·시각 오라클 → 단일 리포트). `HwpxDocument.save_report(...)`로 노출.
- `hwpx.form_fit` — FormFit 엔진(`FitPolicy`/`FitResult`). 폼 값이 셀/필드 박스에 맞는지 측정(한글=1.0em, 한컴 실측 보정)해 wrap/shrink/truncate/fail 처리. `set_cell_text(fit=...)` / `fill_form_field(fit_policy=...)`로 연결.
- `hwpx.layout` — 렌더러 없는 구조적 시각 스모크 `lint_layout`(stale lineseg·dirty/lineseg·overflow risk·표 구조). `QualityPolicy.layout_lint`로 SavePipeline 하드 게이트로 연결.
- `hwpx.design` — 검증된 한컴 저장 템플릿 + harvest 프래그먼트로 새 문서를 생성하는 `compose`/`DocumentPlan`/profile 빌더. `official_notice`/`report`/`application_form` 프로파일 동봉.
- 시각 오라클 `hwpx.visual`에 Mac 한컴 백엔드(`MacHancomOracle`) 추가.

## [2.11.1] - 2026-06-12
### 수정
- `create_document_from_plan()`의 `heading` block과 builder `Heading`이 기본 템플릿의 `개요 N`/`Outline N` 문단 스타일을 실제로 적용하도록 수정했습니다. 생성 문서가 한컴 개요/문서 탐색과 MCP outline readback에서 구조화된 제목으로 인식됩니다.
- document-plan 기본 스타일 preset에 제목 18pt, 부제 12pt, 장 제목 14pt 글자 크기와 함초롬바탕 폰트를 적용해 보고서 생성 시 제목/본문 시각 위계가 명확하게 보이도록 했습니다.

## [2.11.0] - 2026-06-12
### 추가
- 시드 결정적 퍼징 수렴 루프 `hwpx.tools.fuzz`(시나리오 카탈로그·생성기·3중 오라클 러너·최소화)와 `tests/fixtures/fuzz_regressions` 회귀 박제 수트를 추가했습니다.
- 레이아웃 근사 프리뷰 렌더러 `hwpx.tools.layout_preview`를 추가했습니다(페이지 박스·표·여백 근사 HTML/PNG — 에이전트 자기검증용).
- section XML 바이트 splice 기반 문단 패치 경로 `hwpx.patch`를 추가했습니다(미수정 영역 바이트 보존).
- 그림 자산 안전 삽입·치환 API(`add_picture` 및 치환 워크플로)와 manifest 검증을 추가했습니다.
- 기존 문서 서식 편집 API를 추가했습니다: 문단 정렬·줄간격·들여쓰기·문단 간격, 용지·여백·방향, 머리말/꼬리말·쪽번호, 불릿/번호 형식.
- 누름틀(클릭히어 필드) 1급 조회·채움 API를 추가했습니다.
- 공문서 작성규정 lint `hwpx.tools.official_lint`(항목기호 위계·"끝." 표시·붙임·날짜 표기)와 결재란 프리셋을 추가했습니다.
- 고급 생성기 `hwpx.tools.advanced_generators`를 추가했습니다: 사진대지(`build_image_grid`)·회의 명패(`build_meeting_nameplates`)·표 기반 조직도.
- 신구대조 문단 diff와 참조 정합 lint `hwpx.tools.doc_diff`를 추가했습니다.
- 메일머지 대량 생성과 표 합계·평균 계산 유틸 `hwpx.tools.mail_merge`를 추가했습니다.
- 참조 문서 서식 프로파일 추출·적용과 템플릿 레지스트리 `hwpx.tools.style_profile`을 추가했습니다.
- template analyzer 리포트를 강화했습니다(열너비 재구성·cell margin·vertAlign).

### 변경
- `hwpx.oxml.document` 모놀리스(5,700여 줄)를 요소별 모듈(`_document_impl` 외 18개)로 분할했습니다. 공개 API는 변하지 않습니다.

### 수정
- 신뢰할 수 없는 입력 파싱을 강건화했습니다(`hwpx.opc.security`): XML entity 선언 거부와 깊이/크기 한도, ZIP 압축비·멤버 수 한도를 적용해 entity 폭탄·압축 폭탄 입력을 안전하게 거부합니다.

## [2.10.3] - 2026-06-09
### 추가
- `hwpx.tools.validate_editor_open_safety()`와 `EditorOpenSafetyReport`를 추가해 package validation, document validation, 재오픈 검증을 한 곳에서 확인할 수 있게 했습니다.

### 수정
- 텍스트를 줄이는 저수준 편집 뒤 stale `hp:linesegarray`가 남아 한컴 편집기에서 열리지 않을 수 있는 문제를 막기 위해, 저장 직전 plain-text 문단의 무효한 layout cache를 제거합니다.
- 편집된 section과 public 저수준 section write 경로는 모든 `hp:lineSegArray` layout cache를 제거해, 복합 문단처럼 stale 여부를 안전하게 계산하기 어려운 경우도 편집기가 다시 계산하도록 했습니다.
- public 저수준 section/header XML write 경로도 Hancom-compatible root namespace 선언과 `standalone="yes"` XML declaration을 보정해 generic XML serializer 출력이 그대로 저장되지 않도록 했습니다.
- `HwpxDocument.to_bytes()`, `save_to_path()`, `save_to_stream()`이 생성된 패키지의 editor-open safety를 확인한 뒤에만 결과를 반환하거나 쓰도록 보강했습니다. `save_to_path()`는 safety 실패 시 기존 대상 파일을 교체하지 않습니다.
- `HwpxPackage.save()`도 editor-open safety를 기본 검증해 저수준 package 직접 편집이 unsafe HWPX를 bytes/path/stream으로 내보내지 않도록 막습니다.
- public `HwpxPackage.save()`에서 editor-open safety 검증을 우회하는 파라미터를 제공하지 않도록 정리했습니다. 검증 실패 상태의 bytes snapshot은 package 내부 진단 토큰이 있는 경로에서만 생성하며, unchecked 경로는 caller-provided file path/stream에 직접 쓸 수 없습니다.
- `HwpxDocument._to_bytes_raw()`의 open-safety bypass 인자를 제거해 document 객체에서 unchecked bytes를 얻는 실수성 우회 경로를 더 좁혔습니다.
- private archive writer도 save 내부 컨텍스트에서만 동작하게 해, `_write_archive()`/`_write_zip_entry()` 직접 호출로 editor-open safety 검증을 건너뛴 ZIP을 만드는 실수성 우회 경로를 막았습니다.
- 문서/package 저장 중 open-safety, 실제 파일 쓰기, stream short write가 실패하면 dirty 상태를 성공처럼 정리하지 않도록 보강했습니다. seek 가능하고 안전하게 복원 가능한 stream은 쓰기 실패 시 원래 내용으로 rollback합니다.
- archive pack CLI가 재패킹 결과를 editor-open safety 리포트로 재검증하고, 실패 시 기존 output을 보존합니다. 성공 시 `PackResult.open_safety`와 CLI `open_safety_ok=true` 출력으로 handoff evidence를 제공합니다.
- repair/recover 출력도 CRC와 package validation 뒤에 editor-open safety를 재검증하고, section의 `hp:lineSegArray` layout cache 제거와 section/header root namespace 및 `standalone="yes"` 보정을 적용합니다. 실패 시 기존 output은 보존하고, 성공 시 `RepairResult.open_safety`로 handoff evidence를 제공합니다.
- template form-fit apply가 최종 목적지에 먼저 복사하지 않고 temp 파일에서 저장 및 editor-open safety 검증을 끝낸 뒤에만 교체하도록 보강했습니다.
- builder `Document.save_to_path()` 리포트에 `editor_open_safety` hard gate와 세부 리포트를 포함합니다.
- template form-fit paragraph clone 경로가 텍스트를 직접 바꿀 때도 layout cache를 제거합니다.
- package validator가 실제 텍스트 길이를 넘어서는 `lineseg/@textpos`를 hard error로 보고하도록 보강했습니다.
- `EditorOpenSafetyReport.ok`가 package/reopen뿐 아니라 document validation 실행 실패와 hard error도 반영하도록 보강했습니다.
- 저장 직전 paragraph의 `styleIDRef`가 `Normal`/`본문`처럼 header style 이름으로 잘못 들어간 경우, 일치하는 numeric style id로 정규화해 저수준 편집 산출물이 document validation에서 차단되거나 편집기 오픈 리스크를 만들지 않도록 했습니다.
- `HwpxPackage.save(updates=...)` 같은 순수 package 저수준 저장 경로도 header style 이름으로 된 paragraph `styleIDRef`를 numeric id로 정규화해, MCP를 거치지 않는 직접 ZIP/XML 편집 산출물도 같은 safety 보정을 받도록 했습니다.

## [2.10.2] - 2026-06-06
### 추가
- `hwpx.tools.markdown_export.export_markdown()`와 `HwpxDocument.export_rich_markdown()`을 추가해 풍부한 Markdown 변환을 지원합니다. 인라인 서식(굵게/기울임/취소선/색상/하이라이트), 표 병합 셀(colspan/rowspan HTML), 중첩 표 재귀, `rect`/`ellipse`/`polygon` 도형 내부 paragraph, BinData 이미지 추출, `Ⅰ.`/`1.` 패턴 기반 헤딩 감지(`# `/`## `), 각주·미주(정확 위치 마커 + `fn1`/`en1` 일련번호 + 본문 인라인 서식), 하이퍼링크(`[text](url)`) 보존을 한 번에 처리합니다. 기존 `HwpxDocument.export_markdown()`은 그대로 유지됩니다.
- `HwpxOxmlNote`에 본문 paragraph 접근/편집 helper를 추가했습니다: `body_paragraph` property, `add_run(text, *, char_pr_id_ref=..., bold=..., italic=..., underline=..., color=..., font=..., size=..., highlight=..., strike=..., attributes=...)`, `add_hyperlink(url, display_text, *, char_pr_id_ref=...)`. XML 직접 조작 없이 각주 본문에 혼합 서식 run과 하이퍼링크를 추가할 수 있습니다.
- `get_table_map()` 결과에 본문 표 anchor `location`, 셀 문단별 `table_cell_paragraph` location, `caption_text`, `preceding_paragraph_text`를 추가했습니다.
- 새 컨버터와 helper에 대한 회귀 테스트를 `tests/test_markdown_export.py`에 추가했습니다.

### 변경
- `HwpxOxmlTableCell.text`가 셀 내부 여러 문단을 줄바꿈으로 보존하고, `set_text(..., preserve_format=True, split_paragraphs=True)` 경로에서 기존 run `charPrIDRef`를 유지하도록 개선했습니다.

### 수정
- `HwpxOxmlParagraph.add_footnote()`/`add_endnote()`의 `char_pr_id_ref` 인자가 외부 호스팅 run에만 적용되고 각주 본문 run은 항상 `charPrIDRef="0"`으로 하드코딩되던 문제를 수정했습니다. 인자가 사용자 의도대로 본문 run에도 적용됩니다.

## [2.10.1] - 2026-06-04
### 추가
- `document_plan` authoring을 builder lowering 중심으로 확장하고 v2 builder node, TOC, government_report preset을 지원합니다.
- 정부보고서 계산/파싱 유틸리티(`hwpx.tools.report_utils`, `hwpx.tools.report_parser`)와 computed field 치환을 추가했습니다.
- generic element coverage inventory, table cleanup, table profile/caption/unit preservation, id reference integrity checker를 추가했습니다.
- `linesegarray`, `transMatrix`, `scaMatrix`, `rotMatrix`, edit/combo box control을 first-class OXML 모델로 승격했습니다.

### 변경
- builder save report의 hard gate가 id integrity를 실제 검사 결과로 반영하도록 강화했습니다.
- 패키지 rewrite 시 `mimetype` 엔트리를 보존하도록 OPC 저장 경로를 정리했습니다.

## [2.10.0] - 2026-06-02
### 추가
- `hwpx.builder` 공개 패키지를 추가했습니다. `Document`, `Section`, `Paragraph`, `Run`, `Heading`, `Bullet`, `NumberedList`, `Table`, `Image`, `Header`, `Footer`, `PageNumber`, `PageBreak`, `Metadata`, `PageSize`, `Margins` 노드로 조립형 HWPX 생성을 지원합니다.
- `BuilderSaveReport`와 `ReopenReport`를 추가해 builder 저장 후 package validation, document error/lint, reopen, feature flags, visual review 필요 여부를 확인할 수 있게 했습니다.
- 머리글/바닥글 리치 content, 자동 쪽번호, 리치 런 서식(color/font/size/highlight/strike), 다단계 목록, 표 병합/음영/열너비, 이미지 배치를 위한 `HwpxDocument` facade 및 OXML wrapper 메서드를 추가했습니다.
- `hwpx.document_plan.v1`, 운영 계획서 품질 프로필, template form-fit authoring, proposal/form-fill 품질 검증 흐름을 강화했습니다.
- hwpxlib sample corpus 기반 oracle fixture와 builder vertical slice 통합 테스트를 추가했습니다.
- `src/hwpx/tools/_schemas/owpml/`에 2011 Hancom 네임스페이스용 subset XSD 번들을 추가했습니다 (`header.xsd`, `body.xsd`, `paralist.xsd`, `core.xsd`, `xml.xsd`, `NOTICE`).
- `hwpx.oxml.load_compound_schema()`와 `SchemaImportError`를 추가해 offline compound XSD 로딩을 지원합니다.
- fixture matrix 기반 Phase 1 validation 리포트(`shared/hwpx/HWPX_STACK_VALIDATION_2026-04-20_pre-phase1.md`, `..._post-phase1.md`)와 회귀 테스트를 추가했습니다.

### 변경
- `validate_document().ok`는 error 기준으로 유지하고 schema warning은 lint/warning으로 분리해 가시화합니다.
- `HwpxDocument.save_to_path()` 기반 저장/재오픈 검증 경로를 builder와 authoring workflow에서 일관되게 사용하도록 정리했습니다.
- `hwpx-validate`는 이제 기본 strict 모드로 Phase 1 subset schema bundle을 사용합니다. `--no-strict`로 warning-only 분류를 지원합니다.
- `HwpxDocument.validate()`는 기본 `strict=False`로 동작하며, `validate_on_save_strict` 옵션으로 저장 시 strict 검증을 제어할 수 있습니다.
- 패키지 배포물(sdist/wheel)에 OWPML subset schema bundle이 포함되도록 package-data를 확장했습니다.

### 수정
- split-run placeholder, template form-fit, proposal/document-plan 생성 경로의 회귀를 보강했습니다.
- builder vertical slice에서 Hancom Office HWP 재오픈과 구조 hard gate가 통과하도록 머리글/바닥글 lowering과 page number control 배치를 정렬했습니다.

## [2.9.1] - 2026-04-27

상호운용성(interop) 버그 묶음 릴리즈입니다. 외부 기여자들이 보고하고 수정한 세 가지 문제를 정리합니다.

### 수정
- `HwpxOxmlTableCell._ensure_text_element`와 `ensure_run_style` 내 modifier가 lxml 엘리먼트 상에서 또한 `ET.SubElement`를 호출해 `TypeError`를 발생시키던 경로를 기본 헬퍼 `_append_child`로 정리했습니다. 이제 `cell.text = ...`와 `paragraph.add_run(..., bold=True)`가 monkey-patch 없이 정상 동작합니다 (#30, [@hhy827](https://github.com/hhy827)).
- `_paragraph_id` / `_object_id` / `_memo_id`가 `uuid4().int & 0xFFFFFFFF`로부터 signed int32 범위를 벗어나는 값을 약 50% 확률로 생성하던 문제를 수정했습니다. id 값을 signed 32-bit 양수 범위(`0 <= x < 2^31`)로 클램프해 downstream 소비자와의 상호운용성을 확보했습니다 (#34, [@seonghoony](https://github.com/seonghoony)).
- `HwpxDocument.new()`의 seed로 쓰이는 번들 `Skeleton.hwpx`에 signed int32 범위를 벗어나는 `<hp:p id="3121190098">`가 포함돼 있던 문제를 수정했습니다 (#35, [@seonghoony](https://github.com/seonghoony)).
- `pyproject.toml`에 PEP 639 `license` expression과 같이 남아 있던 legacy `License :: OSI Approved :: Apache Software License` classifier를 제거해 `setuptools>=77`에서의 소스 설치/바이너리 빌드 실패를 해소했습니다.

### 추가
- 위 세 버그에 대한 회귀 테스트를 추가했습니다 (`tests/test_document_formatting.py`, `tests/test_id_generator_range.py`, `tests/test_skeleton_template_ids.py`).
- 머지된 기여를 인정하는 `CONTRIBUTORS.md`를 추가하고 `README.md` / `CONTRIBUTING.md`에서 연결했습니다.

### 변경
- License relicensed to Apache-2.0 (sole author, full consent). Previous license terms no longer apply to future releases.

## [2.9.0] - 2026-04-02
### 추가
- `HwpxDocument.get_table_map()`, `find_cell_by_label()`, `fill_by_path()`를 추가해 HWPX 양식/템플릿 표를 문서 순서 기반으로 탐색하고 채울 수 있게 했습니다.
- `hwpx.tools.table_navigation` 모듈을 추가해 엔진 레벨에서 재사용 가능한 표 탐색, 라벨 정규화, 방향 이동, 배치 채우기 helper를 공개했습니다.

### 변경
- 라벨 매칭이 공백 축약, 대소문자 무시, 후행 콜론 허용 규칙을 따르도록 정규화 로직을 추가했습니다.
- 표 자동화 API에 대한 회귀 테스트와 README/API 레퍼런스 문서를 추가했습니다.

## [2.8.3] - 2026-03-10
### 변경
- 저장소와 배포 메타데이터의 라이선스 표기를 실제 `LICENSE` 파일과 일치하도록 정렬했습니다.
- `pyproject.toml`을 PEP 639 방식의 `LicenseRef-python-hwpx-NonCommercial` + `license-files` 구성으로 갱신하고, 잘못된 MIT 분류자를 제거했습니다.
- README 라이선스 배지/섹션을 커스텀 비상업적 라이선스 기준으로 수정하고, wheel/sdist 산출물의 라이선스 메타데이터를 검증하는 회귀 테스트를 추가했습니다.

## [2.8.2] - 2026-03-08
### 변경
- README를 현재 공개 API와 CLI 범위에 맞춰 정리했습니다. Quick start, 텍스트 추출, 객체 검색 예시를 실제 호출 방식 기준으로 수정했습니다.
- `add_memo()`/`add_memo_with_anchor()`가 `HwpxDocument.new()`로 만든 실제 `lxml` 기반 문서에서도 동작하도록 memo XML 생성 경로를 엔진 호환 방식으로 정리했습니다.
- 실제 빈 문서 템플릿에서 메모 추가 후 roundtrip 되는 회귀 테스트를 추가했습니다.

## [2.8.1] - 2026-03-08
### 추가
- 템플릿 자동화 회귀 스위트를 추가했습니다 (`tests/template_automation/`). 단순 토큰, 반복 토큰, split-run, 공백 정규화, 표/머리글/바닥글/다중 섹션, 체크박스 토글, extract-repack, 비표준 rootfile 패턴을 대표 fixture + 시나리오 계약으로 점검합니다.
- `DevDoc/template-automation-regression-suite.md`를 추가해 스위트의 보장 범위, 한계, fixture 추가 절차를 문서화했습니다.

### 변경
- 실제 `lxml` 기반 문서에서 `set_header_text()`/`set_footer_text()`가 동작하도록 header/footer 생성 경로를 XML 엔진 호환 방식으로 정리했습니다.
- 섹션 속성(`secPr`)이 비어 있을 때 보강 생성하는 경로를 XML 엔진 호환 방식으로 정리했습니다.
- `add_section()`이 새 섹션을 잘못된 네임스페이스로 만들던 문제를 수정했습니다.
- mypy/pyright gradual scope에 이번에 추가한 template automation helper/generator 모듈을 포함했습니다.
## [2.8] - 2026-03-08
### 변경
- `HwpxPackage`와 OXML 로딩/저장이 rootfile/manifest-relative 경로를 실제로 따르도록 정렬했습니다.
- `hwpx-analyze-template --extract-dir`가 재구성에 바로 쓸 수 있는 작업 디렉터리와 `.hwpx-pack-metadata.json`을 생성하도록 확장했습니다.
- `hwpx-validate-package`를 엔진 정합 기준으로 재작성해 dynamic rootfile/manifest 관계, CRC, fallback warning을 구분하도록 했습니다.
- `hwpx-unpack` 기본값을 raw-byte preserving으로 바꾸고 `--pretty-xml` opt-in을 추가했습니다.
- tooling/OPC 회귀 테스트를 확대하고, coverage threshold를 60으로 올렸으며, pyright는 touched OPC/tooling 범위에서 `basic`으로 상향했습니다.

## [2.7.1] - 2026-03-08
### 변경
- 공개 저장소와 배포 산출물에서 내부 감사 문서를 제거했습니다.

## [2.7] - 2026-03-08
### 추가
- `hwpx-unpack`, `hwpx-pack`, `hwpx-analyze-template` CLI를 추가했습니다.
- `src/hwpx/tools/archive_cli.py`를 추가해 unpack/pack 워크플로를 패키지 레벨 도구로 승격했습니다.
- unpack 시 `.hwpx-pack-metadata.json`을 기록하고, pack 시 이를 사용해 원본 ZIP 엔트리 순서/압축 방식을 가능한 범위에서 보존하도록 했습니다.
- `src/hwpx/tools/template_analyzer.py`를 추가했습니다.

### 변경
- `scripts/office/unpack.py`, `scripts/office/pack.py`, `scripts/analyze_template.py`를 패키지 도구 래퍼로 정리했습니다.
- `page_guard`에 shape/control count 및 히스토그램 비교를 추가하고, 실제 페이지 수 계산기가 아니라 구조 변화 징후 점검 도구임을 문서와 CLI 설명에 명시했습니다.
- README와 `docs/usage.md`에 새 CLI 사용 예시를 추가했습니다.
- 새 tooling에 대한 CLI/추출/overwrite/page-guard 회귀 테스트를 강화했습니다.

## [2.6] - 2026-03-08
### 추가
- `hwpx-validate-package` CLI와 `hwpx.tools.package_validator`를 추가해 ZIP/OPC/HWPX 패키지 구조, `mimetype`, `container.xml`, manifest/spine 참조, XML well-formedness를 점검할 수 있게 했습니다.
- `hwpx-page-guard` CLI와 `hwpx.tools.page_guard`를 추가해 섹션 수, 단락 수, page/column break, 표 구조, 텍스트 길이 변화량을 기준으로 문서 드리프트를 비교할 수 있게 했습니다.
- `hwpx-text-extract` CLI를 추가해 기존 `TextExtractor` 기능을 plain/markdown 형태로 바로 사용할 수 있게 했습니다.
- `scripts/office/unpack.py`, `scripts/office/pack.py`, `scripts/analyze_template.py`를 추가해 XML-first HWPX 작업 흐름을 지원합니다.
- gap-closure 반영분에 대한 테스트를 추가했습니다 (`tests/test_gap_closure_tools.py`).

### 수정
- `HwpxDocument.validate()`가 내부 직렬화 과정에서 dirty 상태를 지워 버리던 부작용을 제거해, 검증 이후에도 저장 필요 상태가 유지되도록 수정했습니다.

## [2.3.1] - 2026-02-28
### 추가
- **단락 삭제 API**: `paragraph.remove()`, `section.remove_paragraph()`, `document.remove_paragraph()` 메서드를 추가했습니다. 마지막 단락 삭제 시 `ValueError`가 발생합니다.
- **섹션 추가/삭제 API**: `document.add_section(after=)`, `document.remove_section()` 메서드를 추가했습니다. 새 섹션은 manifest/spine에 자동 등록되며, 마지막 섹션 삭제 시 `ValueError`가 발생합니다.
- **네임스페이스 상수 모듈**: `hwpx.oxml.namespaces` 모듈을 추가하여 HP, HH, HC 등 공유 네임스페이스 상수를 제공합니다.
- 새 API에 대한 16개 테스트 케이스를 추가했습니다 (`test_paragraph_section_management.py`).

### 수정
- `import hwpx`만으로 `DeprecationWarning`이 발생하던 문제를 수정했습니다. `hwpx.package` 경고는 이제 사용자가 직접 해당 모듈을 import할 때만 표시됩니다.
- `HwpxOxmlTableCell.text`가 셀에 여러 단락이 있을 때 첫 번째 텍스트만 반환하던 버그를 수정했습니다. 모든 `<hp:t>` 요소의 텍스트를 결합하여 반환합니다.
- `add_hyperlink()` 메서드에서 사용되지 않는 `field_inst_id` 변수를 제거했습니다.
- deprecated `save()` 호출을 사용하던 테스트 코드를 `save_to_path()`/`save_to_stream()`으로 업데이트했습니다.

## [1.9] - 2026-02-18
### 변경
- `hwpx.__version__` 하드코딩 값을 제거하고 `importlib.metadata.version("python-hwpx")` 기반으로 노출하도록 정리했습니다.
- editable/로컬 소스 실행처럼 배포 메타데이터가 없는 환경에서도 동작하도록 `PackageNotFoundError` fallback(`0+unknown`)을 추가했습니다.

## [0.1.0] - 2025-09-17
### 추가
- `hwpx.opc.package.HwpxPackage`와 `hwpx.document.HwpxDocument`를 포함한 핵심 API를 공개했습니다.
- 텍스트 추출, 객체 탐색, 문서 유효성 검사 등 도구 모듈과 `hwpx-validate` CLI를 제공합니다.
- HWPX 스키마 리소스와 예제 스크립트를 번들링해 바로 사용할 수 있도록 했습니다.
- 설치 가이드, 사용 예제, 스키마 개요 등 배포 문서를 정리했습니다.
