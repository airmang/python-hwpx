# 편집기 메뉴 표면 역매핑 — Windows (Menu → Engine Reverse Map, Windows)

`docs/editor-surface-inventory.md`는 "우리 능력 영역 → 실한컴 검증 상태"를
잰다 — 순방향이다. `docs/editor-menu-reverse-map.md`는 그 반대 방향을
**macOS 한컴오피스 메뉴 9종**에서 열었다. 이 문서는 같은 역방향 질문을
**Windows 한글 2024(13.0.0.3901)의 실물 표면 전체**로 넓힌 것이다 —
한컴 편집기 메뉴 항목 → 우리 대응.

macOS 스캔은 스스로 한계를 명시했었다: "**macOS 앱 기준** — Windows 한컴
전용 표면은 이 스캔으로 부재를 단정할 수 없다." 이 문서가 그 유보를
해소한다. 6.16 트레인(2026-08-16~17)이 Windows 실빌드에서 메뉴를
라이브 열거하고, 같은 빌드의 도움말 트리와 한컴 공식 오토메이션 문서를
분모로 삼아 **판정 없는 Windows 항목 0**을 달성했다. 이어서 실한컴
프로브 세션이 판정 보류로 남았던 항목의 실물 계약을 확보했다 —
아래 "실측으로 확정된 계약" 절.

## 방법론

### 분모 — 3축 교차

Windows 표면의 "전체"를 한 축으로 정의하지 않았다. 서로 독립적인 세 축을
교차시켜, 어느 한 축이 놓친 항목이 다른 축에 걸리게 했다.

1. **라이브 메뉴 덤프** — 실빌드(한글 2024, 13.0.0.3901)의 UI Automation
   트리를 워크해 **메뉴바 11항목 + 각 드롭다운 항목 전수(깊이 1)**를 접근키까지
   실측했다: 파일 25 · 편집 16 · 보기 15 · 입력 22 · 서식 13 · 쪽 20 ·
   보안 7 · 검토 8 · 도구 20. 도형/추가 기능은 드롭다운이 없는 리본 탭
   전용임도 실측으로 확인했다. **메뉴바에 '표' 최상위 메뉴는 없다** —
   도움말 트리가 세는 표 24항목은 캐럿이 표 안에 있을 때 뜨는 문맥 메뉴다.
2. **같은 빌드 도움말 목차** — 실설치본 도움말을 디컴파일해 목차를
   **974노드 트리**로 구조화했다. 최상위가 실메뉴 구조와 정합한다(파일 23 ·
   편집 19 · 보기 15 · 입력 22 · 서식 12 · 쪽 19 · 보안 7 · 검토 8 ·
   도구 20 · 표 24 · 그림 그리기 6 · 추가 기능 2 · 한컴독스 5). 라이브
   덤프가 깊이 1까지만 닿는 자리를 이 축이 메운다.
3. **한컴 공식 오토메이션 문서 ↔ 빌드 양방향 대조** — 공식 액션 테이블
   (`ActionTable_2504.pdf`, 2025-04-15판) 시드 **898종**을 실빌드에서 전수
   프로브하고(핸들 생성 / `CreateSet` 존재 / `setId` 관찰), 1차에서 부재로
   나온 55건을 정밀 분류해 **67종을 재프로브**했다 — 합계 **965종 실측**.
   양방향인 이유: 문서에 있고 빌드에 없는 것(오타·더미)과 문서가 틀리게
   적은 것(pset 불일치)이 둘 다 드러난다. 결과는 아래 "오토메이션 문서
   편차" 절.

### 판정 어휘

macOS판과 같은 5갈래를 그대로 쓴다.

- **[대응 영역]** — 기존 캐파빌리티 행(또는 지원 매트릭스 행)과 명확히 대응.
- **[부분 대응]** — 대응하는 메커니즘이 있으나 이 메뉴 항목이 요구하는 전체
  범위를 못 채움(뭐가 빠졌는지 명시).
- **[대응 없음=신규 갭]** — 코드 실사로 확인된, 대응하는 저작/편집 경로가
  전혀 없음.
- **[스코프 밖]** — 문서 형식(OWPML) 자체의 속성이 아니라 애플리케이션
  UI/대화형 편집 세션/언어 도구 등(근거 명시).
- **[미확인]** — OWPML 표현 여부가 실사만으로 불확실. **추측 금지**(무근거
  승격도, 무근거 갭 선언도 하지 않는다) — 확인 방법을 함께 적는다.

계층 판정 하나가 더 있다: **[대응 없음, core]** 는 core 엔진엔 없으나
`hwpx_automation` 계층에 있는 기능이다(표 계산식 3종의 기존 전례).

### 판정 축 — 항목마다 5축

각 항목은 다섯 축을 순서대로 대조했다. 축이 갈리지 않으면 [미확인]으로
남기고 프로브를 처방한다.

1. **벤더 의미** — 같은 빌드 도움말 원문(955개 HTML, cp949). 기능의 정의·
   대화상자 항목·저장 위치 서술을 원문 그대로 인용한다.
2. **스키마** — `DevDoc/OWPML SCHEMA/` 7종 전수 grep(줄번호 기록).
3. **실코퍼스** — `tests/fixtures/**/*.hwpx` **71파일** 전수(모든 zip 멤버
   디코딩 후 카운트). 원장(`docs/coverage-ledger.json`, 237파일 census)과
   수치가 갈리면 둘 다 병기한다.
4. **코드** — `src/hwpx/` 전수 grep(파일:줄). `INLINE_OBJECT_NAMES`
   (`oxml/body.py:17-37`) 소속 요소의 read=True는 **타입 읽기가 아니라
   봉투 읽기**(불투명 `InlineObject`)이므로 구분해 표기한다.
5. **액션** — 965종 실측. `createSet=false`/`null`은 "COM으로 조작 가능한
   문서 상태가 없다"는 신호로 읽고(6.15 트레인의 `FileSaveAsDRM` 판정
   논리), `setId`가 붙으면 그 이름의 상태 묶음이 실재한다는 뜻이다.
   **다만 `setId` 단독으로 "문서에 저장된다"고 승격하지 않는다** — 상태가
   앱 쪽에 있어도 `setId`는 붙는다(스크립트 매크로 행이 그 사례).

### macOS판과의 관계

Windows 표면 판정 행 **181** 중 **91행은 macOS 역매핑의 기존 판정을 그대로
재인용**한 것이다(같은 기능의 다른 진입 경로이거나 이름만 다른 항목 —
"글자 방향 설정…"↔"글자 방향", "다단 설정 나누기"↔"단 설정 나누기" 등).
그 91행의 근거 원문은 `docs/editor-menu-reverse-map.md`에 있고 여기서
재조사하지 않았다. **이 문서의 표는 나머지 90행 — Windows에서 처음
판정한 항목**만 담는다. 상위 행이 자식별로 갈린 2건(차례/색인,
프레젠테이션)을 펼친 표기 때문에 아래 표의 행수는 92다.

스킵 5건은 UI 상태라 판정 대상이 아니다(최근 문서 3 · 끝 · 창 목록의
현재 창).

## 파일

| 메뉴 항목 | 판정 | 근거 |
|---|---|---|
| 문서 시작 도우미 | [스코프 밖] | **도움말**(`file/start_screen.htm`): 한컴오피스 패키지의 응용 프로그램과 한컴독스를 한 곳에서 실행하는 **올인원 시작 화면**(최근/공유 문서 목록, 온라인 서식 내려받기, "다시 표시 안 함" 옵션). 문서의 속성이 전혀 아니다. **스키마** 7종 대응 어휘 0 · **액션** 965종에 `Start`/`Screen`/`Assist`/`Cloud` 계열 0건. macOS "문서마당…"·"최근 사용 문서"와 같은 부류 |
| PDF를 오피스 문서로 변환하기 | [스코프 밖] | **도움말**(`file/open/open(pdf).htm`): [파일 형식]이 `*.pdf`로 고정된 **불러오기 대화상자**다 — PDF 페이지를 텍스트·표·개체로 되살리는 것은 **변환 엔진**이고 macOS "PDF로 저장하기 [스코프 밖]"(렌더/변환은 스코프 밖)과 같은 축이다. **가져오기 방향 확인**: 산출물은 별도 형식이 아니라 평범한 한/글 문서라 우리 파서가 이미 다루고, 변환 유래를 표시하는 어휘도 없다 — OWPML의 유일한 산출-프로그램 표지 `hh:compatibleDocument/@targetProgram`은 코퍼스 69파일 전부 `"HWP201X"` 단일값. **액션** PDF 전용 0건(`FileOpen`, setId=`FileOpenSave`만) |
| 그림을 오피스 문서로 변환하기 | [스코프 밖] | **도움말**(`file/open/open(picture)_ocr.htm`): **OCR**(언어 한국어/영어, 그림 1개씩)이다 — 인식 결과 품질이 그림 품질에 좌우된다는 주의까지 붙어 순수 인식 엔진임이 명백하다. 맞춤법·한자 변환·받아쓰기와 같은 **언어/인식 도구** 분류. **스키마** `ocr` 0건 · **액션** 0건. 산출물(평범한 문서)은 이미 우리 대상 |
| XML 문서 (XML 탭 / 서식 만들기 / 서식마당 / 불러오기 / 저장하기) | [스코프 밖] | **도움말**(`file/xml_document.htm` 외 4): 여기서 "XML"은 HWPX/OWPML이 아니라 **HML 스키마**(한/글 자체 XML)다 — "HML 스키마 형식에 맞는 XML 문서만 한/글 XML 서식으로 불러오고 저장하며, 아니면 바이너리로 처리". 즉 **다른 파일 포맷 가족**(`DevDoc/hwpml형식문서.txt`가 그 포맷의 벤더 레퍼런스)이고 스타일시트(*.xsl)와 짝이다. `XML 서식 만들기`는 XSD를 물려 **서식 파일(*.hwt)**을 만들어 산출물도 hwpx가 아니다. **코드** `.hwt`/`.hml` 취급 0건 · **액션** 0건. 보기 메뉴 "작업 창"의 `XML 문서 구조`/`XML 문서 트리` 패널은 이 기능에서만 나타나므로 같은 판정을 상속 |
| 모바일 최적화 문서로 저장하기 | [스코프 밖] | **도움말**(`file/to_mobile.htm`): 레이아웃은 유지하되 **차트·글맵시·OLE·양식 개체·그룹 개체를 그림으로 저장**하고 그림 해상도를 낮춘다. 개체를 그림으로 굽는 것은 래스터화라 "PDF로 저장하기"와 같은 축이다. **코드** `flatten`/`rasteriz`/`mobile`/`downscale` 계열 0건 · **스키마** `mobile` 0건 · **액션** 0건. 부기: 산출물은 개체가 `hp:pic`으로 치환된 평범한 문서라 우리 읽기/저작 어휘 안에 있다 |
| DAISY 문서 — DAISY로 저장하기 | [스코프 밖] | **도움말**(`file/daisy_document.htm`, `daisy(save).htm`): DAISY는 시각/독서 장애인용 **국제 디지털 문서 형식**이고, 이 기능은 한/글 문서에 DAISY 필터를 적용해 `*.xml`로 내보낸다(입력은 저장 위치·파일 이름·제목·지은이·Uid). 산출물이 OWPML이 아니다 — "인터넷 문서로 저장하기"·"텍스트 파일로 저장하기"와 같은 외부 포맷 내보내기 부류. **스키마** `daisy` 0건 · **액션** 0건 |
| DAISY 문서 — DAISY 스타일 가져오기 | [대응 영역] | **분리 판정**(macOS "날짜/시간·파일 이름" 전례 — 같은 부모의 자식들이 성격이 갈리면 행을 나눈다). **도움말**(`daisy(style_open).htm`): 기본 제공 DAISY 스타일 파일(*.xsl)을 불러오면 **글자 스타일 11개 + 문단 스타일 32개 = 43개가 현재 문서의 스타일 목록에 등록**된다(이름 옆 `(DAISY)` 표기, 바탕글만 예외). 이 자식만은 **문서를 실제로 바꾼다** — 결과는 `hh:style`(+`hh:charPr`/`hh:paraPr`) 추가이고 `HwpxOxmlHeaderPart.ensure_style`(`oxml/header_part.py:1006`, 이름 기준 dedupe·`style_type` PARA/CHAR·id 반환)이 정확히 그 저작이다. 벤더가 번들하는 .xsl 자산(43종의 구체적 서식값)은 한컴 배포물이라 스코프 밖이지만 **등록 메커니즘은 이미 대응** |
| **공공누리 넣기 / CCL 넣기** | **[부분 대응]** | **문서 수준 저작권 레코드가 실재한다 — 이번 실측의 수확 중 하나.** **도움말**(`file/kogl.htm`)의 대화상자 축은 ①영리 목적 허용 ②2차 저작 허용 ③표시 언어(한국어/영어/혼합) ④유형 표시 방법(그림+글자/그림만/글자만) ⑤그림 표시 형태. 결정적 근거는 다른 토픽에 있다(`file/document_properties/document_license.htm`): "[문서 정보] 대화 상자의 [저작권] 탭은 **[CCL 넣기]와 [공공누리 넣기] 기능을 이용하여 … 마크를 삽입한 경우에만 나타납니다**" — 본문 그림/글자만이라면 [문서 정보]가 그 값을 알 길이 없다. **스키마**: `hh:licensemark`(`Header XML schema.xml:80-86`)는 `hh:docOption`(`DocOptionType`, `:71-88`)의 선택 자식이고 속성은 `type`(unsignedInt, required)/`flag`(byte, required)/`lang`(byte)뿐, `xs:documentation`은 전무. **실코퍼스** 71파일 `licensemark` 0건(`hh:docOption` 자체는 69파일에 있으나 자식은 전부 `hh:linkinfo`). **코드**: **읽기 모델은 이미 있다** — `LicenseMark`(`oxml/header.py`) + `parse_license_mark` + `DocOption.license_mark` + 공개 export까지. **저작 경로는 0건**(serializer도 setter도 전수 무결과) — 바탕쪽이 6.13 전까지 "읽기만"이었던 것과 정확히 같은 형태다. **액션**: `InsertCCLMark` handle=True·createSet=True·실측 setId=**`CCLMark`**(공식 문서 주장은 `HyperLink` — 아래 "오토메이션 문서 편차" 참조). 공공누리 전용 액션은 965종에 없다. ✅ **실측으로 2원 구조 확정** — 아래 "실측으로 확정된 계약" ② |
| 점자로 바꾸기 (점자 문서로 / 선택 글자 / 설정) | [스코프 밖] | **도움말**(`file/conversion_to_braille.htm` 외 3): 한글·영문·숫자를 점자로 치환한 **새 문서를 새 창/새 탭에 생성**한다(미주·각주·메모·개체 안 내용 미변환, 역변환 불가). 설정은 변환 코드(6점 ASCII / 8점 유니코드)·글자 크기·글꼴·용지·줄 수. 문자 치환 자체는 **언어/문자 변환 엔진**이고, 8점 방식은 결과가 유니코드 점자 문자라 일반 텍스트와 구조상 구분되지 않는다. **스키마** `braille`/`점자` 0건 · **코퍼스** `braille` 0건(`점자` 6건/3파일은 전부 무관한 본문 텍스트). 산출물 구조는 전부 기존 대응 영역 — 글꼴/크기는 `doc.styles.ensure_run`(`_document/ns/styles.py:372`), 용지·줄 수는 `doc.page.set_size`(`_document/ns/page.py:114`). **액션** 3종 전부 setId=`BrailleConvert`이나 그 내용은 **변환 파라미터**이지 문서 상태가 아니다 |
| 보내기 (편지 본문/첨부 · 웹 브라우저 · 웹 서버) | [스코프 밖] | **도움말**(`file/send_to_mail/send_to_mail.htm` 외 3): MAPI 메일 발송, HTML 임시 저장 후 브라우저 실행, FTP 업로드. 전부 **전송 채널**이지 문서 속성이 아니다. **액션**: `SendMailText`/`SendMailAttach`→setId=`FileSendMail`, `SendBrowserText`→createSet=**False**, 웹 서버 올리기는 액션 없음. 부기: 웹 브라우저로 보내기가 거치는 HTML 내보내기는 core에 대응이 있다 — `hwpx.tools.exporter.export_html`(`tools/exporter.py:143`), 다만 한컴 "인터넷 문서"(문자 코드 6종·서식 보존)와 동일 산출물은 아니고 문단/표 위주 단순 HTML이다 |
| 미리 보기 (미리 보기 탭) | [스코프 밖] | **도움말**(`file/preview/preview.htm`): 인쇄 전 화면 확인 전용 상태로 **문서 편집 불가**, 맞쪽/여러 쪽/여백 보기 상태는 "한/글이 실행되어 있는 동안" 기억된다(=세션 상태). **액션** `FilePreview` handle=True·createSet=True·**setId=`Print`** — 실측 pset이 인쇄와 같다는 것 자체가 "인쇄 다이얼로그의 다른 표시 모드"임을 뒷받침한다. macOS "인쇄… [스코프 밖]" 상속. **코퍼스 확인**: 문서에 저장되는 인쇄 관련 상태는 `settings.xml`의 `config:config-item-set name="PrintInfo"`(69파일 중 14파일, 항목 8종 `PrintAutoFootNote`/`PrintAutoHeadNote`/`PrintMethod`/`OverlapSize`/`PrintCropMark`/`BinderHoleType`/`ZoomX`/`ZoomY`)뿐이고 미리 보기 상태는 없다 |

