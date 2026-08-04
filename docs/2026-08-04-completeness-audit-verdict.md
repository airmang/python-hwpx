# 엔진 완전성 도달 감사 — 판정문

> 감사자: 이 트레인에 관여하지 않은 세션 (2026-08-04).
> 브리프: `docs/2026-08-04-completeness-audit-brief.md`.
> 방법: 작업 세션의 보고서·커밋 메시지는 **주장**으로만 취급했고, 아래 모든
> 판정은 이 워크트리의 코드·원장·실파일에서 직접 재실행·재계산한 결과다.
> 코드는 수정하지 않았다(산출물은 이 문서 하나).
>
> 검증 실행 요약 — 전부 이 감사 세션에서 직접 실행:
> - 스위트: core **2281 passed** (128.6s, `HWPX_ORACLE_STRUCTURAL_ONLY=1`) ·
>   automation **1489 수집·전량 green, exit 0**(기준선 1481에서 +8; 요약행은
>   `addopts="-q"`+`-q` 중복으로 억제될 뿐 실패 0) ·
>   skill **126 passed** — 브리프 기준선 재현.
> - 원장 재생성: `coverage_ledger.py --check` → **in sync** (결정론 재현 ✓).
> - 하한 재계산: 관측 228 중 write=none **70** · read=none **56** · frozen **28**
>   — JSON에서 재현 ✓. 단, 이 수치의 **의미**는 §3에서 기각된다.
> - 실파일 재센서스: hwpxlib 코퍼스 47 + 사설 실파일 72 = 116파일(집 파싱
>   가능 87)의 **전 XML 파트·전 네임스페이스**를 직접 스캔(스크립트는
>   스크래치, 원본 무수정).
> - 런타임 검증: 6.0 표면 실행(스타일 이름 오타·section=0·add_heading·
>   dangling id 9999·legacy shim 경고), `ensure_run` 방출 XML 직접 덤프.

## 요약 (TL;DR)

| 판정 | 결론 |
|---|---|
| **A. 6.0 표면이 갭을 담을 그릇인가** | **블로커 없음 — 출하 가능.** 갭 154개(70+56+28) 전수를 사상한 결과, 기존 표면의 재배치·시그니처 파괴 없이 못 얹는 사례 **0**. 출하 전 권고(비블로커) 3건은 §1.4. |
| **B. 갭 지도** | 원장 하한 너머 실갭은 **기능군 15개**로 정리(§2). 최대 단일 갭 축은 요소가 아니라 **글꼴 선언·탭 정의·개체 내부 텍스트** 3군. |
| **원장 자체** | **측정기로서 불합격.** 모집단·분류기 양방향 오류를 실증(§3). 70/56/28은 하한도 상한도 아닌 **양방향 오차를 가진 추정치**다. 다음 사이클 최우선 = 원장 신뢰 회복. |
| **"엔진으로서 완전해졌다"** | **기각.** 단, 기각의 근거는 갭의 존재(그건 6.x로 채우면 된다)가 아니라, (a) 방향 문서 Q3 게이트("전 파일 존재·코드 무지 요소 = 0")가 자기 원장 기준으로도 미달이고(§4-R1), (b) 그 원장 자체가 완전성을 **측정할 수 없는 상태**라는 것이다(§3). "완전성 **프로그램의 뼈대**(표면·원장·레지스트리·왕복 하니스)가 섰다"가 정확한 주장이다. |

---

## 1. 판정 A — 릴리스 블로커: 없음

### 1.1 판정 기준

브리프 그대로: 갭의 존재는 블로커가 아니다. **어떤 갭을 얹으려 할 때 6.0
표면의 재배치·시그니처 파괴(=7.0 소환)가 필요해지는가**만 본다.

### 1.2 표면의 실체 (전부 런타임 재확인)

- 루트 `vars(HwpxDocument)` 공개 = **34** (설계 일치). 네임스페이스 11종
  실재·위임 확인(`_document/ns/*.py`).
- 반환 규약: add_* 전부 라이브 도메인 객체/모델 타입 주석 — `dict`/`tuple`/
  스칼라 0건을 ns 모듈 grep으로 확인. 결과 페이로드는 `@dataclass(frozen=True)`
  + `to_dict()`, 라이브 객체는 `__slots__` 클래스.