## 편집

| 메뉴 항목 | 판정 | 근거 |
|---|---|---|
| 고치기 | [부분 대응] | **도움말**(`edit/modification.htm`, `<Ctrl+N,K>`): 커서 위치에서 앞쪽으로 거슬러 올라가며 처음 만나는 개체의 고치기 대화상자를 여는 **디스패처**다. 대상 21종(그림·표·글상자·그리기 개체·수식·글맵시·그리기마당·상호 참조·머리말/꼬리말·글자 겹치기·각주/미주·덧말·쪽 번호 위치·감추기·필드 입력·숨은 설명·색인 표시·하이퍼링크·책갈피·메일 머지 표시·계산식). **액션**: 디스패처에 가장 가까운 `ModifyCtrl`은 handle=True·**createSet=False**(자기 pset 없음 = 순수 디스패치)이고 대상별 고치기는 `Modify*` 계열이 각자 pset으로 갈린다. **대상 대부분은 이미 대응**. **못 채우는 대상 4종**: 글맵시(`hp:textart` — 코퍼스 2건/1파일, 코드는 `INLINE_OBJECT_NAMES`(`oxml/body.py:36`) **봉투 읽기만**), 색인 표시(`hp:indexmark`), 숨은 설명(`hp:hiddenComment` `ParaList XML schema.xml:217`, 코퍼스 1건/1파일, 코드 0건 — `GenericElement` 폴백 바이트 보존만), 계산식(계층 판정). **주의**: 이 4종은 각각 다른 메뉴의 독립 항목이므로 그쪽 행이 본 판정을 하고 고치기의 부분성은 거기서 **상속**된다 — 신규 갭으로 중복 계상하지 말 것 |
| OLE 연결 | **[대응 없음=신규 갭] (근거 명시 보류)** | **도움말**(`edit/objectlink.htm`): "개체 연결"(LINK)로 삽입된 OLE의 연결 목록·원본 위치·**업데이트 방식(자동/수동)**·지금 업데이트·원본 열기/변경·연결 끊기를 관리한다. **스키마**: `hp:ole`=`OLEType`(`ParaList XML schema.xml:2304-2343`)에 `objectType` 열거의 `LINK`(`:2316`)와 `hasMoniker`(`:2323`, default false)가 실재한다. **그러나 원본 경로·업데이트 방식·마지막 갱신 시각을 담을 속성이 `OLEType`에 없다** — 연결 메타는 OWPML 밖(`BinData/*.ole` 스트림 안 moniker)일 가능성이 높으나 미실측. **코퍼스**: `hp:ole` 전수 2건/2파일(`objectType="EMBEDDED"` 1 + `"UNKNOWN"` 1) — **`LINK` 표본 0건, `hasMoniker="1"` 0건**. **코드**: 봉투 읽기만, 연결 갱신/끊기 개념 자체가 없다. **액션**: 대응 액션 없음(`OleCreateNew`(setId=`OleCreation`)은 **삽입**이지 연결 관리가 아니다). → 저작 경로 전무는 확실하나 LINK 표본 0건 위에 연결 구조를 합성하지 않는다(`curve`·`connectLine`·DEV-021과 같은 원칙). 이번 프로브 세션에서 미착수, 다음 세션 이월 |
| OLE 개체 속성 | [부분 대응] | **도움말**(`edit/objecedit.htm`): [일반] 종류·크기·위치, [변환] 유형 변경, [보기] 편집 가능한 정보로 표시 / **아이콘으로 표시** / 아이콘 변경 / 배율 10~500%, [연결] 탭(연결 개체일 때만). **스키마 대응은 있다**: `drawAspect`(`ParaList XML schema.xml:2324-2331` — `CONTENT`/`THUMB_NAIL`/**`ICON`**/`DOC_PRINT`)가 "아이콘으로 표시"와 정확히 대응하고 크기는 `extent`+`hp:orgSz`/`hp:curSz`가 담는다. **코드는 봉투 수준**: `ole`은 `INLINE_OBJECT_NAMES`(`oxml/body.py:32`) 소속이라 `Run.inline_objects`(`body.py:385`)에 `InlineObject`(tag/name/**속성 raw dict**/children)로 뜨고 `_inline_object_to_xml`(`:1397`)이 무손실 재직렬화한다 — **타입 읽기가 아니라 봉투 읽기**(`objectType`/`drawAspect`를 아는 모델도, 열거값 검증도 없다). 범용 무타입 편집기 `HwpxOxmlInlineObject.get_attribute`/`set_attribute`(`oxml/objects.py:51-68`)로 문자열 수준 변경은 가능하나 (a) OLE 전용 헬퍼·검증 없음 (b) **기존** `hp:ole`을 집어오는 열거 경로가 oxml 래퍼 층에 없음 (c) 아이콘 변경·[변환]은 `BinData/*.ole` 내부 조작이라 범위 밖. ✅ **`drawAspect="ICON"` 실물은 이번에 확보**(소리 삽입 실측 — 아래 "실측으로 확정된 계약" ③) |

## 보기

macOS 스캔에서는 보기 메뉴 전체가 일괄 [스코프 밖]이었다. Windows 신규
8항목은 개별 판정했고 **8건 모두 [스코프 밖]**으로 수렴했다 — 다만 근거는
항목마다 다르고, 특히 "격자"는 **동명이인(`hp:grid`)과 반드시 갈라야
한다**.

| 메뉴 항목 | 판정 | 근거 |
|---|---|---|
| 확대/축소 (여러 쪽) | [스코프 밖] | **도움말**(`view/zooming/zoom.htm`): "문서의 **실제 크기를 바꾸지 않고 화면에 보이는 크기만** 확대하거나 축소". **액션** `ViewZoom*`→setId=`ViewProperties`(앱 뷰 상태), `ViewZoomLock` createSet=False. **코퍼스 실측**: `settings.xml` 69파일 전수에 화면 배율 항목 **0건** — 등장 태그는 `ha:HWPApplicationSetting`(69)/`ha:CaretPosition`(69)/`config:config-item-set`(14, `name="PrintInfo"` 하나뿐)/`config:config-item`(110)뿐이고, 유일한 zoom 어휘인 `ZoomX`/`ZoomY`는 그 PrintInfo 안 = **인쇄 배율**이다. macOS "화면 확대/축소" 재확인 |
| **격자** (격자 보기 / 격자 설정) | [스코프 밖] | **`hp:grid`와는 다른 개념이다 — 갈라서 판정한다.** **도움말**(`view/grid/grid.htm` 외 3): 편집 화면에 점/선을 그려 **그리기 개체를 정렬하는 스냅 보조선**이다(점/선 격자, 격자 위치, 격자 방식, 간격 1~25mm, 기준 위치, 자석 범위 0~25mm). 결정적 진술: "**[격자 보기]를 선택해 놓더라도 … 문서를 인쇄하면 격자는 인쇄되지 않습니다**". 반면 **`hp:grid`**(`ParaList XML schema.xml:726-746`, `hp:secPr`의 자식, `xs:documentation`="**줄맞춤 정보**")는 속성이 `lineGrid`/`charGrid`/`wonggojiFormat` 셋뿐 = [편집 용지: 줄 격자]와 [원고지]의 구조이고 이미 `doc.page.set_grid`(`_document/ns/page.py:461`, 구현 `oxml/section_format.py:399-426`)가 저작한다(코퍼스 78건/69파일). 같은 축의 `hh:paraPr/@snapToGrid`(`Header XML schema.xml:1624`)도 읽기 모델이 있다. **보기-격자 값이 문서에 저장된다는 근거는 없다**: 스키마에 스냅 격자 어휘(간격/자석/기준 위치) 0건, `settings.xml` 69파일 0건. **액션** setId=`GridInfo`는 **앱 설정 pset**(COM으로 조작 가능 ≠ 문서에 저장) |
| 안내선 (그리기 안내선 / 개체 이동 안내선·설정) | [스코프 밖] | **도움말**(`view/object_move_guideline/*`): 개체를 그리거나 옮길 때 나타나는 정렬 가이드의 표시 토글과 설정. **액션** `ViewOptionGuideLine` handle=True·**createSet=False**(pset 자체가 없다 = 순수 화면 토글), 개체 쪽은 setId=`ShapeGuideLine`(앱 설정). **스키마** `guide`/`guideline`/`안내선` 0건 · **코퍼스** 0건 · `settings.xml` 0건. macOS "조판 부호 지우기…"·"문서 보안 설정…"과 같은 "문서에 흔적 없는 화면 상태" 부류 |
| 문서 보기 색 (사용자 색 설정) | [스코프 밖] | **도움말**(`view/document_view_color.htm`, `user_color.htm`): 사용자의 시각 상태에 맞춰 **편집 영역의 배경/글자 표시 색을 바꾸는 화면 테마**다(컬러/회색조/고대비/어둡게/밝게/한글 테마/사용자 색). "컬러" 설명이 "문서에 사용된 색상을 **그대로 표현**"이라 문서 색을 바꾸는 기능이 아님이 명시적이고, 사용자 색 항목은 하이퍼링크·형광펜·메모·격자 같은 **UI 요소**에까지 걸리는 접근성 설정이다. **액션** 둘 다 **createSet=False**. macOS "컬러/회색조"의 확장판 |
| 작업 창 (14종) | [스코프 밖] | **도움말**(`view/workwindow/workwindow.htm`): 붙이고 뗄 수 있는 **도킹 패널**(사전 검색·한/글 도우미·개요 보기·빠른 실행·쪽 모양 보기·클립보드·양식 개체 속성·스크립트·XML 문서 구조·XML 문서 트리·스타일·책갈피·번역·바탕쪽 보기). **액션** 965종에 `Task`/`Pane`/`Sidebar`/`Window` 어휘 **0건**. **부기(중복 갭 방지)**: 패널이 *보여주는* 내용은 이미 각각 대응 영역이다 — 스타일(`ensure_style`)·책갈피·개요 보기(`apply_paragraph_format(outline_level=)`)·양식 개체 속성·바탕쪽 보기(`add_master_page`)·클립보드(스코프 밖). `XML 문서 구조`/`XML 문서 트리`는 파일 메뉴 "XML 문서" 판정을 상속 |
| 편집 화면 나누기 (나누지 않음/가로/세로/가로세로) | [스코프 밖] | **도움말**(`window/division/division.htm`)의 결정적 진술 2개 — "**[파일-새 문서]나 [불러오기]를 하면 현재 화면의 나누기 상태를 무시하고** 나누지 않은 채로 문서 창을 열어 줍니다"(문서에 안 실린다), "나누기 된 화면에서 화면 확대 비율과 문단 부호·조판 부호·투명 선·쪽 윤곽 등의 보이기/숨기기 상태는 **화면마다 각각 다르게** 지정할 수 있습니다"(뷰 상태의 다중 인스턴스). **액션** 0건 |
| 창 배열 (가로/세로/겹치게/모두 아이콘으로) | [스코프 밖] | **도움말**(`window/arrange/arrange_windows.htm`): 열려 있는 모든 문서 창의 타일/겹침 배치. 애플리케이션 창 관리 — macOS "문서 창"·"전체 화면"과 같은 부류. **액션** 0건 |
| 창 목록 | [스코프 밖] | **도움말**(`window/windows_list.htm`): 열린 문서 창 목록 대화상자에서 창 전환·저장·배열. 열린 창 집합은 애플리케이션 상태다. **액션** 0건 |

## 입력