- typed error: `HwpxValueError/TypeError/LookupError/StateError` + kebab
  `ERROR_CODES` 레지스트리 실재. 런타임 실측: `add_paragraph(style="개요1")` →
  호출 시점 `HwpxLookupError(style-not-found, closest=['개요 1','개요 10'])`;
  `section=99` → `section-not-found`; **`style=9999`(dangling 숫자 id)도 거부**
  — 설계서 §3.1이 "무음 성공"으로 기록한 5.8.0 결함이 6.0에서 닫혀 있다
  (설계 문서보다 구현이 낫다).
- 이주 완충: legacy shim 79종이 위임+`DeprecationWarning`(행선지 포함),
  `doc.set_header_text("x", section=0)`이 **경고 내며 동작**(§1.6의 서드파티
  실물 결함이 실제로 낫는 것 확인).

### 1.3 갭 154개 전수 사상 결과

154개(write-none 70 + read-none 56 + frozen 28, 중복 라벨 포함)를 기능군으로
묶어 수용 표면에 사상했다. 전 항목이 다음 4개 **가산(additive) 경로** 중
하나로 수렴하며, 예외를 찾지 못했다:

| 가산 경로 | 대상 예 | 왜 minor로 충분한가 |
|---|---|---|
| ① 라이브 객체에 속성/서브객체 추가 | `hp:caption`→`Table`/`InlineObject`의 `.caption`, `hp:drawText`→`Shape`의 텍스트 컨테이너 접근자, header 전수 4종→`parts.headers[i]` 속성 | `Shape`(`oxml/objects.py:424`)·`Table`·`HeaderPart` 전부 얇은 라이브 뷰 — 필드 추가는 기존 소비자 무영향 |
| ② 네임스페이스에 메서드 추가 | markpen 저작→`doc.text`/`styles`, `newNum`/`pageHiding`→`doc.page`, 글꼴 등록→`doc.styles.ensure_font` | 네임스페이스 멤버는 루트 락(34) 밖 — 락 재생성 불필요 |
| ③ 기존 `ensure_*`/`apply_*`에 kwarg 추가 | `hh:tabItem`(탭 정의)→`apply_paragraph_format(tab_stops=…)`, `hc:imgBrush`→`ensure_border_fill(fill_image=…)` | `ensure_run`이 이미 18개 keyword-only kwargs — kwarg 추가는 하위호환. 결과 dataclass 필드 추가도 기본값 패턴 선례 있음(`FieldFillResult.fit=None`) |
| ④ 파트 접근자 추가 | `settings.xml`(ha)→`doc.parts.settings`, masterpage/history 시맨틱 승격 | `PartsNamespace`는 현재 4멤버 — 추가는 가산 |

브리프가 특정한 5개 요소의 개별 판정:

| 요소 | 빈도 | 착지 | 파괴 필요? |
|---|---|---|---|
| `hh:tabItem` (39) | 문단 탭 정의 | ③ `styles.apply_paragraph_format(tab_stops=…)` + `ParagraphProperty` 모델 확장(읽기) | 아니오 |
| `hp:drawText` (16) | 도형 안 텍스트 | ① `Shape`에 컨테이너 접근자 — `Shape`는 현재 평면 래퍼(attributes·resize·line_*)라 컨테이너 표현이 **없지만**, 추가가 기존 멤버와 충돌하지 않음 | 아니오 |
| `hh:layoutCompatibility` (166) | 호환성 설정 | ① `parts.headers[i]` 속성 또는 ④ 신규 접근자 | 아니오 |
| `hp:caption` (6) | 개체 캡션 | ① 라이브 객체 관계 속성 | 아니오 |
| `hc:imgBrush` (8) | 이미지 채우기 | ③ `ensure_border_fill` kwarg + `BinaryItem`(media) 연계 | 아니오 |

반환 규약·오류 좌표계의 확장성도 직접 확인했다: frozen dataclass는 소비자가
생성하지 않고 라이브러리만 생성하므로 **기본값 있는 필드 추가 = minor**;
`to_dict()` 키 추가는 additive JSON(단 automation의 계약 스냅샷이 흔들리면
그쪽 minor로 흡수 — 이번 트레인의 automation 7.0.0이 도구 표면 무변경
128/136/29 + 플로어 전진만으로 계약 해시를 옮긴 것이 그 증거다.
`hwpx-mcp-server-s120/CHANGELOG.md` 7.0.0 절, 직접 확인); `ERROR_CODES`는
문자열 레지스트리라 코드 추가 = additive.