| 메뉴 항목 | 판정 | 근거 |
|---|---|---|
| 글상자 | **[부분 대응]** | **도움말**(`insert/textbox/textbox.htm`): 글상자는 사각형 개체 + 그 안의 텍스트, 고치기는 [서식-개체 속성]. **스키마** `hp:drawText`(`ParaList XML schema.xml:2351` — `subList`+`textMargin`, 속성 `lastWidth`/`name`/`editable`). **코퍼스** `hp:drawText` 56건·11파일(원장 237파일 census는 42파일). **코드** `HwpxOxmlShape.draw_text`/`.set_draw_text`/`.remove_draw_text`(`oxml/objects.py:1489-1521`, 쓰기 `_write_draw_text` `:1237-1269`) — 본체는 저작 가능. **못 채우는 범위 3종**: ①**글상자 연결** — 스키마가 `hp:ParaListType`에 `linkListIDRef`/`linkListNextIDRef`(`:51-52`)로 선언하지만 코퍼스 실측 **9,587/9,587 전부 `"0"`**(33파일), 즉 **실 체인 사용례 0건**이고 저작 API도 없다. `tools/document_merge.py:80-95`가 이 둘을 `_REJECTED_ATTRS`에 두되 `"0"`을 센티널로 통과시키는 설계가 같은 사실의 독립 확인이다. COM도 `LinkTextBox`/`NextTextBoxLinked`/`PrevTextBoxLinked` 3종 전부 `createSet=false`. ②**글상자에서 세로쓰기** — `hp:subList/@textDirection`(`:20-31`)인데 코퍼스 **9,667/9,667 전부 `"HORIZONTAL"`**(69파일)이고 `_document_primitives.py:1556`의 `_default_sublist_attributes()`가 그 값을 상수로 박아 방출한다(오버라이드 경로 없음). 쪽 메뉴의 `hp:secPr/@textDirection`(6.12 갭③)과는 **다른 요소**라 대응으로 셀 수 없다. ③단일 진입점 부재 — `add_rectangle(...).set_draw_text(...)` 2단 조합뿐(기능 갭이 아니라 API 표면 관찰) |
| 멀티미디어 > 동영상 | **[부분 대응]** *(기존 판정 재인용)* | 스키마 `ParaList XML schema.xml:630-665`(`AbstractShapeComponentType` 확장, 속성 4 = `videotype`(Local\|Web, required)·`fileIDRef`·`imageIDRef`·`tag`), 코퍼스 고유 표본 1(이번 71파일 census에서도 `hp:video` 1건 재확인), 코드는 **봉투 읽기**뿐이고 `fileIDRef`/`imageIDRef` 해소 코드가 `src/hwpx/` 전체 0건. 저작 없음. 액션 `InsertMovie`(setId=`ShapeObject`)는 실재. **이번 프로브 세션 이월** — 삽입 시퀀스까지는 도달했으나 저장 실패로 gold 미확보 |
| 멀티미디어 > 소리 | ✅ **[대응 없음=신규 갭] — OLE 저작 축에 흡수** | ~~[미확인]~~ **실측으로 확정.** 판정 전 4축은 전부 음성이었다: 스키마 7종 `audio` 0건(같은 grep이 `video`는 `:630`·`:634`로 정확히 잡으므로 grep 실패가 아니다) · 코퍼스 71파일 0건 · 원장 345개 요소에 `audio`라는 항목 **자체가 없음**(`video`는 있다) · 액션 965종에 `Sound`/`Wave`/`Audio`/`Multimedia` 0건. 즉 `hp:audio`라는 이름의 유일한 근거는 **우리 자신의 `INLINE_OBJECT_NAMES`(`oxml/body.py:35`) 항목 하나**뿐이었고, 도움말(`insert/wave.htm`)은 소리를 "눈에 보이지 않는 개체이므로… **응용프로그램의 아이콘으로 표시하고 소리 파일을 연결**"이라 설명하며 관련 기능 첫 항목이 [OLE 개체 넣기]였다. ✅ **실물이 도움말 쪽을 지지했다** — 삽입 결과는 `hp:ole objectType="EMBEDDED" drawAspect="ICON" binaryItemIDRef="ole1"` + `BinData/ole1.ole`이고 `hp:audio`는 **생성되지 않는다**(아래 "실측으로 확정된 계약" ③). 따라서 이 항목의 공백은 소리 전용 갭이 아니라 **OLE 저작 공백 그 자체**이며 "OLE 연결" 행과 같은 축이다 — 신규 갭으로 **중복 계상하지 않는다**(고치기 행과 같은 원칙). `INLINE_OBJECT_NAMES`의 `audio` 항목 정리 여부는 후속 결정 |
| 문단 띠 | **[대응 영역]** | **도움말이 구조를 직접 명시한다**(`insert/line.htm`): "[문단 띠]는 '두께: 1.06mm, 너비: 문단에 따라 100%, 기준 위치: 문단, 면 색: 검정, 선 종류: 선 없음'의 **사각형 개체**입니다." 신규 요소가 아니라 특정 기본값을 가진 `hp:rect`다. **코드** `doc.shapes.add_rectangle(width, height, line_color=, line_width=, fill_color=)`(`_document/shapes.py:246-274`)가 그 사각형을 저작하고, 기준 위치(`horzRelTo="PARA"`)·`flowWithText` 같은 배치 축은 드롭캡(6.12 갭②)이 이미 같은 어휘로 실한컴을 통과시킨 바 있다. 도움말 자신이 "삽입 후 [서식-개체 속성]으로 얼마든지 바꿀 수 있다"고 해 전용 구조가 없다는 것도 같은 문장이 뒷받침한다 |
| 입력 도우미 | **[스코프 밖]** *(신규 3종 기준)* | 자식 5종이 갈린다. **재인용 2종**: 상용구 = 6.14 트레인㊿ [스코프 밖] 확정(재조사 안 함) / 글자 겹치기 = [대응 영역](`add_composed_character`). **신규 3종 = 외래어 표기·로마자로 바꾸기·로마자 등록**: 도움말(`tools/loan_word.htm`, `tools/roma/roma(change).htm`) 실측 결과 셋 다 **사전을 조회해 결과 문자열을 커서 위치에 삽입/치환**하는 기능이다 — "본문의 커서 위치에 '컴퓨터(computer)'가 삽입됩니다". 삽입된 결과는 손으로 친 텍스트와 문서 구조상 구분이 안 되고(전용 필드/마커 없음) 사전·사용자 등록 로마자는 애플리케이션 설정에 산다. 상용구·자동완성·맞춤법·한글/한자 변환과 정확히 같은 부류. COM `SearchForeign`은 `createSet=true`지만 `setId=""`(빈 문자열 — 다른 항목이 실제 pset 이름을 갖는 것과 대비되는 신호) |
| 채우기 | **[스코프 밖]** | 자식은 표 자동 채우기·자동 채우기 내용 2종. **도움말**(`table/autofill/table(autofill).htm`): "표의 일부 셀에서 **규칙을 찾아** … 자동으로 채웁니다" — 산출물은 평범한 셀 텍스트다("입력된 셀과 같은 셀 속성(글자 모양, 문단 모양, 셀 모양, 선 종류)으로 나머지 셀들을 채웁니다" — 전부 이미 저작 가능한 기존 속성). 자동 채우기 목록은 한컴 사용자 설정에 저장된다. **스키마·코퍼스에 채우기 규칙 요소 없음**(`autofill` 0건). 결과 상태는 `set_table_cell_text`+charPr/paraPr 대입으로 도달 가능. **정직한 여백 하나**: 규칙 추론(수열·목록 매칭) 엔진은 core에도 automation에도 없다 — 다만 이건 편의 계산이지 OWPML 표면이 아니라 판정을 바꾸지 않는다 |
| 한자 입력 | **[스코프 밖]** | 자식 4종(한자로 바꾸기·한자 단어 등록·한자 부수/총획수·한자 새김 입력) 전부 입력 방식(IME) 변형이다. 기존 [한글/한자 변환… = 언어 도구]와 같은 축이나 이번엔 **"한자로 바뀐 텍스트가 별도 마커를 남기는가"를 실측으로 배제했다**: 스키마 7종 `hanja` 매치 8건은 전부 **언어별 축**이다 — `Header XML schema.xml:418-425`가 `hangul/latin/hanja/japanese/other/symbol/user` 언어 열거를 선언하고 `:581`/`:611`/`:674`/`:736`/`:799`의 `hanja` 속성은 글꼴·장평·자간·크기의 **언어별 슬롯**이다. 코퍼스 12,610건 전부 그 슬롯 값이고 변환 이력을 남기는 요소·속성은 없다. 즉 한자로 바뀐 글자는 처음부터 한자로 친 글자와 구조상 동일하다. COM `InputHanja`/`AddHanjaWord`/`InputHanjaBusu`/`InputHanjaMean` 전부 `setItemCount=0` |

## 서식

| 메뉴 항목 | 판정 | 근거 |
|---|---|---|
| 한 수준 증가 | **[대응 영역]** *(기존 판정 재인용)* | macOS "한 수준 증가/감소" 행 = `apply_paragraph_format(outline_level=)`를 level±1로 재호출하는 것과 동치(신규 코드 없음). 이번에 **도움말로 범위를 교차 확인**: `format/outline/outline_numbering(depth).htm`이 "최상위 1수준~최하위 10수준"이라 명시하고 코드 검증 범위가 정확히 `0 <= outline_level <= 10`(`_document/layout.py:178-186`, 0=해제)이다 — 도움말의 수준 폭과 구현 폭이 일치한다. Windows가 증가/감소를 두 항목으로 쪼갠 것뿐 |
| 한 수준 감소 | **[대응 영역]** *(기존 판정 재인용)* | 상동(같은 `outline_level` 축의 반대 방향) |
| 스타일마당 | **[대응 영역]** *(벤더 자산 경계 명시)* | **도움말**(`format/style_templates/style_templates.htm`): 용도별 스타일 묶음(논문·단행본·보고서·신문·편지글·프레젠테이션)을 고르면 "문서의 **글자 모양, 문단 모양**이 … 한 번에 바뀝니다". 문서에 남는 산출물은 `hh:style`+`hh:charPr`+`hh:paraPr` 재작성이고 신규 요소가 없다 — `header_part.ensure_style`이 그 산출물을 저작한다. **경계**: 한컴이 큐레이션한 프리셋 묶음 자체는 벤더 배포 자산이라 macOS "문서마당… [스코프 밖]"과 같은 선례로 스코프 밖이다. 엔진 능력("이 문서의 스타일 묶음을 통째로 바꿀 수 있는가")은 충족되므로 행 자체는 [대응 영역] |
| 개체 속성 | **[부분 대응]** | 자식 10탭. **도움말**(`insert/objectattribute/objectattribute.htm`)이 탭 구성을 개체 종류별 표로 주고, 실제 탭은 목록보다 3개 많다(반사·네온·옅은 테두리 포함). **대응하는 탭**: 기본(위치·크기·`textWrap`/`textFlow`/`lock` — `AbstractShapeObjectType`, `ParaList XML schema.xml:1859`) / 여백·캡션(`outMargin`+`hp:caption`) / 선(`lineShape`) / 채우기(`fillBrush` — `winBrush`/`gradation`/`imgBrush` 3종 전부, `_document_primitives.py:775-823`) / 글상자(`drawText`+`textMargin`) — 여기까지는 `add_rectangle`/`add_ellipse`/`ensure_border_fill` 축으로 저작된다. **못 채우는 범위**: ①**그림자** — `hp:ShadowType`(`:1808`, 개체 자식은 `:2367`)가 실재하고 코퍼스 2,642건·67파일로 흔하지만 우리 도형 빌더는 `objects.py:283`에서 `hp:shadow`를 **고정 기본값으로 방출만** 하고 파라미터화하지 않는다(끄기·오프셋·색 지정 경로 없음). ②**반사/네온/옅은 테두리** — `reflection`(`:1618`)·`glow`(`:1585`, 스키마 documentation이 "**네온** 크기")·`softEdge`(`:1608`) 셋 다 선언돼 있으나 코퍼스 실사용은 `glow`/`softEdge` 각 1건·`reflection` 0건이고 코드 저작 0. ③**글맵시** — `hp:textart`는 봉투 읽기 확정(저작 없음). ④**OLE 속성** — DEV-021 근거 명시 보류 그대로. 즉 공통 속성군과 도형 고유 속성은 대응, **시각 효과 탭 4종과 글맵시/OLE 탭은 공백** |

## 쪽