### 1.4 출하 전 권고 (블로커 아님 — 구분 명시)

1. **core 내부가 자기 legacy shim을 호출한다.** automation의
   `pyproject.toml:133` filterwarnings가 실증: `hwpx._document._legacy` 경유
   경고를 `hwpx.form_fit.measure`·`hwpx.ingest.hwpx_converter` 출처로 ignore
   처리 중. 7.0에서 shim을 지울 때 이 내부 호출들이 함께 안 고쳐지면
   **자기 파괴가 예약**된다. 6.x 중 정리 권고(외부 계약 무관 — 블로커 아님).
2. **원장의 공개 숫자가 틀렸다(§3).** 커버리지 원장은 "공개가 도약"인
   산출물인데, 지금 상태로 6.0 휠·gh-pages에 실리면 **거짓 숫자를 공개**하는
   것이 된다 — Q1이 복구한 진실 축의 재위반. 원장 문서에 알려진 오차를
   명시하거나 분류기를 수리한 뒤 공개할 것.
3. **설계 게이트 §7.4와 구현의 드리프트.** "루트 34+네임스페이스 11의 모든
   공개 시그니처가 model/objects 이름만" 게이트가 실제 테스트
   (`test_engine_surface_6_0.py:329`)에서는 **document.py의 신규 이름에만**
   적용된다. `ns/parts.py:44` 등은 `HwpxOxmlHeader` 리터럴을 노출(모델 별칭과
   동일 클래스라 실계약 위반은 아님 — 문서·게이트 문구 정합만 필요).

루트 ≤35 게이트는 여유 1칸(34/35)이다. settings/compat류가 1급 네임스페이스를
요구하면 마지막 칸이 소진된다 — 자기 정책이라 사용자 파괴는 아니지만,
"게이트 개정 없이 담을 수 있는 신규 1급 축은 1개"임을 기록해 둔다.

---

## 2. 판정 B — 갭 지도 전수 (다음 사이클의 입력)

원장 하한(70/56/28)에서 §3의 허위 갭을 걷어내고, 요소 너머 기능군 관점을
합친 **실갭 지도**. 빈도는 census(166 실문서) 파일수. "왜 아직"은 코드·스펙
근거로 재분류했고, 작업 세션의 "의도적 보류" 주장 중 재검증에서 살아남은
것만 그렇게 표기했다.

| # | 기능군 | 핵심 요소(빈도) | 현재 표면 | 수용 표면(§1.3 경로) | 난이도 | 왜 아직 |
|---|---|---|---|---|---|---|
| 1 | **글꼴 선언·대체** | `hh:fontfaces`/`fontface`/`font`(166 frozen)·`substFont`(27) | Skeleton 고정 글꼴만. 새 글꼴 등록 API 없음 | ② `styles.ensure_font` | 중 | 미착수. `font=` kwarg가 fontRef만 만지고 선언부는 박제 |
| 2 | **문단 탭 정의** | `hh:tabItem`(39)·`tabPr`(166 frozen) | 없음(단어조차 무지 — grep 0) | ③ + `ParagraphProperty` 확장 | 중 | 미착수 |
| 3 | **도형 안 텍스트** | `hp:drawText`(16)·`textMargin`(16)·`hp:text`(2) | 없음. `markdown_export`는 명시적으로 건너뜀(주석) | ① Shape 컨테이너 | 중~상 | 미착수 |
| 4 | **개체 캡션** | `hp:caption`(6)·`label`(4) | 삭제 휴리스틱만(`table_patch.py:1781`) | ① 관계 속성 | 중 | 미착수(S-114 axis 24 B/F 후보 그대로) |
| 5 | **형광펜 저작** | `markpenBegin/End`(5) | 읽기만(`object_finder`·`text_extractor`) | ② run 마크 저작 | 중 | 미착수(S-114 axis 23) |
| 6 | **채우기 심부** | `hc:imgBrush`(8)·`gradation`(3)·`color`(3)·`alpha`(1) | 단색 fill만(`ensure_border_fill(fill_color=)`) | ③ | 중 | 미착수 |
| 7 | **곡선·다각형·연결선 저작** | `polygon`(7)·`hc:pt`(7)·`curve`(1)·`connectLine`(2)·`arc`(1)·`startPt/endPt`(2)·`controlPoints`(1) | 읽기 일부(polygon·curve·arc·connectLine read=True) + `add_raw` 탈출구 | ② `shapes.add_polygon` 등 | 상 | **의도적 보류 재검증 통과** — S-114 axis 8 "F 정직 표기", 문서화된 미지원. 단 빈도 합산(폴리곤군 ≈7~10%)은 라디오(2/166 컷) 대비 유의미 — 보류 근거를 빈도 컷으로 쓰려면 재계산 필요 |
| 8 | **문자 서식 의미 요소 잔여** | `hh:supscript`(12)/`subscript`·`emboss`/`engrave`(재센서스 1)·`outline`(값 설정 불가) | **부분 허위 갭**: ratio(장평)·spacing(자간)은 이미 저작됨(§3-C3). script="sup"은 offset(-30)+relSz로 **시각 등가**만 방출, `hh:supscript` 요소는 미방출(직접 덤프 확인) | ③ ensure_run 확장 | 하 | 부분 미착수. "첨자 지원"의 실체는 offset 근사 — 실한컴 gold와 요소 수준 대조 필요 |
| 9 | **메모 모양 정의** | `hh:memoPr`(13) | 조회만(`styles.memo_shapes`) — mint 없음 | ② `styles.ensure_memo_shape` | 하 | 미착수 |
| 10 | **쪽번호 제어 심부** | `newNum`(12)·`pageHiding`(10)·`titleMark`(1) | `set_page_number`만(autoNum류) | ② page ns | 중 | 미착수 |
| 11 | **필드 파라미터·양식개체 잔여** | `parameterset`/`booleanParam`/`listParam`(4)·`comboBox`(1)·`radioBtn`(2)·`btn`(1)·`listItem`(1) | CLICKHERE/HYPERLINK/TOC/CROSSREF만 시맨틱. 파라미터셋 범용 모델 없음 | ①+② fields ns | 중 | radioBtn·btn = **오너 결정 보류 재검증 통과**(방향 문서 §6, 빈도 2/166 컷) — 나머지는 미착수 |
| 12 | **개체 시각 효과** | `effects` 계열: `glow`/`reflection`/`softEdge`/`shadow`/`skew`/`scale`/`rgb`…(각 1) | 없음 | ① effects 서브객체 | 상 | 미착수·저빈도 — 후순위 타당 |
| 13 | **문서 옵션·호환성** | `layoutCompatibility`(166)·`compatibleDocument`/`docOption`/`linkinfo`(166 frozen)·`metaTag`(68) | 전무(무지 4종 포함) | ①/④ | 하(읽기)~중(저작) | 미착수. **166/166 요소가 여전히 code-blind로 남은 유일 군** |
| 14 | **비주류 개체** | `ole`(4)·`container`(8)·`video`(1)·`textart`(1)·`dutmal`(1)·`compose`(6)·`masterPage`(1)·`presentation`(1) | 읽기 일부(ole·container·textart·video read=True)·저작 없음 | ①② | 상 | §7.5 빈도 대기 — 재검증 통과(합리적 보류). 단 `compose`(6)·`container`(8)는 컷 경계 위 |
| 15 | **파트 계층 잔여** | `hhs:*` 이력(10요소)·`hm:*` 바탕쪽·`hv:HCFVersion`·`ha:*` settings | raw 파트 접근만(`parts.histories` 등)·**ha는 모집단 밖** | ④ | 중 | 미착수 + census 맹점(§3) |
| — | (기능 축) 차트 종수 | ChartML 전수 대비 | core=임의 chartML 수용(kind 무관) · automation 생성기 = **bar/line/pie 3종** | automation 확장 | 중 | 빈도 근거 없음 — 시장 신호 대기 타당 |
| — | (기능 축) 문서 병합·비교 | — | 없음 | 신규 | 상 | 실코퍼스 근거 0 — 보류 타당 |
| — | (기능 축) 배포용·암호화 | — | fail-closed 거부(capabilities 매트릭스 등재) | — | — | **의도적 미지원 재검증 통과**(정직 표기 확인) |

**다음 사이클 제안 순서** (빈도 × 이번 감사 실증 × 그릇 준비도):