| 메뉴 항목 | 판정 | 근거 |
|---|---|---|
| 글자 방향 | **[대응 영역]** *(기존 판정 재인용, 이름 변형)* | macOS "글자 방향 설정…"과 같은 항목 — 6.12 트레인㊸ 갭③에서 해소(`doc.page.set_text_direction` → `hp:secPr/@textDirection`, v16 render-verified). **도움말이 적용 범위를 추가로 알려준다**(`format/vertical.htm`): 범위는 "선택된 문자열 / 특정 구역 / 문서 전체"이고 블록 지정 시 "블록을 설정한 부분이 **별도의 구역으로 설정되면서** 해당 구역에만 세로쓰기가 적용" — 세 범위 모두 결국 `hp:secPr` 단위로 귀결한다(`add_section`+`set_text_direction` 조합). 글상자·셀 내부 세로쓰기는 **다른 요소**(`hp:subList/@textDirection`)이며 별도 행에서 미대응으로 판정했다 |
| 쪽 테두리/배경 | **[대응 영역]** ⚠️ **선입견 정정** | 이 요소를 "원장에서 frozen-template(Skeleton 상수)"으로 지목한 사전 브리핑이 있었으나 **실사 결과 그렇지 않다**. 원장의 해당 항목은 `"codeWrite": "api"`(`corpusFileCount` 237, `codeRead` true)이고 frozen-template 14건 명단에도 없다. **코드 실물**: `SectionProperties.set_page_border_fill()`(`oxml/section_format.py:647-696`)이 `borderFillIDRef`/`textBorder`/`fillArea`/`headerInside`/`footerInside`+`hp:offset` 4변을 전부 쓰고 `_page_border_fill_element(page_type, create=True)`(`:612-627`)가 없으면 새로 만든다. **스키마·도움말·코드 3중 일치**: 스키마는 `pageBorderFill minOccurs=0 maxOccurs=3`(`ParaList XML schema.xml:897`), 도움말(`format/pageborder/page_border.htm`)은 "쪽 테두리/배경은 **구역 단위**로 만듭니다. 하나의 구역에는 [양쪽], [홀수 쪽], [짝수 쪽]의 **3가지**", 코드는 `page_type`(BOTH/EVEN/ODD)으로 그 3슬롯을 키잉한다 — 자식 "홀짝수 쪽 구별"까지 같은 파라미터가 커버한다. 배경 4종(색/무늬/그러데이션/그림)은 `ensure_border_fill(fill_color=/fill_image=/fill_gradient=)`(`oxml/header_part.py:956-1003`)로 배선. 코퍼스 234건·69파일. COM `PageBorder`→setId=`SecDef`도 같은 결론 |
| 현재 쪽만 감추기 | **[대응 영역]** *(기존 판정 재인용)* | macOS "감추기…"(`hide_page_elements`, `hp:pageHiding`)와 같은 항목. 이번에 **감출 항목이 스키마 속성과 1:1인지 도움말로 대조**했다: `format/hide.htm`의 감출 내용은 머리말·꼬리말·쪽 번호·쪽 테두리·문서 배경·바탕쪽 6종이고 스키마 `hp:pageHiding`(`ParaList XML schema.xml:148-163`)의 속성도 정확히 6개(`hideHeader`/`hideFooter`/`hidePageNum`/`hideBorder`/`hideFill`/`hideMasterPage`) — **완전 일치, 빠진 항목 없음**. 원장 `codeWrite=api`·Render-verified. COM `PageHiding`이 전용 setId를 갖는 것도 "문서 상태"임을 뒷받침 |
| 줄 번호 | **[대응 영역]** *(기존 판정 재인용)* | 자식 2종(표시·설정) 모두 `hp:lineNumberShape` 한 요소의 표시/파라미터다. **스키마** `ParaList XML schema.xml:793` · **코퍼스** 78건·69파일 · **원장** `codeWrite=api`·Render-verified. **코드** `doc.page.set_line_numbers(...)`(`_document/ns/page.py:573-590`) → `SectionProperties.set_line_number_shape`(`oxml/section_format.py:578-598`, `restartType`/`countBy`/`distance`/`startNumber`). 표시 토글은 `hp:visibility/@showLineNumber`(`section_format.py:508`·`:548`)가 담당. COM 둘 다 setId=`SecDef` |
| 단 설정 나누기 | **[대응 영역]** *(기존 판정 재인용, 이름 변형)* | macOS "다단 설정 나누기"와 같은 항목 — 단순 강제 분리(`hp:p/@columnBreak`, 6.12 갭④)와 "새 단 구성 시작"(`hp:colPr`/`ColumnDefType`)을 스키마가 구분해 선언하고 후자를 `add_column_definition`/`set_columns`가 이미 저작한다. 세 번째 별개 구조 없음. *(혼동 주의: 도움말 `format/columns/columns(division).htm`은 동명이 아닌 "배분 단"이라 이 행과 무관)* |
| 쪽 복사하기 | **[스코프 밖]** | **"쪽"은 OWPML에 저장되는 구조가 아니다** — 스키마 7종에서 `xs:element name="page*"`는 `pageNumCtrl`/`pageHiding`/`pageNum`/`pagePr`/`pageBorderFill` 5개뿐이고 **쪽 자체를 담는 컨테이너는 하나도 없다**(전부 쪽 관련 *설정*이다). 쪽 경계는 조판기가 계산하는 산출물이라 "한 쪽을 통째로 복사"는 편집기 세션 워크플로다. **도움말이 뒷받침**(`format/copy_page.htm`): 붙인 뒤 "쪽 번호, 구역 번호, 줄 번호가 **자동으로 업데이트**"되고 속성이 다르면 "**구역이 변경**" — 실제 문서 변화는 문단·구역 삽입이며 이미 저작 가능한 결과 상태다. COM `CopyPage` `createSet=false`. macOS "복사하기 [스코프 밖]"과 같은 부류 |
| 쪽 붙이기 | **[스코프 밖]** | 상동(`PastePage`도 `createSet=false`). 붙인 결과인 문단/구역 삽입은 `add_paragraph`/`add_section`/문서 끼워 넣기로 이미 커버 |
| 쪽 지우기 | **[스코프 밖]** | **도움말**(`format/remove_page.htm`, `remove_page_current.htm`): "현재 쪽이나 쪽 **영역을 지정하여** 지웁니다" — 대상이 쪽 구조가 아니라 그 쪽에 조판된 문단 범위다. 결과(문단 삭제)는 기존 remove 계열로 커버. COM `DeletePage`만 `createSet=true`지만 `setItemCount=0`이고 이는 "지울 범위" 대화상자 파라미터이지 문서에 남는 상태가 아니다 |

## 보안

| 메뉴 항목 | 판정 | 근거 |
|---|---|---|
| 문서 암호 변경/해제 | **[부분 대응]** *(기존 판정 재인용)* | macOS "문서 암호 변경 및 해제…"와 같은 항목. 재확인만 했다: "암호화 HWPX" 영역은 `capabilities.py:255-260`에서 `entry_points=()`·`authoring_methods=()` — **읽기 거부만 있고 저작 경로가 선언조차 없다**. 코드 전수에서 `def set_password`/`def encrypt` 계열 0건. COM은 `FilePassword`/`FilePasswordChange`/`FileRWPasswordNew`/`FileRWPasswordChange` 4종이 전부 setId=`Password`로 실재하나 우리 공백을 메우지 못한다(암호화는 패키지 레벨 변환이라 OWPML 저작과 층이 다르다) |
| 배포용 문서로 저장 | **[미확인]** → 프로브 이월 | **"저장"과 "편집"을 분리 판정했다.** 6.15 트레인이 [스코프 밖]으로 확정한 것은 **배포용 문서 암호 변경/해제**(이미 배포용인 문서의 암호 조작)이고 근거는 `FileSaveAsDRM`의 `CreateSet` null + macOS 메뉴 실측이었다. 그런데 **도움말은 저장 쪽에 대해 정반대를 말한다**(`file/send_to_mail/publish(save).htm`): "지정한 암호가 **문서 내용과 함께 파일로 기록**되고, 현재 문서는 '배포용 문서'가 됩니다", 그리고 [인쇄 제한]/[복사 제한] 두 플래그를 저장 시점에 선택한다. baseline과 **바이트 단위 동일**해서 [스코프 밖]으로 확정된 "문서 보안 설정…"과 결정적으로 다른 서술이다. **우리 축은 전부 음성**(스키마 7종 DRM/배포용 요소 0건 · 코퍼스 71파일 0건 · 코드 0건). **판정 불가 사유**: 배포용 저장이 (ㄱ)패키지 전체를 암호화 래핑하는지 (ㄴ)평문 패키지에 제한 플래그만 심는지를 가를 근거가 없다. **확인 방법**: 배포용으로 저장한 결과 파일을 먼저 zip 목록으로 연다 — 목록이 안 읽히거나 파트가 암호화돼 있으면 "암호화 HWPX"와 같은 층([스코프 밖] 확정), 평문 패키지면 baseline과 파트별 diff로 플래그·검증자 위치를 찾는다. 이번 세션 **미착수**(모달 위험으로 세션 말미 단독 실행 대상) |
| 배포용 문서 편집 | **[스코프 밖]** | **도움말**(`file/send_to_mail/publish(edit).htm`) 전문이 한 문장이다: "배포용 문서 속성은 그대로 유지한 채 문서를 **편집 상태로 만듭니다**." 문서에 새 상태를 쓰는 명령이 아니라 쓰기 암호를 확인해 현재 세션의 편집 잠금을 푸는 것 — 문서 속성(배포용)은 그대로 유지된다고 도움말이 명시한다. 대화형 편집 세션 상태다(되돌리기·모두 선택과 같은 부류). 산출 파일 자체의 구조 문제는 위 "배포용 문서로 저장" 행이 담당 |
| 개인 정보 보호 | **[미확인]** → 프로브 이월 **(최고 우선순위)** | **도움말이 "문서에 남는다"를 명시하는데 우리 축은 전부 0인 유일한 표면이다.** ①**도움말이 자매 기능과의 대비로 구조 존재를 함의한다**: 도구 메뉴의 **개인 정보 바꾸기**(`security/user_info_protection/`)는 "한 번 변경한 문자는 [되돌리기]로만 복구, 한/글을 종료하면 **복구할 수 없습니다**" — 원본이 사라지는 단순 치환이다. 반면 보안 메뉴의 **개인 정보 보호**(`security/user_info_security/`)는 "암호를 걸어… 내용을 **감추거나 복구**", "[파일-저장하기]를 실행하면 새 암호가 **문서 내용과 함께 파일로 기록**됩니다", 보호 해제 시 "`****`로 보이던 정보가 **원래 정보로** 보입니다". **원본을 복구하려면 암호화된 원문과 검증자가 파일 안에 있어야 한다.** ②**그런데 우리 축은 전부 0**: 스키마 7종에 `privateInfo`/`personal`/`encrypt` 관련 요소 0(유일한 근접 타입 `hc:KeyEncryptionType`(`Core XML schema.xml:891-903`: `derivationKey` algorithm/size/count/salt + base64 `hash`)는 **오직 `hh:trackChangeEncrpytion` 하나만 참조**), 코퍼스 71파일 0건, 코드 0건. ③**COM은 전용 pset을 확인해 준다**: `MarkPrivateInfo`·`PrivateInfoSetPassword`·`PrivateInfoChangePassword` 3종이 setId=`PrivateInfoSecurity`(`FileSaveAsDRM`의 null과 정반대 신호). **가설(검증 대상, 승격 아님)**: `KeyEncryptionType`이 재사용되고 보호 구간에 별도 마크가 붙을 것이다 — 그러나 스키마가 그 부모를 선언하지 않으므로 **스키마 미선언 요소**(DEV-027 `hp:lineseg` 부류)일 가능성이 크다. **이번 세션 결과**: 헤드리스 COM `MarkPrivateInfo` Execute가 2변형 모두 False로 돌아왔다(선택 상태를 요구하는 액션) — GUI 경로 필수로 프로토콜을 갱신하고 이월 |

## 검토

macOS 스캔에는 검토 메뉴 자체가 없었다 — Windows 표면 확장의 순수 신규분이다.

| 메뉴 항목 | 판정 | 근거 |
|---|---|---|
| 변경 내용 추적 | **[부분 대응]** | 부모(추적 자체)와 자식 2종을 함께 본다. **대응하는 부분**: 변경추적 저작은 이미 [대응 영역](`doc.tracking.insert`/`.delete`/`.replace`, Edit·Create·Render-verified). 자식 **사용자 이름 변경**도 대응 — `add_track_change(author_name=)`(`oxml/header.py:849-882`)가 `hh:trackChangeAuthor`를 이름으로 찾거나 새로 만든다(스키마 `Header XML schema.xml:1860-1868`: name/mark/color/id). **못 채우는 부분 2종**: ①**추적 on/off 독립 토글이 없다** — 상태는 `hh:trackchageConfig/@flags` bit 0인데(`header_part.py:911-916`이 `flags \| 1`로 켠다) 이건 `add_track_change`의 **부수효과로만** 켜진다. `doc.tracking`의 공개 메서드는 insert/delete/replace/add_change/changes/authors뿐이고 "변경 하나 없이 추적만 켜기"(=메뉴가 실제로 하는 일) 경로가 없다. ②**변경 내용 보호** — COM `TrackChangeProtection`의 setId=**`Password`**이고 스키마도 `trackchangeConfig`의 자식으로 `trackChangeEncrpytion`(type `hc:KeyEncryptionType`)을 선언한다(`Header XML schema.xml:56-64`) — **두 축이 독립적으로 "암호"를 가리켜 일치한다**. 우리는 `parse_key_encryption`(`oxml/header.py:1041-1063`)으로 **읽기 모델만** 갖고 저작 API가 없다. 코퍼스 실사용 0건. *(부수 확인: `hh:trackchageConfig` 오자는 DEV-026 그대로 — 이번 71파일 census도 오자 68건 / 정자 0건으로 재현)* |
| 변경 내용 표시 설정 | ✅ **[부분 대응]** | ~~[미확인]~~ **실측으로 확정 — 문서에 저장된다.** **도움말**(`review/track_changes/track_changes(options).htm`)의 설정 항목은 삽입/삭제/변경된 부분 서식·색·서식 변경 기록·변경 안내문(풍선 표시·연결선 표시·너비 지정)이다. 판정 전엔 두 갈래였다 — 뷰 토글이면 [스코프 밖], `flags` 비트면 [부분 대응]. **격리쌍 실측이 후자를 확정했다**: 표시 옵션 하나만 바꾼 전/후 저장본에서 `hh:trackchageConfig/@flags`가 **56 → 60**(bit 2 토글)으로 갈렸다. 즉 이 설정군은 문서 상태이고, 우리는 bit 0만 쓰므로 **나머지 비트에 대한 저작 여백**이 확정됐다. *(항목↔비트 전체 대응표와 너비 같은 비-불리언 값의 자리는 여전히 미해독 — DEV-011 선례대로 추측하지 않는다.)* 검토자별 색은 별개 축으로 `hh:trackChangeAuthor/@color`(RGBColorType)가 실재하고 우리 직렬화도 그걸 쓰지만(`header.py:1799-1807`), `add_track_change`가 새 저자를 항상 `color=None`으로 만들어(`:875-881`) 색 지정 파라미터가 없다 |
| 문서 이력 관리 | **[부분 대응]** | 자식 5종(버전 비교 탭·새 버전으로 저장·버전 지우기·버전 설명 보기·버전 비교). **도움말과 스키마가 필드 단위로 1:1이다**: `file/version_information/version_information.htm`의 [버전 정보] 목록 항목은 번호·날짜 및 시간·지은이·설명이고 각 버전에 [버전 정보 잠그기], 그리고 "저장할 때 버전 정보 자동 저장" 옵션이 있다. `Document History XML schema.xml`의 `HistoryEntryType` 속성은 **`revisionNumber`·`revisionDate`·`revisionAuthor`·`revisionDesc`·`revisionLock`·`autoSave`** — 여섯이 1:1로 맞는다. 본문은 `packageDiff`/`headDiff`/`bodyDiff`/`tailDiff` 4종 diff 엔트리로, 도움말의 "버전 비교 결과 부분에는 추가된 내용이나 삭제, 수정된 부분이 포함됩니다"와 대응한다. **우리 상태**: `hhs:` 10개 요소 전부 원장 `codeRead=true`·`codeWrite=none`·`corpusFileCount=0`. 읽기는 봉투가 아니라 **진짜 타입 읽기**다(`oxml/history_part.py`의 `History`/`HistoryEntry`+`DiffNode`). 다만 그 모듈 독스트링이 스스로 밝히듯 **schema-only·corpus-unverified**였다. ✅ **이번에 실물 확보** — 파트 구조가 스키마 서술과 다르다(아래 "실측으로 확정된 계약" ⑥, 신규 편차 등재). 읽기 모델은 완비, **파트 탐색과 저작이 공백** |
| 문서 비교 | **[대응 영역]** *(산출물 경계 명시)* | **도움말**(`review/compare_document/compare_document.htm`): "두 개의 문서를 비교하여 **새 편집 창**에 문서 간 다른 내용을 표시", "**읽기 전용 창**에 두 문서의 내용이 세로로 배열되어 나타납니다" — **한컴의 산출물은 문서가 아니라 앱 뷰다**. 창 자체는 [스코프 밖]. 그러나 이 메뉴의 실질(두 문서의 내용 차이 계산)은 **core에 이미 있다** — `hwpx.tools.doc_diff.doc_diff(old_source, new_source)`(`tools/doc_diff.py:93`), 보조로 `tools/ir_equality.compare_documents_semantic`. 표 계산식 3종이 automation에만 있어 계층 판정으로 갈린 것과 달리 이건 **core 자산**이라 계층 판정이 필요 없다. 차이를 문서로 내는 것(신구대조표)도 기존 저작 API 조합으로 표현 가능 |
| 새 메모 | **[대응 영역]** *(기존 판정 재인용)* | macOS 입력 메뉴 "메모"와 같은 항목(Windows는 검토 탭에도 노출). `doc.notes.add_memo`/`add_memo_with_anchor`, `hp:memo`(원장 `codeWrite=api`, Edit·Create·Render-verified, 코퍼스 24파일). 재조사 안 함 |
| 메모 모양 | **[대응 영역]** *(기존 판정 재인용)* | 같은 영역의 모양 정의 축 — `doc.styles.ensure_memo_shape(width=, line_width=, line_type=, line_color=, fill_color=, active_color=, memo_type=)`(`_document/ns/styles.py:464-495`)가 `hh:memoPr`를 만들고 `add_memo(memo_shape_id_ref=)`로 연결한다. 원장 `codeWrite=api`·59파일. **도움말 대화상자 항목과 파라미터가 대응**(`insert/memo/memo(format).htm` 계열). COM `MemoShape` setId=`SecDef` |
| 모든 메모 표시 | **[스코프 밖]** *(기존 판정 재인용)* | macOS 보기 메뉴 "메모"(표시/숨김 토글, 콘텐츠 자체는 메모 영역이 이미 대응 — 중복 아님)와 같은 항목이다. 도움말 경로도 이를 확인한다 — 이 항목의 토픽은 `view/memo/memo(expression).htm`으로 **보기 트리 아래**에 있다(새 메모·메모 모양이 `insert/memo/` 아래인 것과 대비) |