1. **원장 수리**(§3 — 측정기 없이는 이후 전부가 다시 주장이 된다):
   분류기 3결함 수리 + census 재구축(전 파트·전 네임스페이스·생성기 보존).
2. **글꼴 선언**(#1): 전수-등장 축이면서 `font=` kwarg가 이미 있는 표면과
   바로 이어진다.
3. **탭 정의**(#2): 39/166, 문단 서식의 마지막 큰 구멍.
4. **문서 옵션·호환성 읽기 노출**(#13): "무지 0" 게이트를 실제로 닫는 작업.
5. **도형 텍스트 + 캡션**(#3·#4): 읽기 충실도(추출·검색)에 직결.
6. 이후: #5 형광펜 → #6 채우기 → #9 메모 모양 → #10 쪽번호 심부.

---

## 3. 원장 자체의 결함 — 측정기로서 불합격 (별도 절)

원장의 **결정론은 재현됐다**(`--check` in sync). 문제는 결정론이 아니라
**정확도**다. 세 층 전부에서 실증했다.

### C1. 모집단(census)이 부분적이다 — "실코퍼스 등장 요소 전수 = 228"은 거짓

- census(`docs/_extra/element-census.json`)는 S-114 저작 충실도 감사용으로
  **hp:/hh:/hc: 요소만** 센서스했다(spec 056 방법절에 명시). 원장이 이를
  "실코퍼스 전집"으로 승격하면서 다음이 모집단·빈도축 밖으로 빠졌다:
  - **재센서스 실증**(실파일 116, zip 파싱 가능 87): `hs:sec` **87/87
    (100%)** — 원장 기록은 빈도 0. `hv:HCFVersion` **87/87** — 원장에 항목
    자체가 없음(2024 스키마는 `hv:version`을 선언하나 실문서 어휘는
    `HCFVersion` — 이 어휘 불일치는 그 자체로 편차 레지스트리 후보인데
    원장이 삼켰다). `ha:HWPApplicationSetting`/`ha:CaretPosition`(settings.xml)
    **87/87** — 네임스페이스 통째로 모집단 밖.
  - 실파일 1건에서 **OOXML DrawingML 차트 파트**(`drawingml/2006/chart` 등
    4개 외부 네임스페이스)와 `hancom.co.kr/hwpml/2021/extended`·
    `schemas.haansoft.com/office/8.0` 임베드 발견 — 원장 어디에도 없음.
  - census의 `files: {real: 166, unknown: 84}` — **84개 파일이 제외**된 채
    분모가 166이다. unknown의 정의·목록은 어디에도 없다.
- **census 생성기가 보존되지 않았다.** 레포 전체 grep에서
  `real_element_filecounts`를 만드는 코드 0건 — 세션 일회성 코드였다.
  원장 docstring의 "4개 입력에서 결정론적으로 재산출" 주장에서 입력 #2는
  **재현 불가능한 스냅샷**이다.
- spec 056은 "요소·**속성** 출현 빈도"를 약속했으나 census JSON에 속성 축은
  없다 — 원장도 요소만 센다. 속성(예: charPr의 수십 개 속성값)은 완전성
  정의의 절반인데 측정 자체가 없다.

### C2. 분류기의 write 축 — 양방향 오류 실증

- **위음성(실제 저작 가능 → none/frozen 오판)**:
  - `_WRITE_MARKERS`에 `etree.Element(`가 없다(`ET.Element(`/`LET.Element(`만).
    `oxml/body.py`(14곳)·`header.py`가 lxml alias로 방출하는 요소는 전부
    안 보인다. 실증: **`hp:insertBegin/insertEnd/deleteBegin/deleteEnd`가
    write=none으로 집계** — 실제로는 2.17.0에 출하되고 실한컴 COM으로
    검증된 `add_tracked_*`가 `body.py:881`
    `etree.Element(_qualified_tag(mark.tag, mark.name))`로 방출한다. 태그는
    f-string 런타임 조립(`f"{normalized}{'Begin' if …}"`, `body.py:303`)이라
    문자열 매칭 자체가 불가능한 부류다.
  - 태그가 함수 인자로 넘는 자리(자인한 한계): `footNotePr`/`endNotePr`는
    `section_format.py:875-909`의 실제 setter가 안 보여서, **독스트링이
    우연히 태그를 언급한 덕에** api로 "맞게" 집계됐다 — 맞는 값, 틀린 근거.
  - `hh:ratio`(장평)·`hh:spacing`(자간): **frozen으로 집계됐지만 실제 저작
    가능** — `ensure_run(ratio=90, letter_spacing=-5)` 실행 후 방출 charPr
    XML에서 값 설정을 직접 확인했다(`document_parts.py:281-283`이
    `"ratio"`/`"spacing"`을 함수 인자로 전달 — 같은 한계 부류).
- **위양성(주석·독스트링이 만든 커버리지)**: 주석·베어 문자열을 제거하고
  원장을 재계산하면 **13개 요소의 분류가 뒤집힌다**
  (codeWriteApi 134→123, codeRead 192→186). 뒤집힌 것 중 `hp:footNotePr`/
  `endNotePr`(166/166)·`hp:header`/`footer`·`hp:footNote`/`endNote`가 포함 —
  즉 **원장의 write=api 판정 중 최소 11건의 근거가 비코드 텍스트**다.
- **"write=api ≠ 독립 API"**: 차트 내부 요소(`hc:ax1` 등 corpusOnly 38의
  다수)는 add_chart의 고정 템플릿 방출인데 api로 집계된다. 원장 md의
  워크리스트 정의("독립적으로 만들거나 편집할 API가 없는")와 분류기의 실측
  단위가 다르다.

### C3. read 축 — 같은 부류의 위음성

`insertBegin` 4종은 `parser.py:39`가 명시 등록하는데 read=False로 집계된다
(등록 루프가 f-string 태그 조립 관용구가 아니라서 loop-resolver도 못 잡음).
ratio/spacing도 동일. 따라서 **read=none 56에도 허위 갭이 섞여 있다**.

### 결론

70/56/28은 "작업 세션이 이미 인정한 갭"으로서의 방향성은 옳지만, **하한이
아니다** — C2 위음성은 갭을 부풀리고(C2-위양성·C1은 갭을 감춘다), 두 오차가
상쇄된다는 보장이 없다. 이 원장을 CI 게이트·공개 산출물로 쓰려면:

1. `_WRITE_MARKERS`에 `etree.Element(` 추가 + 함수-인자 태그의 호출부 추적
   (또는 해당 요소의 명시 화이트리스트에 근거 링크).
2. 주석·독스트링을 스캔 전에 제거(이번 감사의 재계산 방식 그대로).
3. census 재구축: 전 파트(version/settings/masterpage/history/패키징)·전
   네임스페이스·임베드 외부 XML까지, **생성 스크립트를 레포에 보존**하고
   unknown 84의 처분을 명시.
4. 속성 축 추가(최소한 "미측정"을 원장 문서에 명시).

---

## 4. 작업 세션 주장 재검증 결과

### 반증에 성공한 것 (있는 그대로)

- **R1. "실코퍼스 전 파일에 존재하는데 코드가 단어조차 모르는 요소 → 0"
  (Q3 게이트, 태스크 #28·#31 "박제 개방" 계열 주장).** 명명된 7종
  (pageBorderFill·footNotePr·noteLine·lineNumberShape·visibility·hh:style 등)의
  개방은 실재한다(커밋 a5116b5·f01bf57 + v4 스트라타 검증). 그러나 게이트의
  **기준 자체**로는 미달: `hh:layoutCompatibility`(166/166)가 여전히 코드
  전체 grep 0건이고, 원장 기준 read=none·166/166 요소가 5개 남아 있다
  (그중 ratio/spacing은 C2 허위 갭이지만 layoutCompatibility는 진성).
  census 맹점의 `ha:*`(100%)·`hv:HCFVersion`(100%)까지 넣으면 "전 파일
  존재·코드 무지"는 0이 아니라 **최소 3계열**이다.
- **R2. "커버리지 원장 = 손으로 쓴 지원 주장이 아니라 기계 재산출"** —
  결정론은 참이나 **측정 정확도가 불합격**(§3 전체). 특히 "4개 입력에서
  재산출"의 입력 #2(census)는 생성기 미보존으로 재현 불가.
- **R3. "왕복 충실도 — 실한컴이 저장한 문서를 우리가 읽고 다시 써서
  실한컴이 다시 열기"(Q4 게이트, 태스크 #29 "왕복" 주장).** 실측된 것은
  픽스처 **64건의 sha 대조**(byte-identical 11 + zip-container-only 53,
  `specs/064/evidence/roundtrip-v1-manifest.json`)뿐이다. **"실한컴이 다시
  열기" 관찰은 0건** — 왕복 산출물은 openrate v4의 모집단(authored-* 스트라타)
  에 없다. "코퍼스 전건"도 아니다(census 166도, 야생 476도 아닌 레포 픽스처).
  구조 왕복 하니스로서는 실재하나, 방향 문서가 정의한 게이트로는 미충족.
- **R4. "corpus v4 170/170 실한컴"의 함의** — 수치는 참이고 기록도 정직
  (hancom_build 12.0.0.3288·음성 대조군 3/3 거부·scopeNote 명시)하나,
  모집단은 **우리가 만들 수 있는 것의 스트라타**다. 완전성 증거로의 인용은
  기각(브리프 경고 그대로). 참고: v4 스트라타의 요소별 "실한컴 수용"이
  원장의 `verificationBasis`로 **환류되지 않아**, 원장의 renderVerified
  47은 support-matrix 산문 근사 그대로다 — 두 산출물이 서로를 모른다.
- **R5. 편차 레지스트리 "every probe executed"(커밋 ab76077 문구).** 구조
  프로브 17종의 실행 산출물(`probes/output/*.hwpx`)은 실재하나, 레지스트리
  자신이 **렌더·의미 확인 3건을 pending**으로 남겼다(DEV-005 의미·DEV-012
  렌더·DEV-016 경계 + DEV-010 크래시 재현). "모든 프로브 실행"은 "모든
  구조 프로브 실행"으로 읽어야 정확하다. 게이트(≥15건·4필드) 자체는 충족.

### 반증을 시도했으나 실패한 것 (주장이 검증에서 살아남음)

- Q2 게이트 전부 실측 충족: 루트 34(≤35)·반환 1종·스타일 이름+호출 시점
  typed error(+제안)·`add_heading` 실재·`section=0` 수용(31경로 파라미터화
  테스트 실재)·문서 예제 standalone **71**/117(≥60)·python-docx 비교표
  실측+지는 칸 5행 명시·oxml 티어 모순 해소(model.py 별칭+allowlist 락).
  일부는 설계보다 낫다(dangling style id 거부).
- 스위트 3종 기준선 재현: core 2281 · automation green · skill 126.
- 편차 레지스트리 17건의 **구조적 사실들은 전부 독립 재검증 가능한 근거**
  (스키마 파싱·census·코드 라인)를 인용하고 있고, 스팟체크(DEV-004 오자
  방출 `header_part.py:802`, DEV-015 manifest 누락 `package.py:714`)가 일치.
- automation 7.0.0의 "도구 표면 무변경·플로어 전진만" — CHANGELOG 주장과
  filterwarnings 구성·pin(`>=6.0.0.dev0,<7`)이 정합. 6.0 이주가 MCP 계약을
  깨지 않았다는 주장은 지지된다.
- "라디오/명령단추 보류"(빈도 컷)·"배포용/암호화 fail-closed"·"곡선류 F
  정직 표기" — 전부 코드·문서에서 주장대로 확인.

---

## 5. 최종 판정

**A: 6.0은 출하해도 된다.** 갭 154개 중 6.0 표면의 재배치나 시그니처 파괴
없이는 못 얹는 사례를 찾지 못했다. 표면은 네임스페이스(루트 락 밖 확장) +
라이브 객체(속성 추가) + keyword-only kwarg + 문자열 코드 레지스트리로
일관되게 **가산 확장** 형태다. §1.4의 권고 3건은 출하 전 처리가 바람직하나
블로커가 아니다.

**B: "엔진으로서 완전해졌다"는 오늘 참이 아니다.** 참인 주장은 이것이다 —
"완전성을 **측정하고 채워 나갈 구조물**(34-표면·원장·편차 레지스트리·왕복
하니스·v4 파이프라인)이 섰고, 그 측정기가 첫 실측에서 자기 오차를 드러냈다."
다음 사이클의 1번은 기능 추가가 아니라 **측정기 수리**다(§2 제안 순서).
측정기가 맞아야, 그다음 "실문서에 있는 것을 못 다루는 상태 = 0"이라는
방향 문서의 완전성 정의에 도달했는지를 **주장이 아니라 기계가** 말할 수 있다.