## 도구

| 메뉴 항목 | 판정 | 근거 |
|---|---|---|
| 한컴 사전 | [스코프 밖] | 언어 도구 전례(맞춤법·한자 변환·받아쓰기와 같은 분류). 도움말 `tools/dictionary/`(15토픽)는 전부 사전 창 UI·인터넷 사전 연동·환경 설정 — 문서에 남는 산출물이 없다. 스키마 `dictionary` 0건 · 코퍼스 0건 · 액션 0건. 하위 5종 전부 같은 근거 |
| 한자 사전 | [스코프 밖] | 상동. 액션은 `InputHanja`/`InputHanjaBusu`/`InputHanjaMean`/`InputPersonsNameHanja`/`AddHanjaWord`/`ConvertOptHanjaToHangul`로 실재하나 **결과는 본문 텍스트 치환**뿐 — 삽입된 한자는 손으로 친 글자와 구조상 구분되지 않는다(상용구가 6.14 트레인㊿에서 [스코프 밖] 확정된 것과 같은 논리) |
| 유의어/반의어 사전 | [스코프 밖] | 상동. 도움말 `tools/thesaurus/`(2토픽)는 낱말 대체 제안 UI. 스키마·코퍼스 `thesaurus` 각 0건, 액션 0건. 하위 "설정"은 앱 설정. **macOS 스캔이 "부재를 단정할 수 없다"로 보류했던 4건 중 하나 — 이번에 실재 확인 후 [스코프 밖] 확정** |
| 번역 | [스코프 밖] | 언어 도구. 스키마·코퍼스 `translat` 각 0건, 액션 0건. 산출물은 치환된 본문 텍스트뿐 |
| 한컴 애셋 | [스코프 밖] | **macOS "문서마당…" 전례 그대로**(벤더 프리셋 갤러리는 OWPML 속성이 아니다). 도움말 `tools/asset.htm`: 온라인에서 서식·클립아트·그리기 조각(*.drt)·글꼴을 **내려받는** 대화상자이고, 내려받은 서식은 [파일-문서마당]으로 열린다 — 애셋은 문서의 속성이 아니라 문서의 **출처**다. 코퍼스 `asset` 0건 |
| 메일 머지 | [부분 대응] — 하위 행 참조 | 상위 행. 4개 하위 중 "메일 머지 만들기/데이터 파일 만들기"는 기존 [대응 영역](`hwpx.tools.mail_merge`), "필드 넣기"가 이번에 좁혀진 항목, "라벨로 인쇄"는 라벨(`hp:label`, v11) + 인쇄(스코프 밖) 조합 |
| — 메일 머지 필드 넣기 | ✅ **[부분 대응]** — 저작 여백 1건 | **도움말이 문법을 확정했다**(`tools/mail_merge/mail_merge(mark).htm`): "커서 위치에 필드 이름이 **{{이름}}**과 같이 나타납니다" — 한컴의 표시 달기 문법은 중괄호 2겹이고, 우리 `_PLACEHOLDER_RE`(`tools/mail_merge.py:20-24`)가 받는 첫 번째 형태(`{{key}}`)와 **표면 문법이 정확히 일치**한다(우리는 `${key}`·`<<key>>`도 함께 받는다). macOS 판정 당시의 보류 사유("표시 달기 문법과 우리 placeholder의 대응은 실물 확보 후")는 이로써 문법 축에서 해소. **남은 것은 저장 형태 한 축이었다** — 스키마 `FieldType`(`ParaList XML schema.xml:2701-2717`)에 `MAILMERGE`가 실재 선언돼 있고 액션 `MailMergeInsert`/`MailMergeModify`의 setId가 `FieldCtrl`이라 한컴이 `{{이름}}`을 평문이 아니라 필드로 감쌀 가능성이 높았으나, 코퍼스 71파일 `MAILMERGE` **0건**이라 계약을 실측할 근거가 없었다. ✅ **실측으로 확정됐고**(아래 "실측으로 확정된 계약" ⑤) **그 계약대로 저작을 열었다** — `HwpxOxmlParagraph.add_mail_merge_field(name, *, cached_text=None)`(`oxml/paragraph.py:866`, 구현 `oxml/field_marks.py:283`). 즉 치환 산출물이 동등한 데 그치지 않고 **한컴 자신이 인식하는 필드**를 저작한다. 행이 [대응 영역]이 아니라 [부분 대응]인 이유는 남은 하위 2종이다 — "메일 머지 만들기"는 기존 [대응 영역]이지만 "라벨로 인쇄"는 라벨(`hp:label`) + 인쇄(스코프 밖) 조합이라 이 메뉴가 요구하는 범위를 한 진입점으로 못 채운다. 캐파빌리티는 기존 `mail-merge` 영역 승격이 아니라 **신규 영역 `mail-merge-field`**(namespace `doc.fields`)다 — 기존 영역은 등급 Edit(기존 `hp:t` 치환)이고 진입점이 모듈 함수라, 합치면 혼합 지원 영역이 된다 |
| 스크립트 매크로 | [스코프 밖] ✅ **확정** | "문서에 저장되는가, 앱에 저장되는가"의 갈림을 **도움말이 직접 답한다** — `tools/macro/macro.htm` 「참고: 매크로 내용은 시스템에 보관」: "정의된 매크로 내용은 **현재 문서와는 상관없이** 어느 문서 창에서나 쓸 수 있으며, [파일-끝]으로 한/글을 끝낼 때 **모두 시스템에 기억**되므로…". 저장 위치도 명시된다 — 꾸러미 `.HMI` 파일이 **개인 데이터 폴더** 아래에 산다. 보안 설정 쪽도 같은 방향으로 `script_setsecurity(level).htm`은 허용 오브젝트를 **레지스트리**에 등록한다고 명시한다. 3축 독립 일치 — 스키마 7종 `macro` 0건 · 코퍼스 71파일 0건 · 코드 0건. 액션은 실재하나(setId=`ScriptMacro`) **앱 기능을 구동하는 핸들**일 뿐 문서 상태가 아니다. macOS "문서 보안 설정…"·"조판 부호 지우기…"·"상용구"와 같은 부류. **macOS 보류 4건 중 두 번째 해소** |
| 차례/색인 | 하위 6종 분리 판정 — 아래 | 상위 행 |
| — 차례 만들기 | [대응 영역] *(기존 판정 재인용)* | 네이티브 목차 `add_native_toc`(`tools/toc_author.py:255`) |
| — 차례 새로 고침 | [대응 영역] | `mark_toc_dirty`(`tools/toc_author.py:239-251`)가 모든 `TABLEOFCONTENTS` 필드에 `dirty="1"`을 세운다 — 주석이 명시하듯 이것이 **실측된 재계산 트리거**(한컴이 다음 열기에서 항목·스타일·쪽번호를 전부 재생성). `add_native_toc(dirty=True)`가 기본값으로 같은 일을 한다. 액션 `MakeContents` |
| — 제목 차례 표시 | [대응 영역] *(기존 판정 재인용)* | `HwpxOxmlParagraph.add_title_mark(in_toc=True)` → `hp:titleMark ignore="1"`. 6.15 Windows COM `SetPos` 재프로브로 캐럿 문단 타겟팅 확정(DEV-044). 원장 codeWrite=`api`·Create(experimental)·Render-verified |
| — 차례 숨기기 | [대응 영역] *(기존 판정 재인용)* | 같은 요소의 반대 극성 — `add_title_mark(in_toc=False)` → `ignore="0"` |
| — 색인 표시 | ✅ **[대응 영역]** | ~~[대응 없음=신규 갭]~~ **실측 계약 확보로 해소.** 판정 시점 상태: 스키마(`ParaList XML schema.xml:209-216`) 부모 `hp:ctrl` 선택군, 속성 0개, 자식 `firstKey`/`secondKey` 둘 다 필수이면서 **무타입(`xs:anyType`)** — 키 문자열이 텍스트 노드인지 속성인지 스키마가 침묵하고 `xs:documentation`도 없다. 코퍼스 71파일 0건, 레포 전체 8,869개 hwpx 확대 재스캔도 0건. 코드는 `parse_control_element`(`body.py:980-984`) → `GenericElement` 순수 불투명 보존. **도움말이 두 키의 의미를 확정**했다(`tools/index/index(mark).htm`): [색인 표시] 대화상자의 [첫 번째 낱말]/[두 번째 낱말]이 각각 `firstKey`/`secondKey`이고 **한 단계 색인은 [두 번째 낱말]을 비워 둔다** — 빈 요소로 방출되는지 아예 미방출인지가 저작 분기점이었다. **액션** `IndexMark`(setId=`IndexMark`)로 조작 가능한 문서 상태 실재를 독립 확인. ✅ **실측이 분기를 갈랐고**(아래 "실측으로 확정된 계약" ①) 그 계약대로 저작을 열었다 — `HwpxOxmlParagraph.add_index_mark(first, *, second=None)`(`oxml/paragraph.py:906`) |
| — 색인 만들기 | [스코프 밖] | **도움말이 산출 위치를 명시한다**(`tools/index/index(make).htm`): "현재 문서 창에 **새 탭이 열리면서 색인 파일이 만들어집니다**… 색인 내용을 알맞은 모습으로 바꾸어 저장해 놓거나 현재 문서의 뒤쪽에 붙여 넣으십시오." 색인 목록은 원본 문서 안에 생기는 구조가 아니라 **별개 문서**로 산출되고 본문에 넣으려면 사용자가 붙여넣어야 한다 — TOC(`TABLEOFCONTENTS` 필드가 본문 안에 사는 것)와 근본적으로 다르다. macOS "블록 저장…"과 같은 부류(결과물이 평범한 독립 문서). 액션 `MakeIndex`의 setId가 **빈 문자열**인 것도 같은 방향의 독립 신호다 |
| 참고 문헌 | **[대응 없음=신규 갭]** — 실물 1건 확보 | **문서 안에 저장된다는 실물 근거를 특정했다.** 원장 `corpusForeignNamespaces`의 `…/officeDocument/2006/bibliography`(237파일 중 1건)의 그 파일에서: ①zip 멤버 **`Custom/bibliography.xml`**(891바이트)가 실재한다. ②루트는 **OOXML 서지 네임스페이스를 그대로 재사용**한 `<b:Sources SelectedStyle="BibStyle_APA6.xml" StyleName="APA" Version="6">`이고 자식 `<b:Source>`는 `b:Tag`/`b:SourceType`(`ConferenceProceedings`)/`b:Year`/`b:Guid`/`b:Title`/`b:Pages`/`b:Volume`/`b:ConferenceName`/`b:LCID`(1042=ko-KR)/`b:Author`(`b:NameList`/`b:Person`/`b:Last`/`b:First`) 구조다 — 도움말 `tools/bibliography/bibliography.htm`의 [출처 종류]·[언어]·[태그]·[저자 이름 편집]과 필드가 1:1로 대응한다. ③패키지 등록은 `Contents/content.hpf`의 `<opf:item id="bibliography" href="Custom/bibliography.xml" media-type="application/xml"/>` + 대응 `<opf:itemref>` 2줄. ④**본문 인용 마커는 이 파일에 없다** — `CITATION`/`Biblio`/`인용` 0건이고 `FieldType` 열거에도 서지 전용 값이 없다(출처 목록만 있고 아직 인용은 안 단 상태). **코드**: `src/hwpx` 전체 `bibliograph` **0건** — 읽기도 저작도 없고 `Custom/` 파트를 다루는 코드 자체가 없다(불투명 보존만). 액션에도 서지 액션 0건(도구 상자 전용으로 보인다). **결론**: 문서 내 저장이 실증된 실제 기능인데 엔진이 손을 안 댔다. 다만 인용 마커 계약이 미실측이라 저작은 그 프로브 이후 |
| 블록 계산 | [대응 없음, core] — **표 계산식과 별개 기능임을 정정** | **도움말이 둘을 명시적으로 가른다**(`tools/blocksum/blocksum.htm` 「참고: 표에서는 블록 계산식을 이용」): "**표 안**에서 계산할 때에는 [블록 계산식]을, **표가 아닌 본문**에서 계산할 때에는 [블록 계산]을 이용하십시오." 즉 도구 메뉴의 이 항목은 표 기능이 아니라 **본문 텍스트 블록의 합계/평균**이고, 토크나이저 계약까지 도움말이 규정한다 — "숫자와 `+`, `-` 그리고 쉼표(,)와 소수점(.) 부호만 취하고, **글자와 괄호 속의 내용은 없는 것으로 처리**". 액션도 갈린다: 본문 쪽은 `Sum`/`Average`(setId=`Sum`), 표 쪽은 `TableFormula*`(setId=`FieldCtrl`). **현 상태**: core 없음. automation의 `table_compute`는 **행/열 구조를 받아 합계·평균 행을 덧붙이는 표 모양 API**라 이 본문 블록 계산의 대체물이 아니다. 하위 2종(블록 합계·블록 평균) 동일 |
| 문서 찾기 | [스코프 밖] | **도움말이 별도 프로그램임을 명시한다**(`file/finding_files/finding_files(finder).htm`): "한/글에서는 기존의 [문서 찾기] 기능을 강화하여 **[한컴 문서찾기]를 별도의 프로그램으로 제공**합니다" — 폴더를 색인해 hwpx·hwp·cell·show·doc·xls·ppt·txt를 가로질러 검색하는 데스크톱 파일 검색기다. 현재 문서의 속성과 무관. 액션 `DocFind*`는 그 프로그램 구동 핸들 |
| 개인 정보 바꾸기 | [대응 없음, core] (계층 판정) | 도움말(`security/user_info_protection/`)이 규정하는 동작은 **되돌릴 수 없는 텍스트 치환**이다 — 「바로 바꾸기」는 선택 영역을 무조건 `*`로, 「찾아서 바꾸기」는 [개인 정보 선택 사항](전화번호·주민등록번호·외국인등록번호·전자우편·계좌번호·신용카드·IP·생년월일) 패턴만 골라 `*`로 바꾸며, "단순히 문자를 `***`로 변경했으므로" 문서에는 마커가 남지 않는다. 즉 **문서 형식이 아니라 텍스트 조작**이고, 스키마의 `PRIVATE_INFO` FieldType(`:2714`)은 이것이 아니라 보안 메뉴의 [개인 정보 **보호**](암호 기반)에 딸린 별개 메커니즘이다(코퍼스 `PRIVATE_INFO` 0건). **계층**: core에 없고 automation에 `scan_personal_info`가 있다 — 표 계산식 3종과 같은 계층 판정 패턴. 하위 2종 동일 |
| 프레젠테이션 | 하위 3종 분리 판정 — 아래 | 상위 행 |
| — 프레젠테이션 설정 | **[대응 없음=신규 갭]** — 구조 완비, 저작 경로 0 | **실물 인스턴스 특정**: 원장의 `hp:presentation`(corpusFileCount **1** · codeRead=false · codeWrite=none · observedAttributes `applyto`/`autoshow`/`effect`/`invertText`/`showtime`/`soundIDRef`)의 그 1파일에서 이 요소는 `hp:secPr`의 **마지막 자식**으로 산다(`hp:pageBorderFill` 3형제 직후): `<hp:presentation effect="none" soundIDRef="" invertText="0" autoshow="0" showtime="4294967295" applyto="WholeDoc"><hc:fillBrush>…</hc:fillBrush></hp:presentation>`. **스키마도 완전히 문서화돼 있다**(`ParaList XML schema.xml:1031-1085`, `xs:documentation` "프레젠테이션 정보"): 자식 `fillBrush` + 속성 `effect`(enum 9종 none/overLeft/overRight/overUp/overDown/rectOut/rectIn/blindLeft/blindRight, "화면 전환 효과")·`soundIDRef`·`invertText`·`autoshow`·`showtime`·`applyto`(`WholeDoc`/`NewSection`). **도움말 대화상자와 6/6 대응**(`tools/presention/present(effect).htm` + `presentation_range.htm`). **코드**: `src/hwpx`에서 `presentation`이 등장하는 곳은 `oxml/section_layout.py:113` 단 하나이고 그것도 새 구역 파생 시 **제거하는 목록**이다 — 읽기 모델도 저작 API도 없다. 액션 4종 전부 setId=`Presentation`(특히 `PresentationDelete`의 존재가 "지울 문서 상태가 있다"는 독립 증거). ✅ **이번에 GUI gold 확보** — 아래 "실측으로 확정된 계약" ④. 저작은 여전히 0 |
| — 프레젠테이션 범위 | **[대응 없음=신규 갭]** | 위와 같은 요소의 `applyto` 속성(`WholeDoc`/`NewSection`) + 구역 분할. 도움말: "배경 화면, 화면 전환 효과, 효과음 등의 속성은 **프레젠테이션 구역 단위**로 다르게 설정" — 구역은 `hs:sec`이고 `add_section`이 이미 대응하므로 갭은 구역이 아니라 그 안의 `hp:presentation` 저작 하나다 |
| — 프레젠테이션 실행 | [스코프 밖] | 전체화면 시연 모드 — 뷰어 상태(보기 메뉴 일괄 [스코프 밖]과 같은 원칙). 설정만 문서에 남고 실행 자체는 남지 않는다 |
| 글자판 | [스코프 밖] | 입력기(IME) 자판 배열 전환·언어 선택. 스키마·코퍼스 `keyboard` 각 0건, 액션 0건. 받아쓰기·자동 완성과 같은 부류. 하위 4종 전부 앱 설정 |
| COM 추가 기능 설정 | [스코프 밖] | 애플리케이션 확장(플러그인) 등록/편집 — macOS "사용자 설정…"·"스킨 설정…"과 같은 앱 설정 축. 스키마·코퍼스 `addin`/`add-in` 각 0건, 액션 0건. 등록 정보는 문서가 아니라 앱/레지스트리에 산다(스크립트 매크로의 오브젝트 등록과 같은 결론) |
| 환경 설정 | [스코프 밖] | 애플리케이션 환경설정 대화상자(하위 8탭: 편집·파일·일반·글꼴·새 문서·코드 형식·개체·기타). macOS "사용자 설정…"의 형제. **`settings.xml`이 반증이 아님을 재확인**: 6.13·6.14 트레인이 177파일 전수로 확정한 대로 `ha:HWPApplicationSetting`의 실제 구조는 `ha:CaretPosition`(177/177)과 `config:config-item-set name="PrintInfo"`(77/177)뿐이며, 환경 설정 8탭이 문서에 저장된다면 관측된 `name` 값이 하나뿐일 수 없다 |

## 표 (문맥·리본)

라이브 메뉴바에 '표' 최상위 메뉴는 없다 — 아래 항목은 캐럿이 표 안에
있을 때 뜨는 문맥 메뉴와 리본 탭의 표면이다.

| 메뉴 항목 | 판정 | 근거 |
|---|---|---|
| 표 테두리/배경 | [부분 대응] | **셀 단위와 표 단위가 다른 속성이라는 것이 도움말의 요지다**(`table/tableborder/tableborder.htm`): "[표 테두리/배경]은 **표 단위**로 적용됩니다… 이에 비하여 [셀 테두리/배경]은 **각 셀 단위**로 적용됩니다." 스키마도 두 자리를 따로 준다 — 표 단위는 **`hp:tbl/@borderFillIDRef`**(`ParaList XML schema.xml:2152`), 셀 단위는 `hp:tc/@borderFillIDRef`(`:2108`). **우리 상태**: 셀 단위는 완비(`set_cell_border_fill`/`set_cell_shading`/`set_cell_fill_image`/`set_cell_fill_gradient`, `oxml/table.py:775-885`), **표 단위는 생성 시점에 한 번 쓰고(`oxml/table.py:553`) 사후 setter가 없다**(`set_table_border_fill` 계열 전수 0건). 추가로 도움말이 이 기능의 전제로 지목하는 **셀 간격**(`hp:tbl/@cellSpacing`, `:2151`)도 생성 시 `"0"` 하드코딩(`table.py:552`)에 setter 없음이고, 코퍼스 434/434 전부 `0`이라 비-0 실사용 표본도 없다. 하위 2종 동일 |
| 표마당 | [스코프 밖] — 단, **하위 갭 1건 명시** | **문서마당 전례**(벤더 프리셋 갤러리는 OWPML 속성이 아니다). 도움말(`table/tablemadang/`)대로 표마당은 미리 만든 표 서식 묶음을 현재 표에 덮어쓰는 대화상자이고 결과는 전부 기존 어휘로 환원된다(테두리/셀 배경→`borderFillIDRef`, 글자/문단 모양→`charPr`/`paraPr`). 스키마 `tableTemplate`/`madang` 류 0건, 코퍼스 0건. **다만 [적용 대상] 축에 실제 문서 속성이 하나 있다**: 「제목 줄」은 "[셀 속성]의 **[제목 셀] 속성이 적용된 줄**"을 가리키고 이는 **`hp:tc/@header`**(xs:boolean, `ParaList XML schema.xml:2098`)다. 우리는 이 값을 `_default_cell_attributes`(`oxml/_document_primitives.py:1001`)에서 **`"0"` 하드코딩**하고 setter가 없다 — 표마당 자체는 스코프 밖이지만 **제목 셀 저작은 실제 공백**이다. *(코퍼스 실사용: `header="1"` **7/71파일**, 속성 존재 25/71.)* |
| 1,000 단위 구분 쉼표 | [대응 영역] (기존 API 조합) | **도움말이 순수 텍스트 조작임을 확정한다**(`table/table(threedigits_insert).htm`): 셀 블록 안 숫자에 "1,000단위마다 **자릿점(,)이 입력됩니다**", [자릿점 빼기]는 그 쉼표를 "**일괄 삭제**" — 결과는 셀 텍스트에 들어간 리터럴 쉼표 문자일 뿐 전용 서식 속성이 아니다(세 자리 이하·소수부·날짜 코드의 연도 제외 규칙도 전부 문자열 규칙). 액션 `TableInsertComma`/`TableDeleteComma`가 **`createSet=false`** — 설정할 문서 상태가 없다는 독립 확인. `get_table_text`/`set_cell_text` 조합으로 표현 가능. *(구분 주의: [계산식]의 「세 자리마다 쉼표로 자리 구분」은 계산 필드의 표시 형식이고 이 항목이 아니다.)* |
| 셀 블록 | [스코프 밖] | 선택 상태(F5로 잡는 셀 블록) — macOS "모두 선택"과 같은 축. 액션 5종이 **전부 `createSet=false`** — 조작할 문서 상태가 없다. 우리 API는 애초에 셀을 인덱스로 직접 지목하므로 "블록"이라는 중간 상태가 필요 없다 |
| 표 크기 조절 | [대응 영역] | 도움말(`table/table(size).htm`)의 실체는 마우스 끌기·단축키 조작이고 **바뀌는 것은 셀·표의 치수 값**이다(대화상자 경로도 [개체 속성-기본]의 [크기]에 직접 입력하는 같은 결과). 그 값은 이미 대응 영역 — `HwpxOxmlTable.set_size`(`oxml/table.py:133`)·`set_column_widths`(`:888`)·`equalize_row_heights`/`equalize_column_widths`(6.13 트레인㊻)·`hp:cellSz`. 액션 `TableResize*` 18종 전부 `createSet=false`(순수 넛지). UI 조작 방식 자체는 스코프 밖이나 결과 상태는 전부 저작 가능 |
| 표의 편집 | [대응 영역] (개념 설명 행) | 도움말(`table/table(edit).htm`)은 기능이 아니라 **개념 안내 토픽**이다 — "표의 한 칸 한 칸은 한/글의 편집 화면을 작게 축소한 것과 같습니다. 각 칸마다 본문을 편집하듯이 글자 모양과 문단 모양을 다르게 지정할 수 있으며". 우리 모델이 정확히 그렇다: `hp:tc/hp:subList`가 완전한 `hp:ParaListType`이라 셀 안에서 문단·런·스타일을 본문과 동일하게 저작한다(`oxml/table.py:259-330`). 이 토픽이 안내하는 개별 기능은 각자의 행에서 판정 |
| 표에서 세로쓰기 | **[대응 없음=신규 갭]** — `secPr`과 **별개 자리다** | **스키마 체인 확정**: `hp:tc`의 자식 `subList`는 `hp:ParaListType`(`ParaList XML schema.xml:2061-2065`)이고 `ParaListType` 자신이 **`textDirection` 속성**(`:20-32`, enum `HORIZONTAL`/`VERTICAL`/`VERTICALALL`)을 갖는다 — `hp:secPr/@textDirection`(`:1088`)과 **선언 위치가 완전히 다른 별개 속성**이다. 같은 `ParaListType`을 `drawText/subList`(`:2354`)도 쓰므로 글상자 세로쓰기와 셀 세로쓰기는 한 메커니즘이다. **도움말이 enum까지 갈라 준다**(`table/table(write_vertically).htm`): [세로쓰기]를 켜면 [**영문 눕힘**]/[**영문 세움**]을 고르는데, 스키마 `VERTICALALL`의 `xs:documentation`이 문자 그대로 **"세로 영문 세움"**(`:24-28`)이다 → 눕힘=`VERTICAL`·세움=`VERTICALALL`로 대응이 유도된다. **액션도 두 계열로 갈린다**: 셀/글상자는 `TableCellTextVert`/`TableCellTextVertAll`/`TextBoxTextVert`/`TextBoxTextVertAll`(setId=`ShapeObject`), 구역은 `ModifySecTextVert`/`ModifySecTextVertAll`/`VerticalText`(setId=`TextVertical`) — "구역 축과 별개인가"에 대한 네 번째 독립 확인. **우리 상태**: `_default_sublist_attributes`(`oxml/_document_primitives.py:1556`)가 `"textDirection": "HORIZONTAL"`을 **하드코딩**하고 셀·글상자 단위 setter가 전수 0건이다(`section_format.py:451-452`의 setter는 `hp:secPr` 전용이고 `errors.py:254`의 오류 메시지조차 `hp:secPr/@textDirection`만 지목한다 — 셀 축이 존재하지 않는다는 방증). 코퍼스는 `subList` **9,589건 전부 `HORIZONTAL`**. 6.12 트레인㊸ 갭③(구역 세로쓰기)이 연 문을 셀·글상자 축에서 반복하는 형태이고, 이미 파싱·직렬화되는 기존 요소의 스키마 선언 열거값이라 추측 위험은 낮다 |
| 셀 붙이기 | [스코프 밖] (결과는 대응) | 클립보드 붙이기의 표 안 변형 — macOS 오려 두기·복사하기·붙이기·골라 붙이기가 이미 전부 [스코프 밖]인 계열. 도움말(`table/table(paste).htm`)의 대화상자 6모드도 결과는 전부 기존 저작 어휘로 환원된다(끼워 넣기 4방향→행/열 삽입, [덮어 쓰기]→셀 텍스트+여백+`borderFillIDRef` 대입, [내용만 덮어 쓰기]→`set_cell_text`, [셀 안에 표로 넣기]→중첩표). 클립보드라는 중간 상태 자체는 문서 형식이 아니다 |

## 그림 그리기 (문맥·리본)

| 메뉴 항목 | 판정 | 근거 |
|---|---|---|
| 도형 탭 | [부분 대응] — 15개 하위 중 1건 공백 | 리본 탭 전체를 묶는 행. 도움말 `draw/drawing.htm`의 관련 기능 목록과 하위 15종을 대조하면 대부분 이미 대응한다: 도형(선·사각형·타원·arc·polygon) · 개체 선택(UI, 스코프 밖) · 개체 모양 복사/붙이기(macOS "모양 복사…" [대응 영역]) · 선 모양(`oxml/objects.py` 1300대) · 채우기 모양(`hc:fillBrush`) · 그림자 모양(`hp:shadow`, `objects.py:283`) · 본문과의 배치(`hp:pos`, `objects.py:234-254`) · 개체 묶기/풀기(`hp:container`, `objects.py:490-600`) · 순서 바꾸기(`zOrder`, `objects.py:182`) · 맞춤(`hp:pos` `horzAlign`/`vertAlign`) · 회전(`hp:rotationInfo/@angle`) · 개체 보호(`lock`, `objects.py:184`) · 같은 크기로(`resize` 조합). **공백 1건 — 글상자 연결**: 스키마가 `ParaListType`에 `linkListIDRef`/`linkListNextIDRef`(`ParaList XML schema.xml:51-52`)를 선언하는데 `src/hwpx` 전체 `linkListIDRef` **0건** — 넘치는 글이 다음 글상자로 흐르는 연결 사슬을 읽지도 쓰지도 않는다. *(단, 실 체인 사용례는 코퍼스 0건 — 위 "글상자" 행 참조. 저작을 열려면 실 체인 gold가 먼저 필요하다.)* |
| 개체 이동하기 | [부분 대응] | 이동의 저장 자리는 `hp:pos`다 — 도움말(`draw/move/drawing(move).htm`) 「정확한 위치 값 설정」이 [개체 속성-기본]의 "가로 위치/세로 위치"(기준=종이/여백/단, 값=mm)를 지목하고 이는 `hp:pos`의 `horzRelTo`/`vertRelTo`/`horzAlign`/`vertAlign`/`horzOffset`/`vertOffset`(`ParaList XML schema.xml` 1930-1940대)과 1:1이다. **우리 상태**: 이 속성들은 **삽입 시점에는 저작된다**(`insert_picture(pos_overrides=)`가 스키마의 `nonNegativeInteger` 제약까지 클램프해서 쓴다, `oxml/objects.py:715-730`) — 그러나 **이미 문서에 있는 개체를 옮기는 setter가 없다**: `HwpxOxmlShape`의 메서드 전수는 `resize`/`line_color`/`line_style`/`get_attribute`/`set_attribute`/`caption`/`draw_text` 계열뿐이고 위치 대응물이 없다(`resize`만 있고 `move`가 없는 비대칭). 액션 `ShapeObjMove*` 4종은 `createSet=false`(순수 넛지) |
| 개체 크기 조절 | [대응 영역] | `HwpxOxmlShape.resize(width, height)`(`oxml/objects.py:1320-1348`)가 대응한다 — `sz`만 고치는 게 아니라 `sz`/`orgSz`/`curSz`를 함께 갱신하고 **한컴이 실제로 그리는 타입별 지오메트리**(사각형 `pt0~pt3`, 타원 `center`/`ax1`/`ax2`, 선 `startPt`/`endPt`)를 같은 축 비율로 스케일한 뒤 `scaMatrix`를 단위행렬로 되돌린다. 도움말(`draw/drawing(size).htm`)의 「크기 조절 후의 회전 중심점」("회전 중심점이 개체 중심으로 옮겨 간다")도 구현이 반영한다(`rotationInfo`의 `centerX`/`centerY`를 새 크기의 절반으로 재설정). 축 하나가 0인 경우는 `UserWarning`으로 정직하게 알린다 |
| 개체 기울이기 | **[미확인]** — 저장 자리 미상 | **함정 주의 — 이름이 같은 다른 요소가 있다.** 스키마에 `hp:SkewType`(`ParaList XML schema.xml:1786-1801`, 속성 `x`/`y`, 각 -90~90 float)이 실재하지만 그 사용처는 **`EffectsType`의 `shadow/skew`(`:1511-1513`, "기울기 각도")와 `reflection/skew`(`:1621`) 둘뿐** — 즉 **그림자·반사 효과의 기울기**이지 개체 자신의 기울이기가 아니다. 개체 자신의 기하 자리인 `AbstractShapeComponentType`이 갖는 것은 `offset`/`orgSz`/`curSz`/`flip`/`rotationInfo`/`renderingInfo`뿐이고 **skew 속성이 없다**(`:2225-2262`). **그런데 기능은 실재한다** — 도움말 `draw/drawing(incline).htm`: [개체 속성-기본]의 [기울이기-가로/세로]에 **-89~89도**를 입력하면 개체가 기운다(글자처럼 취급된 개체는 불가). 액션 `ShapeObjShear`(setId=`ShapeObject`)도 있다. 남는 후보는 `renderingInfo`의 아핀 행렬인데 **코퍼스에 전단(shear) 표본이 0건**이다: 71파일의 전체 행렬 2,621개를 분해한 결과 `transMatrix` 744개는 전부 대각, `scaMatrix`·`rotMatrix`의 비-대각 110개는 **전부 열벡터 내적 0**(= 회전 또는 회전∘비균등스케일, 예 `e1=0.965926, e2=-0.258819` = 정확히 15°) — 전단이면 내적이 0이 아니어야 하는데 하나도 없다. 스키마 침묵 + 코퍼스 0 → 저장 자리를 단정할 근거가 없다. **이번 세션 결과**: `ShapeObjShear`는 선택된 개체를 요구하는데 COM `FindCtrl`이 이 경로에서 무효였다(우리 저작 rect 문서 자체는 정상 개봉·보존 확인). **확인 방법**: GUI 드래그로 기울인 gold를 baseline과 diff — 행렬 비-대각 원소에 `tan(20°)=0.36397`이 뜨면 아핀 인코딩, 새 요소/속성이 생기면 스키마 미선언 구조, `pt0~pt3` 좌표 자체가 다시 쓰였다면 저장되는 상태가 아니라 좌표에 굽는 일회성 변환이다 |
| 개체 복사하기 / 붙이기 | [스코프 밖] (결과는 대응) | 클립보드 계열 기존 판정 그대로. 도움말(`draw/drawing(copy).htm`)의 문서 결과는 "같은 모양의 개체가 하나 더" = 도형 요소 복제이고, 우리는 같은 저작 호출을 한 번 더 하면 된다. **주의 1건**: 요소를 복제할 때 `instid`가 새로 발급돼야 하는데 `_document_primitives.py:203`이 `"instId"`(카멜케이스)를 검사하고 실물은 `instid`(픽스처 744/0)라 이 분기가 영원히 타지 않는다 — 복제 경로를 여는 순간 중복 `instid`가 나갈 수 있다(이번 스코프 밖, 별도 티켓 후보) |
| 개체를 그림 파일로 저장하기 | [스코프 밖] | **macOS "PDF로 저장하기…" 전례 그대로** — 렌더링/래스터화는 이 라이브러리의 스코프 밖이다. 도움말(`draw/drawing(save).htm`): 선택한 개체 하나를 BMP/GIF/PNG/JPG/WMF/EMF 중 한 형식의 **그림 파일로 내보내는** 기능이다. 문서에 남는 변화가 없다 — 원본 개체는 그대로다 |

## 실측으로 확정된 계약

위 표의 [미확인]과 "계약 미실측" 상태를 갈라내기 위해, 실빌드에서 각
기능을 실제로 조작하고 그 산출물을 계약으로 고정했다. 프로브 15종 중
**9종이 완결**됐고 나머지는 프로토콜이 이번 실측으로 정밀화된 채
이월됐다. 실행 방식은 두 갈래다 — **헤드리스 COM**(액션 핸들 +
파라미터 셋 SetItem + Execute)과 **GUI 메뉴워크**(메뉴 열기 + 항목 클릭 +
키 입력 + 스냅샷).

**방법론 수확 하나를 먼저 적는다**: 6.15가 세운 "Execute 금지" 원칙은
**모달 액션에만** 해당한다는 것이 이번에 실증됐다. `CreateSet`이 null인
액션(`FileSaveAsDRM` 부류)은 여전히 대화상자를 띄우지만, **pset이 확보된
액션의 Execute는 무대화상자로 동작한다** — `IndexMark`·`SaveHistoryItem`·
`InsertCCLMark`·`MailMergeInsert`·`PresentationRange`가 전부 헤드리스로
성공했다. 또한 GUI 경로에서는 대화상자 확정이 ENTER가 아니라 **버튼 이름
클릭**이어야 하고(멀티라인 입력이 있는 대화상자에서 ENTER는 개행),
프로브는 **한 런에 1건**이어야 한다(잔류 대화상자가 후속 프로브의 메뉴
접근·타이핑을 오염시킨다).

### ① 색인 표시 — `hp:indexmark`

- 위치·구조: `hp:ctrl > hp:indexmark`, 같은 run의 `hp:t` **앞**에 삽입된다
  (`hp:titleMark` 관행과 동형).
- 키는 **자식 요소의 텍스트 노드**다 — 스키마가 `xs:anyType`으로 침묵했던
  분기의 답: `<hp:firstKey>apple</hp:firstKey>`.
- **2단계를 생략하면 `secondKey` 요소 자체가 방출되지 않는다** — 빈 요소가
  아니다. 스키마가 둘 다 필수로 선언한 것과 어긋나므로 편차로 등재했다
  (`docs/owpml-deviations.md` 참조).
- gold: `tests/fixtures/gui_probes/index_mark_first_only.hwpx`(1키),
  `index_mark_two_keys.hwpx`(2키).
- 부수 관찰: `MakeIndex`도 헤드리스로 동작하나 산출물이 색인 목록만 남고
  원문이 사라진 상태로 저장됐다 — 목록-대체 동작 의심으로 정직하게 기록만
  하고, 계약 gold는 1키/2키 두 벌이다(위 "색인 만들기 [스코프 밖]" 판정과
  모순되지 않는다).

### ② 공공누리 / CCL — 2원 구조

마크 삽입은 **두 자리를 동시에 건드린다**.

1. **문서 수준 레코드** — 헤더에
   `hh:docOption > hh:licensemark type="CCL" flag="0" lang="6"`.
2. **본문 배지** — `hp:pic` + `BinData/image1.png`(한컴이 자체 생성해 넣는
   배지 이미지, `opf:item … isEmbeded="1"`) + `href` 속성에
   `http://creativecommons.org/licenses/by/4.0/deed.ko;1;0;1` — **URL 뒤에
   `;영리;변경;` 파라미터가 접미**된다. 같은 문자열이 `hp:parameterset`
   (`name="539"` > `listParam name="623"` > `stringParam name="613"`)에도
   복제되고, 뒤따르는 안내 문장은 별도 `hp:fieldBegin type="HYPERLINK"`가
   감싼다.

macOS 트레인㊺의 "CCL 삽입은 그림+하이퍼링크+텍스트의 **조합**일 뿐"
판정은 **배지 절반만 맞았고 헤더 레코드를 놓쳤다** — 그 행은 이번에
정정했다(`docs/editor-menu-reverse-map.md`). 배지는 기존 조합으로 저작
가능하고, 문서 레코드 쪽은 이번 트레인에서 저작을 열었다 —
`doc.parts.set_license_mark(*, mark_type, flag, lang=None)` /
`doc.parts.remove_license_mark()`(`_document/ns/parts.py:220`·`:238`, 구현은
`oxml/header_compat.py:200`·`:258`). **`type`은 숫자가 아니라 문자열이다** —
스키마는 `xs:unsignedInt use="required"`로 선언하는데 실물은 `"CCL"`이므로
setter도 `str`로 받아 그대로 통과시킨다. 이건 취향이 아니라 **실제 읽기
결함을 드러낸 자리**였다: 스키마만 보고 `int`로 선언돼 있던 읽기 모델이
실한컴 CCL 문서를 `to_model()`로 읽을 때 `ValueError: Invalid integer
value: 'CCL'`로 터졌고, 저작만 열고 이걸 안 고쳤다면 **우리 출력을 우리
리더가 거부하는 상태**가 됐을 것이다(편차 레지스트리 신규 등재).
`flag`/`lang`은 관측값 `0`/`6` 하나씩뿐이라 범위를 강제하지 않는다 —
관측 1건은 열거가 아니다.

gold: `tests/fixtures/gui_probes/license_mark_ccl.hwpx`.

### ③ 소리 = `hp:ole` (`hp:audio` 아님)

삽입 실물은 `hp:ole objectType="EMBEDDED" drawAspect="ICON"
binaryItemIDRef="ole1"` + `BinData/ole1.ole`이고, **`hp:audio`는 이 빌드의
소리 삽입에서 생성되지 않는다**. 판정 단계의 4축 무근거(스키마·코퍼스·
원장·COM 전부 0)에 **실물 반증**이 더해져 확정됐다. 부수 수확으로
`hp:ole`의 **제3 표본**을 얻었고, `drawAspect="ICON"`은 코퍼스에 없던
신조합이라 "OLE 개체 속성" 행의 미실측 조각 하나가 채워졌다.

⚠️ 소리 대화상자는 파일 선택이 아니라 **녹음기**다(파일 삽입은 폴더
아이콘 경유). 그래서 `BinData`에 프로브 환경의 마이크 녹음이 담겨 원본
gold는 저장소에서 제외하고, OLE 바이트를 제로화한 스크럽본만 남겼다.

### ④ 프레젠테이션

`hp:secPr > hp:presentation effect="none" soundIDRef="" invertText="0"
autoshow="0" showtime applyto="WholeDoc"` + 자식 `hc:fillBrush` — 스키마
서술 그대로이고 `effect`는 정수가 아니라 **문자열 enum**이다. 두 표본을
대조해 `showtime`의 두 얼굴도 확인했다: GUI로 새로 만든 문서는 `0`,
실코퍼스 표본은 `4294967295`(0xFFFFFFFF) — 후자가 "미설정" 센티널로
보인다(도움말의 유효 범위는 1~600초).

**잔여**: `effect`의 비기본값과 enum 경계는 미확보다. 스키마 9값 대
대화상자 약 19항목의 차이(`blindUp`/`blindDown`·커튼·가리기 계열 미선언)가
편차인지 확인하려면 콤보 조작이 필요한데 이번 세션에서 도달하지 못했다 —
**무근거 등재를 하지 않는다.**

### ⑤ 메일 머지 표시 — 네이티브 필드 계약

`hp:fieldBegin type="MAILMERGE"` + `hp:parameters cnt="5"`:

| 파라미터 | 타입 | 값 |
|---|---|---|
| `Fiexde` | booleanParam | `1` — **공식 철자가 이렇다**(오탈자 복제 계열) |
| `Prop` | integerParam | `8` |
| `Command` | stringParam | 필드 이름 |
| `FieldType` | stringParam | `USER_DEFINE` |
| `FieldValue` | stringParam | 필드 이름 |

그리고 **캐시 텍스트가 `{{name}}` — 이중 중괄호 그대로**다. 우리
`tools/mail_merge.py`의 `{{field}}` 문법이 네이티브 캐시 관행과 정확히
일치함이 실증됐다(macOS 판정의 "표시 문법 실물 확보 후" 보류 해소).
`Fiexde`는 편차 레지스트리에 등재했다.

**저작**: `HwpxOxmlParagraph.add_mail_merge_field(name, *, cached_text=None)`이
이 5파라미터를 순서까지 복제하고 `hp:fieldEnd`까지 gold 그대로 낸다
(`add_date_field`/`add_path_field`와 같은 필드 계열). `cached_text` 기본값이
`"{{" + name + "}}"`라, 이 필드로 저작한 템플릿이 기존 `merge_template_rows`
배치 생성기에 그대로 물린다 — 네이티브 필드와 우리 치환기가 같은 문자열을
쓴다는 실측이 곧바로 배당으로 돌아온 자리다.

gold: `tests/fixtures/gui_probes/mailmerge_display_fields.hwpx`.

### ⑥ 문서 이력 — 파트 구조가 스키마 서술과 다르다

`SaveHistoryItem`은 헤드리스로 동작한다(`ItemSaveDescription=0`으로
무대화상자). 산출된 파트 구조:

- **`DocHistory/versionlog{N}.xml`** — 루트 `hhs:history`
  (`…/hwpml/2011/history`, `version="1.0.0.1"`)이고 **리비전 하나당 파트
  하나**다. 각 파트는 `hhs:historyEntry`를 **정확히 1개**만 담는다.
- **`DocHistory/historylastdoc.hml`** — 최종본 스냅샷인데 OWPML이 아니라
  **HWPML 2.91 구식 포맷**이다(`<HWPML Style="embed" SubVersion="10.0.0.0"
  Version="2.91">`, `content.hpf` 등록 media-type `application/hancomhml`).

즉 OWPML 패키지 안에 구식 포맷이 공존한다. 스키마는 `historyEntry
maxOccurs="unbounded"`인 **단일 집합 파트**를 그리지만 실물은 파트를
쪼갠다 — 편차로 등재했다. 우리 읽기 모델(`oxml/history_part.py`)은
`hhs:` 쪽은 그대로 파싱하지만 **파트 탐색이 HML 파트까지 history로
집어 들이고, `version.xml` 해소가 `versionlog0.xml`과 충돌한다**(같은
등재 항목 참조). 왕복 자체는 무손실이다.

### ⑦ 변경 내용 표시 설정

표시 옵션 하나만 바꾼 격리쌍에서 `hh:trackchageConfig/@flags`가
**56 → 60**(bit 2)으로 갈렸다 — 문서에 저장되는 상태임이 확정됐고,
판정이 [미확인]에서 [부분 대응]으로 내려앉았다.

### ⑧ 글맵시 — 대화상자 계약 (gold 미확보)

실물 조작으로 대화상자 구조까지 확정했다: 내용은 **멀티라인 텍스트영역**
(ENTER가 개행이라 확정 버튼이 아니다) · 글맵시 모양 픽커 · 글꼴 · 줄/글자
간격이고 확정은 **[설정] 버튼**이다. 삽입 직전까지 도달했으나 후속 오염으로
gold를 못 남겼다 — 재시도 프로토콜은 완성됐다. `hp:textart`의 저작 판정은
그대로 **봉투 읽기·저작 없음**이다.

### ⑨ 개체 기울이기 — 음성 결과

`ShapeObjShear`가 선택 개체를 요구하는데 COM `FindCtrl`이 이 경로에서
무효였다. [미확인] 유지, GUI 드래그 경로로 프로토콜을 갱신했다. 부수
확인 하나: 우리가 저작한 rect 문서 자체는 실빌드에서 정상 개봉·보존됐다.

### 이월 프로브

| 프로브 | 이번에 배운 것 → 다음 세션 지시 |
|---|---|
| 동영상 | 삽입 시퀀스는 도달(저장 실패) — 파일 대화상자 후 확인을 ENTER가 아니라 **버튼 이름 클릭**으로 |
| 개인 정보 보호 | 헤드리스 `MarkPrivateInfo` Execute=False 재확인(2변형) — GUI 경로 필수, 잔류 대화상자 없는 클린 상태에서 단독 실행 |
| 배포용 문서로 저장 | 미착수(모달 위험 — 세션 말미 단독으로) |
| OLE 연결(LINK) | 미착수 — 소리 실측으로 `hp:ole` 구조 이해가 깊어져 프로브 가치 상향 |
| 상용구 재확인 | 미착수(저순위 — 6.14 판정을 뒤집을 근거가 아니라 실물 재확인 목적) |

## 오토메이션 문서 편차

`docs/owpml-deviations.md`는 **OWPML 스키마 대 실문서**의 편차를 기록한다.
아래 네 건은 자리가 다르다 — **한컴 공식 오토메이션 문서 대 실빌드**의
편차다. OWPML과 무관하므로 편차 레지스트리에 넣지 않고 여기 남긴다.
양방향 대조(공식 시드 898종 프로브 → 부재 55건 정밀 분류 → 67종 재프로브)의
산물이다.

1. **공식 문서 오타 4건** — `TextArtShadowMobeToDown`/`…Left`/`…Right`와
   `ViewOptionTrackChnageInfo`는 **빌드에 없다**. 교정 철자
   (`TextArtShadowMoveTo*`, `ViewOptionTrackChangeInfo`)로 재프로브하면
   **전부 실재**한다. 즉 문서 쪽 오탈자다 — OWPML의 `trackchageConfig`
   (DEV-026)와 같은 부류이되 **방향이 반대**다(그쪽은 스키마가 정자,
   실물이 오자).
2. **문서가 주장하는 pset ≠ 실측 `setId` 18건** — 대표 3건:
   `InsertCCLMark`는 문서가 `HyperLink`라 하지만 실측은 전용 셋
   **`CCLMark`**(CCL을 "하이퍼링크 조합일 뿐"으로 본 macOS 판정을 재검토하게
   만든 첫 신호이고, 실제로 위 ②가 그 재검토를 확정했다),
   `MacroRepeatDlg`는 실측 **`ScriptMacro`**, `InsertChart`는 문서
   `OleCreation` 대 실측 **`ChartObjShape`**.
3. **`FileSaveAsDRM`** — 공식 목록에 없는데 빌드에는 실재한다(핸들 생성
   성공). 다만 `CreateSet`이 **null**이라 COM으로 조작 가능한 문서 상태가
   없다 — 6.15 트레인이 "배포용 문서 암호 변경/해제"를 [스코프 밖]으로
   확정할 때 쓴 근거이고, 이번 실측이 그것을 독립 재현했다.
4. **더미/컨트롤 전용 클래스** — 공식 PDF가 "빨간 밑줄=Dummy"로 표기한
   항목들이 텍스트 추출에서 표시를 잃는다. 프로브 실패가 그 표기를 대신
   판정했다: `HwpCtrl*` 8종(공식 범례의 "글 컨트롤 전용" 클래스 — 풀 앱에서
   실패가 정상)과 `HiddenCredits`·`SaveBlockAction`·`SearchAddress`·
   `TextBoxAlignCenterBottom`·`TrackChangeCancelNext/Prev` 등.

**같은 오탈자 계열이지만 자리가 다른 것 하나** — 메일 머지 필드 파라미터
`Fiexde`는 공식 파라미터셋 문서와 실물이 **둘 다** 이 철자를 쓴다. 그런데
이건 오토메이션 API 이름이 아니라 **문서 안에 저장되는 파라미터 이름**이라
OWPML 편차 레지스트리 소관이다(그쪽에 등재).

## 요약 — 판정 분포와 로드맵 후보

Windows 표면 판정 행 **181**(재인용 91 + 신규 90). 스킵 5건은 UI 상태다.

| 판정 | 재인용 | 신규 | 합계 |
|---|---:|---:|---:|
| [대응 영역] | 53 | 21 | **74** |
| [부분 대응] | 6 | 14 | **20** |
| [대응 없음=신규 갭] | 1 | 6 | **7** |
| [대응 없음, core] (계층 판정) | 3 | 2 | **5** |
| [스코프 밖] | 28 | 42 | **70** |
| [미확인] | 0 | 5 | **5** |

프로브 세션이 위 분포를 세 자리에서 움직였다: 색인 표시는 신규 갭에서
[대응 영역]으로, 변경 내용 표시 설정은 [미확인]에서 [부분 대응]으로,
소리는 [미확인]에서 OLE 저작 축으로 흡수됐다(중복 계상 안 함). 남은
[미확인]은 **개인 정보 보호 · 배포용 문서로 저장 · 개체 기울이기** 3건이다.

### 신규 갭 — 다음 사이클 로드맵 재료

1. ~~**색인 표시**(`hp:indexmark`)~~ ✅ 실측 계약 확보로 이번에 해소
   (`add_index_mark`).
2. **참고 문헌**(`Custom/bibliography.xml` 전용 파트) — 실물 1건 확보,
   본문 인용 마커 계약만 미실측.
3. **프레젠테이션 설정 · 범위**(`hp:presentation`) — 스키마 문서화 완비 +
   GUI gold 확보, 저작 경로 0. `effect` enum 경계만 잔여.
4. **표에서 세로쓰기**(`hp:subList/@textDirection`) — 하드코딩 상수 +
   setter 부재.
5. **OLE 연결**(`objectType="LINK"`) — 표본 0건이라 **근거 명시 보류**.
   소리 실측으로 `hp:ole` 표본이 3건이 됐으므로 프로브 가치가 올랐다.
6. **표 뒤집기** — macOS 판정의 근거 명시 보류 재인용(병합 셀·중첩표에서
   반전의 정의가 안 서고 실코퍼스 예시 0건).

### "하드코딩 상수 + setter 부재" 클러스터

같은 수리 패턴이라 한 트레인에 묶을 수 있는 저작 여백 4건이다.

| 속성 | 하드코딩 위치 | 코퍼스 실사용 |
|---|---|---|
| `hp:subList/@textDirection` (표·글상자 세로쓰기) | `oxml/_document_primitives.py:1556` = `"HORIZONTAL"` | 9,589건 전부 기본값 |
| `hp:tc/@header` (제목 셀) | `oxml/_document_primitives.py:1001` = `"0"` | `header="1"` **7/71파일** |
| `hp:tbl/@cellSpacing` (셀 간격) | `oxml/table.py:552` = `"0"` | 434건 전부 `0` |
| `hp:tbl/@borderFillIDRef` (표 단위 테두리/배경) | `oxml/table.py:553`(생성 시만) | 실사용 다수(id 2~99) |

### 저작 착수 후보 (근거 강도 순)

1. ~~**`hh:licensemark` 저작**(공공누리/CCL)~~ ✅ **이번 트레인에서 착수·완료** —
   읽기 모델이 이미 있었고 벤더 도움말이 문서 수준 레코드임을 진술했으며
   실측으로 인코딩까지 확보돼, 문서 정보(`set_document_metadata`)와 같은 결의
   head-level 저작으로 곧바로 이어졌다(`set_license_mark`/`remove_license_mark`).
   남은 것은 배지까지 묶는 단일 진입점 하나다.
2. ~~**네이티브 메일 머지 필드**~~ ✅ **이번 트레인에서 착수·완료** —
   파라미터 5종이 실측으로 고정됐고 `add_date_field`/`add_path_field`와 같은
   필드 계열이라 그대로 합류했다(`add_mail_merge_field`, 신규 캐파빌리티 영역
   `mail-merge-field`).
3. **변경추적 on/off 독립 토글** — 신규 구조가 필요 없는 순수 엔지니어링
   여백(`flags` bit 0을 부수효과 아닌 명시 API로).
4. **변경 내용 보호**(`hh:trackChangeEncrpytion`) — 읽기 모델
   (`parse_key_encryption`)이 있고 COM setId=`Password`와 스키마가 두 축에서
   일치한다. 다만 코퍼스 실사용 0건이라 gold가 먼저다.
5. **문서 이력 저작** — 읽기는 타입 읽기로 완비인데 파트 탐색이 실물과
   어긋난다. **탐색 수리가 저작보다 먼저다**(아래 후속 티켓).

### 후속 티켓 (코드·원장 정리)

- **`hp:audio` 정리** — 스키마·코퍼스·원장·COM 4축 음성인데
  `INLINE_OBJECT_NAMES`(`oxml/body.py:35`)에만 있고, 실물 반증까지
  나왔다. 봉투 읽기가 능력으로 과대 표시되는 문제의 극단 사례다.
- **문서 이력 파트 탐색** — `history` 문자열 매칭이 HML 파트를 집어 들이고,
  `version` 매칭이 `versionlog{N}`과 충돌한다(편차 레지스트리에 실측 기록).
- **`instid` 카멜케이스 오검사** — `_document_primitives.py:203`이 `"instId"`를
  보는데 실물은 `instid`다. 개체 복제 경로를 여는 순간 문제가 된다.
- **DEV-021 서술 정밀화** — "1건"은 `hp:switch` 대안 표현 조합의 표본 수이고
  `hp:ole` 자체 표본은 이제 **3건**(EMBEDDED · UNKNOWN · ICON)이다.

## 관련 문서

- [편집기 메뉴 표면 역매핑 (macOS)](editor-menu-reverse-map.md) — 이 문서가
  확장한 2차 지평. 재인용 91행의 근거 원문이 거기 있다
- [편집기 표면 인벤토리](editor-surface-inventory.md) — 순방향(영역→검증)
- [지원 매트릭스](support-matrix.md) — 영역별 등급·증거
- [OWPML 편차 레지스트리](owpml-deviations.md)
