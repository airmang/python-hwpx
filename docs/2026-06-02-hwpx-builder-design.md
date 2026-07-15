# HWPX Builder 설계 스펙 (docx-js급 생성 표현력)

- 상태: 설계 확정 (브레인스토밍 완료, 구현 계획 작성 대기)
- 작성일: 2026-06-02
- 범위: cross-stack (`python-hwpx` → `hwpx-mcp-server` → `hwpx-skill`)
- 관련 공개 문서: [`schema-overview.md`](schema-overview.md), [`usage.md`](usage.md)

---

## 1. 목표

docx 스킬이 `docx-js`로 누리는 경험 — **선언형·조립형 코드로 폭넓은 문서를 신뢰성 있게 생성** — 을, 검증된 `python-hwpx` 엔진 위의 새 빌더 레이어 `hwpx.builder`로 재현한다.

에이전트가 자연스러운 코드(또는 동등한 선언형 플랜)를 쓰면, 빌더가 OWPML ID 테이블을 전면 자동관리하고, 유효한 HWPX로 직렬화하며, 검증·재오픈·한컴 수용성·시각 검수 게이트를 통과시킨다.

핵심 가치 명제는 유지한다: **라이브러리 자체는 렌더러-프리**(한컴 설치 불필요, 순수 파이썬). 한컴 의존 검증은 스킬/오케스트레이션 레이어에만 둔다.

---

## 2. 배경과 현 상태 진단

### 2.1 이미 갖춰진 것

| 계층 | 산출물 | 상태 |
|---|---|---|
| 라이브러리 | `python-hwpx` 2.9.1 | 파싱·편집·생성 코어, OWPML oxml 모델, 손상 복구, document-plan v1, template form-fit, 품질검사 |
| MCP | `hwpx-mcp-server` 2.2.6 | 위 기능을 39~49개 도구로 노출 |
| 스킬 | `hwpx-skill` | 라우팅·예제·`visual_review.py` 스캐폴드·멀티호스트 패키징 |

### 2.2 격차 진단 — "생성 표현력이 좁다"의 정체

사용자가 지목한 핵심 격차는 **생성 표현력**이다. 조사 결과 이는 *엔진 능력의 부재가 아니라* 표면·ergonomic·오라클 문제였다.

- **엔진(HwpxDocument + oxml)은 이미 넓다**: `add_run(bold/italic/underline)`은 `ensure_run_style()`로 charPr를 자동관리하고, `add_image`·`set_header_text`/`set_footer_text`·`add_footnote`/`add_endnote`·`add_shape`·`add_hyperlink`/`add_bookmark`·`set_columns`·`set_page_size`/`set_page_margins`·`set_span`(셀병합)·`set_start_numbering`·`add_bin_item`(이미지 바이너리)까지 존재한다.
- **에이전트 저작 표면이 좁다**: 권장 경로인 선언형 `document_plan.v1`은 heading/paragraph/bullets/table/page_break로 제한된다. 넓은 엔진 API가 docx-js처럼 *조립형으로 일관·발견 가능하게* 정리·노출돼 있지 않다.
- **진짜 빈틈(엔진에도 없음)**: ① 머리글/바닥글 **자동 쪽번호 필드**, ② **TOC 필드**, ③ 런 서식이 **색·폰트·크기·음영까지는 자동관리 안 됨**, ④ 머리글/바닥글이 **plain text 전용**, ⑤ 다단계 **개요번호** 시맨틱 미노출.

### 2.3 오라클 문제 (설계를 바꾼 결정적 사실)

현 상태: `validate_document()`가 쓰는 `src/hwpx/tools/_schemas/header.xsd`·`section.xsd`는 **2011 네임스페이스 + `<xs:any processContents="lax">` stub**(루트 요소·몇몇 속성만 보는 사실상 noop)이다. 지금은 하드 게이트도 아니고 false-rejection 위험도 아니다.

진행 중인 `feat/phase1-real-xsd-validation-v2` 노력은 이 stub을 **공식 2024 OWPML 전체 스키마로 교체**해 진짜 검증 게이트로 만들려는 것이다. 그런데 여기서 두 가지 벽에 부딪힌다.

1. **de jure ≠ de facto**: 공표 OWPML 스키마가 한컴오피스의 실제 동작과 다르다(한컴 구현이 스키마와 어긋남). "스키마 통과 ≠ 한컴 수용"이고 그 역도 성립한다. 레포의 *"Prevent Hancom from rejecting HWPX roundtrips"* 커밋이 이 교훈을 이미 담고 있다.
2. **네임스페이스 버전 불일치**: `docs/schema-overview.md`가 기록하듯 코드는 2011/2016 ns를 기본으로 쓰는데 공식 스키마는 2024 ns다.

따라서 공표 스키마를 **하드 정확성 게이트**로 삼을 수 없다. → §8에서 오라클을 재정의한다. (이는 `real-xsd-validation` 노력과 충돌이 아니라, 그 노력이 부딪힌 벽에 대한 *해법*이다 — §8.2 참조.)

### 2.4 진행 중 작업과의 정합 (greenfield 아님)

본 스펙은 Wily `hwpx` 프로젝트의 진행 중인 프로그램 위에 얹힌다. **권위 있는 백로그(2026-06-02 기준):** 완료 = S-004(file-only 품질)·S-005(시각검증 루프)·S-006(스택 스모크)·S-045(플러그인 번들)·STG-7df…(깨짐방어)·STG-6be…(split-run form-fill). 남은 `ready` = **"범정부오피스" 7단계 시리즈**(STG-1f5…/5fb…/da0…/1fa…/064…/998…/01c…).

| 진행 작업 | 본 스펙과의 관계 |
|---|---|
| **범정부오피스 7단계 (남은 백로그 전부)** | **충돌→재루팅.** 이 시리즈는 좁은 `authoring.py` document_plan 경로를 패치(name-aware preset, per-level heading, bullet 스타일, table profile)하는데, 이는 빌더가 일반화로 해결하는 바로 그 관심사다. **결정(Ⓐ): 빌더를 먼저 만들고 범정부오피스를 빌더 위로 재루팅** — `government_report`는 빌더 스타일 프리셋/어댑터가 되고, 그 7단계는 빌더 프리미티브 위에서 *얇아진다*. 좁은 경로 패치는 하지 않는다. → §11. |
| `computeruse-visual-review-loop` (S-005, 완료) | §9를 여기에 **위임**. 본 스펙은 빌더 연결 + 축 A(수용성)만 보강. 재정의 금지. |
| `hwpx-absorption-implementation` (clean-room 규칙) | §8.1이 그 법적 경계를 **계승**(코드 clean-room, 샘플 데이터만 벤더링). |
| `feat/phase1-real-xsd-validation-v2` 브랜치 | §8.2가 그 노력의 **착지점**(스키마를 게이트→수렴 lint로). |
| `s006-split-run-form-fill` / `form_fill.py` (완료) | 빌더 완성 후 form-fill을 빌더 위 어댑터로 정렬할 여지. hwpxlib `testFile/error/` 회귀셋으로 강화. |
| 빌더(docx-js급 생성) 자체 | **신규** — 기존 어떤 Stage도 다루지 않음. 본 스펙의 고유 기여이자 범정부오피스의 새 토대. |

**확정 시퀀싱:** ① hwpxlib **오라클 기반(지금 먼저, 독립 선행)** → ② 빌더 코어 → ③ document_plan v2 + **범정부오피스 재루팅**(presets/form-fill을 빌더 어댑터로) → ④ MCP → ⑤ Skill. 남은 범정부오피스 Wily Stage들은 빌더 토대 위로 **재스코프**되어야 한다(보드 액션).

---

## 3. 접근법 결정

### 3.1 채택: 빌더 우선 (Builder-first)

`hwpx.builder` 조립형 객체모델을 새로 만들어 `docx-js`를 미러링한다. 빌더가 ID 테이블을 전면 자동관리하고, 진짜 빈틈을 엔진에 명명된 메서드로 보강한다. `document_plan`은 *이 빌더로 내려가는 얇은 선언형 프런트(plan v2)*로 재정의한다.

### 3.2 기각한 대안과 이유

- **진짜 JS 라이브러리(hwpx-js)를 새로 작성** — 기각. docx-js의 가치는 "JS"가 아니라 "성숙한 폭넓은 선언형 빌더"다. HWPX의 성숙한 엔진은 이미 `python-hwpx`다. OWPML 직렬화는 OOXML보다 까다롭고(한컴의 엄격한 검증), JS로 처음부터 다시 만들면 그동안 쌓인 엣지케이스 수정을 전부 다시 치러야 한다. 런타임 제약(Node/브라우저)이 실재할 때만 정당화된다 — 현재는 아님. (사용자 확인: "docx-js급 빌더 경험, 언어 무관".)
- **선언형 plan v2만 확장 (새 빌더 없음)** — 기각. MCP/검증 재사용은 좋지만 본질이 JSON이라 사용자가 요청한 "코드 빌더 경험"이 아니다. (단, plan v2는 빌더의 선언형 프런트로 §5에 포함된다.)
- **갭만 메우고 스킬 쿡북** — 기각. 최저비용이나 DX가 가장 약하다.

---

## 4. 범위

### 4.1 범위 안

- 새 조립형 빌더 객체모델 `hwpx.builder` (docx-js 미러, Pythonic)
- 빌더의 ID 테이블 전면 자동관리: charPr(색·폰트·크기·굵기/기울임/밑줄·음영), paraPr(정렬·줄간격·들여쓰기), borderFill(표/셀 테두리·음영), binData(이미지)
- 진짜 빈틈 보강 (엔진/facade 신규 메서드): 자동 쪽번호 필드, 리치 머리글/바닥글, 리치 런 서식, 다단계 개요번호/목록
- `document_plan`을 빌더로 lower하는 plan v2로 재정의 (v1 ⊂ v2)
- `.save_to_path()`에 검증·재오픈 게이트 내장 + authoring-quality 리포트
- **렌더링·수용성 검증 루프** (한컴 + ComputerUse) — §9
- 오라클 재정의 (hwpxlib 미러 + 샘플 코퍼스 + 한컴 교차검증 + 스키마 강등) — §8

### 4.2 첫 슬라이스에서 연기 (본 스펙 후반 단계)

- **TOC(목차) 필드** — 필드+스타일 스캐닝이 무거워 첫 슬라이스에서는 제외하고, 본 스펙 §11 **Phase 2**에서 빌더 노드로 추가한다.

### 4.3 범위 밖 (별도 스펙/후속)

- 바이너리 `.hwp` 생성/변환, 임의 OWPML 주입, 기존 문서의 픽셀 단위 재현.
- CI/컨테이너에서 한컴 없는 환경의 정식 렌더링(=blocked evidence로 핸드오프, 기존 패턴 유지).

---

## 5. 아키텍처

```
                ┌─────────────── 에이전트 진입점 ───────────────┐
   코드 경로     hwpx.builder (NEW)            JSON 경로  document_plan.v2
   Document/Section/Paragraph/Run/...            (빌더의 선언형 직렬화)
                          │                              │
                          └──────────┬───────────────────┘
                                     ▼
                         hwpx.builder 코어 (단일 모델)
                   intent → ID 테이블 자동관리 → engine 호출
                                     │
              ┌──────────────────────┼───────────────────────┐
              ▼                      ▼                        ▼
   HwpxDocument facade        신규 facade 메서드        oxml (저수준,
   (add_paragraph/add_run/    (page-number field,        갭일 때만 직접)
    add_image/add_table/...)   rich header/footer,
                               rich run style, numbering)
                                     │
                  validate(lint) + 구조 하드게이트 + reopen
                                     │
                        authoring-quality 리포트
                                     │
              (visual_review_required=true → 스킬 CU 검증 루프, §9)
```

**핵심 원칙:**

1. 빌더는 **공개 `HwpxDocument` facade를 통해서만** 생성한다. 빌더 내부 임의 XML 금지.
2. facade로 표현 불가능한 진짜 빈틈은 **빌더 안에서 땜질하지 않고** facade/oxml에 *명명된 신규 메서드*로 추가한다. → MCP/plan 경로도 같은 게이트로 이득.
3. `create_document_from_plan`은 plan을 빌더 노드로 **lower**하도록 재구현. plan v1은 v2의 부분집합으로 하위호환.
4. `presets/proposal`, `template_formfit`, MCP 도구는 빌더 위 어댑터로 점진 이전(엔진 중복 0).
5. 라이브러리는 렌더러-프리 유지. 한컴 의존 검증은 스킬/MCP 오케스트레이션 레이어에만.

---

## 6. 빌더 객체모델

docx-js의 "생성자 트리 + 자식 리스트 + 선언형 속성" 패턴을 Pythonic하게 미러링한다.

```python
from hwpx.builder import (
    Document, Section, PageSize, Margins, Metadata,
    Heading, Paragraph, Run, Bullet, NumberedList,
    Table, Image, Header, Footer, PageNumber, PageBreak,
)

doc = Document(
    metadata=Metadata(title="2026 AI 교육 운영계획", author="AI교육팀", organization="○○학교"),
    sections=[Section(
        page=PageSize.A4, margins=Margins(top_mm=20, left_mm=20, right_mm=20, bottom_mm=20),
        header=Header(children=[
            Paragraph(align="right", children=[Run("○○학교  -  "), PageNumber()])]),
        footer=Footer(children=[Paragraph(align="center", children=[PageNumber(format="page/total")])]),
        children=[
            Heading(level=1, text="추진 개요"),
            Paragraph(children=[
                Run("본 계획은 "),
                Run("AI 융합교육", bold=True, color="C00000", size=12, font="함초롬바탕"),
                Run(" 추진을 위한 것이다."),
            ]),
            Bullet(level=0, items=["목표 설정", "예산 편성", "일정 수립"]),
            Table(
                header=["구분", "내용", "기한"],
                rows=[["1단계", "기반 구축", "3월"], ["2단계", "운영", "4~11월"]],
                column_widths=[2, 3, 1],
                header_shading="EAF1FB",
                merges=["A2:A3"],   # 스프레드시트식 표기 (1차 채택)
            ),
            Image("logo.png", width_mm=30, align="center", caption="학교 로고"),
            PageBreak(),
            Heading(level=1, text="기대 효과"),
            Paragraph(text="..."),
        ],
    )],
)
report = doc.save_to_path("운영계획.hwpx")   # validate + reopen 내장
# report.validate_package.ok / validate_document.ok / reopened / visual_review_required
```

**노드 설계 원칙:**

- 각 노드는 작고 독립적이다. "무엇을 의미하는가 / 어떻게 lower되는가"만 알면 되고, 노드별 단위 테스트가 가능하다.
- 속성은 의도 중심(`bold`, `color`, `size`, `align`, `width_mm`)이며, ID 테이블 plumbing은 빌더가 숨긴다.
- 1차 노드 집합: `Document`, `Section`, `PageSize`, `Margins`, `Metadata`, `Heading`, `Paragraph`, `Run`, `Bullet`, `NumberedList`, `Table`, `Image`, `Header`, `Footer`, `PageNumber`, `PageBreak`.
- 셀 병합 표기는 스프레드시트식(`"A2:A3"`)을 1차 채택한다. (좌표식 `(row,col,rowspan,colspan)`은 필요 시 보조 입력으로 추가 가능.)

---

## 7. 엔진 빈틈 보강 (facade/engine 신규 메서드)

빌더는 facade만 호출한다. 아래 빈틈은 빌더 안에서 땜질하지 않고 엔진에 명명된 메서드로 추가하며, 각 메서드는 §8의 오라클(대응 hwpxlib 샘플 미러 + 한컴 재오픈)로 검증한다.

| 빈틈 | 빌더 노드 | 신규 엔진/facade | 검증 기준 샘플 |
|---|---|---|---|
| 자동 쪽번호 | `PageNumber()` | `HeaderFooter.add_page_number_field()` | `PageFunctions.hwpx` |
| 리치 머리글/바닥글 | `Header/Footer(children=[…])` | `set_header(content=…)` (현 `set_header_text`는 text-only) | `HeaderFooter.hwpx` |
| 리치 런 서식 | `Run(color=,font=,size=,highlight=,strike=)` | `ensure_run_style()` 확장 (현재 bold/italic/underline만) | (서식 포함 일반 샘플) |
| 다단계 번호/목록 | `NumberedList(level=)`, `Bullet(level=)` | `ensure_numbering()` + paraPr 참조 | (목록 포함 샘플) |
| 셀 병합·음영·열너비 | `Table(merges=,header_shading=,column_widths=)` | 기존 `set_span` + borderFill 자동관리 래핑 | `SimpleTable.hwpx` |

각 신규 메서드의 OWPML 토큰은 **공표 스키마가 아니라** hwpxlib 동작/샘플에서 확정한다.

---

## 8. 오라클 재정의 (이 스펙의 핵심 차별점)

공표 OWPML 스키마는 신뢰할 수 없으므로(§2.3), 진실의 우선순위를 다음과 같이 재정의한다.

### 8.1 1차 오라클 — `hwpxlib` clean-room 미러 + 샘플 코퍼스 벤더링

[`neolord0/hwpxlib`](https://github.com/neolord0/hwpxlib)는 수년간 실사용 버그 리포트로 다져진 성숙한 de-facto 레퍼런스 구현이며 **Apache-2.0**(python-hwpx와 호환)이다.

`hwpx-absorption-implementation.md`의 **clean-room 법적 경계를 그대로 따른다**: 외부 코드의 함수 본문/구조를 복사·번역 포팅하지 않는다. 동작만 관찰해 재구현하고 출처를 `NOTICE`에 기록한다.

- **구조 레퍼런스 = hwpxlib 동작의 clean-room 미러링.** 소스를 *읽어 코드/구조를 옮기는 것이 아니라*, 한컴이 각 기능을 어떻게 직렬화하는지 동작을 관찰해 `python-hwpx` 위에서 독립 재구현한다. 관찰로 설명되지 않는 동작이 필요해지면 즉시 중단하고 출처·법적 경계를 재확인한다.
- **골든 코퍼스 = hwpxlib의 47개 `.hwpx` 샘플 데이터 파일 벤더링.** (사용자 결정: 샘플 *데이터*는 Apache-2.0 하에 벤더링 허용, *코드*는 clean-room.) `tests/fixtures/hwpxlib_corpus/`에 서브모듈 또는 복사 + `NOTICE` 귀속. round-trip/구조 테스트의 기준선.
- (옵션) 필요 시 hwpxlib jar를 돌려 기능별 canonical `.hwpx`를 *생성물*로 확보 — 파일 복사가 아닌 생성이라 추가 엣지케이스 보강에 활용.

기능 → 골든 샘플 매핑:

| 빌더 기능 | hwpxlib 샘플 |
|---|---|
| 머리글/바닥글 | `reader_writer/HeaderFooter.hwpx` |
| 자동 쪽번호 | `reader_writer/PageFunctions.hwpx` |
| 용지/여백 | `reader_writer/PageSize_Margin.hwpx` |
| 다단 | `reader_writer/MultiColumn.hwpx` |
| 표 / 이미지 | `reader_writer/SimpleTable.hwpx`, `SimplePicture.hwpx` |
| 수식(Phase2)/변경추적 | `reader_writer/SimpleEquation.hwpx`, `ChangeTrack.hwpx` |
| 실제 정부문서 회귀셋 | `error/.../재난안전종합상황_분석_및_전망.hwpx`, `프로젝트 계획서.hwpx`, `테스트문서.hwpx` 등 |

추가 무료 보강: 정부가 2026년 10월부터 공공기관 HWPX를 의무화하므로 도메인 일치(공문·계획서) 실제 코퍼스가 공공채널에 폭증한다.

### 8.2 2차 — 스키마는 게이트에서 강등 (`real-xsd-validation` 노력의 착지점)

진행 중인 `feat/phase1-real-xsd-validation-v2`는 stub을 공식 2024 OWPML 스키마로 교체해 *하드 게이트*로 만들려 했고, §2.3의 두 벽(de jure≠de facto, 2011↔2024 ns 불일치)에 부딪혔다. 본 스펙은 그 노력을 폐기하지 않고 **지속가능한 형태로 착지**시킨다 — 공식 스키마는 게이트가 아니라 *수렴하는 lint*로 둔다.

- 공식 2024 OWPML 스키마를 도입하되 **하드 게이트 아님 → 경고(lint)**. 스키마 실패는 (한컴 실거부와 상관될 때만 빼고) 경고로 보고한다.
- **네임스페이스 정합**: 코드가 쓰는 2011/2016 ns와 공식 2024 ns의 매핑/호환 전략을 `owpml-deviations.md`에 명시(이 정합 자체가 `real-xsd-validation`의 핵심 미해결 과제였다).
- `docs/owpml-deviations.md` 레지스트리 신설: 각 항목 = "공식 스키마는 X라는데 한컴은 Y를 요구/생성함 + 증거 샘플(§8.1 코퍼스/캡처)". 확인된 편차는 로컬 스키마를 한컴 현실에 맞게 패치(주석으로 편차 인용). → 스키마가 시간이 갈수록 한컴 진실로 수렴.

### 8.3 스키마 무관 하드 게이트 (항상 유지)

스키마가 틀려도 참인 진짜 정확성 검사는 하드 게이트로 유지한다: XML well-formed · ID 참조 무결성(charPr/paraPr/borderFill/binData 모두 해소) · 관계/Content_Types 무결성 · ZIP/OPC 유효성 · **signed-int32 ID 경계**(알려진 quirk) · `HwpxDocument.open` 재오픈.

### 8.4 교차검증 파이프라인

1. hwpxlib 샘플을 python-hwpx로 **읽기** 성공(47개 전부) → 현 리더 갭 즉시 노출.
2. 같은 기능을 빌더로 **생성**.
3. 생성 구조를 대응 hwpxlib 샘플과 **diff**.
4. 한컴 **재오픈**(CU 루프, §9) 확인.

---

## 9. 검증 루프 (한컴 = 레이아웃 + 수용성 양축 오라클)

> **재사용 주의:** 시각 검증 루프 자체는 본 스펙이 새로 만드는 것이 아니다. 공개
> `hwpx.visual-review.v1` 증거 계약(`observed_pass`/`needs_review`/`blocked`, 타임스탬프,
> 스크린샷 경로, CI fallback, 반복 이력)을 재사용한다. 본 스펙의 기여는 두 가지뿐이다:
> (1) 빌더 리포트가 그 계약과 연결되도록 `visual_review_required`를 노출, (2) 시각/레이아웃
> 증거에 "복구 다이얼로그 없이 열림 + 라운드트립" 구조 수용성 검사를 추가한다.

빌더 리포트의 `visual_review_required=true`가 이 루프를 트리거한다. ComputerUse + 설치된 한컴오피스를 오라클로 쓴다. 라이브러리가 아니라 **스킬/MCP 오케스트레이션 레이어**(S-005의 `hwpx-skill/scripts/visual_review.py` 확장)에 둔다.

- **축 A — 구조 수용성(진짜 정확성 오라클).** 생성물을 한컴에서 열기 → **"복구/repair" 다이얼로그 없이 깨끗이 열리는가** → 저장 → **save→reload 라운드트립**에서 구조가 안 깨지는가. 스키마 과신을 대체한다.
- **축 B — 시각 레이아웃.** 캡처(ComputerUse 스크린샷, 가능하면 한컴 AppleScript "PDF로 내보내기"→`pdftoppm`→이미지) → 비전 검수: 페이지 나눔, 표 맞춤/넘침, 머리글·바닥글·쪽번호 노출, 이미지 배치, placeholder/□□ 잔존 여부.
- **반복.** 결함이면 빌더 입력 수정 → 재생성 → 재검.
- **증거.** 통과 시 기존 `hwpx.visual-review.v1` 증거 스키마(`current.status=="observed_pass"`, `current.screenshot_path`)에 기록.
- **폴백.** 한컴/CU 없는 CI에선 `--viewer none → blocked` 증거로 핸드오프(제출 준비 완료 아님).

---

## 10. 첫 수직 슬라이스

빌더 + 5개 갭보강 + 오라클을 한 번에 증명하는 최소 end-to-end.

**생성:** `hwpx.builder`로 다음을 포함한 문서 하나 — 메타데이터 / A4+여백 1개 섹션 / 리치 머리글(Run+PageNumber) / 바닥글(쪽번호 page/total) / Heading 1·2 / 혼합 런(굵게+색+크기+폰트) 문단 / 다단계 Bullet / 헤더음영+셀병합+열너비 표 / 이미지 1개 / PageBreak.

**검증:**

1. `save_to_path()` → validate_package OK · validate_document(lint, 경고허용) · 재오픈 OK · ID 무결성 하드게이트 OK
2. 읽기 되돌림: 텍스트/표 내용 일치
3. 교차검증: 생성 구조를 hwpxlib `HeaderFooter`/`PageFunctions`/`SimpleTable`/`SimplePicture` 샘플과 diff
4. 한컴 CU 루프: 복구 다이얼로그 없이 열림(=수용) → 스크린샷 → 비전 검수 → `hwpx.visual-review.v1` observed_pass 증거
5. 동일 내용을 `document_plan.v2` JSON으로도 생성 → 동일 출력(코드/JSON 패리티)

---

## 11. 단계 (라이브러리 → MCP → 스킬)

### Phase 0 — 오라클 기반 (지금 먼저, 독립 선행 Wily Stage)

> cross-cutting: 빌더뿐 아니라 범정부오피스 테이블/품질·이미 끝난 form-fill까지 de-risk한다. 그래서 빌더보다 먼저 독립 Stage로 깐다.

- hwpxlib 47샘플을 `tests/fixtures/hwpxlib_corpus/`로 벤더링 + `NOTICE` 귀속 + 기능→샘플 매니페스트.
- "47개 전부 읽기" 스모크 테스트(현 리더 갭 즉시 노출).
- `docs/owpml-deviations.md` 신설; `validate_document` 스키마 실패를 경고로 강등(구조 불변식은 하드게이트 유지); 2011↔2024 ns 정합 메모.
- 기존 S-005 `visual_review.py` 루프에 **축 A(구조 수용성: repair 다이얼로그 없이 열림 + 라운드트립)** 보강. (시각 루프 자체는 S-005가 이미 구현 — 재구현 아님.)

### Phase 1 — 빌더 코어 (centerpiece)

- 새 패키지 `hwpx/builder/`: §6 노드모델.
- 각 노드는 HwpxDocument facade 경유 lower; ID 테이블 자동관리.
- §7의 5개 갭보강을 명명된 엔진 메서드로(각 hwpxlib 샘플 미러 + 한컴 재오픈 테스트).
- `Document.save_to_path()`가 authoring-quality 리포트 반환(검증 + 재오픈 + `visual_review_required`).
- 테스트: 노드 단위테스트 + §10 슬라이스 통합테스트 + 코퍼스 교차검증.

### Phase 2 — 선언형 프런트(plan v2) + 어댑터 + 범정부오피스 재루팅

- `create_document_from_plan`을 plan→빌더 lower로 재구현(v1 ⊂ v2; 코드/JSON 패리티 테스트).
- proposal preset / template_formfit을 빌더 위 어댑터로 이전(엔진 중복 0).
- **범정부오피스 재루팅**: `government_report`를 빌더 스타일 프리셋으로 구현(한국 공문 불릿 □/○/-/※/*, per-level heading, callout 등은 빌더 프리미티브로 자연 지원). 남은 범정부오피스 Wily Stage(STG-1f5… 외)들을 좁은 `authoring.py` 패치가 아니라 **빌더 기반으로 재스코프**. 테이블 정규화·품질 프로필은 빌더 표/리포트 위에 얹는다.
- **TOC 노드**를 이 단계에서 추가(빌더 Phase 2 항목).

### Phase 3 — MCP 노출

- plan v2를 기존 MCP 도구(`validate_document_plan` / `create_document_from_plan` / `inspect_document_authoring_quality`)로 노출; sanitized schema; JSON-RPC e2e 테스트.

### Phase 4 — 스킬 교육 + 스택 스모크

- `SKILL.md` 라우팅: 코드-실행 에이전트 → 빌더 / MCP·데이터 에이전트 → plan v2; 검증+재오픈 증거 요구; `visual_review_required`일 때 한컴 시각 증거 요구.
- `references/api.md`: 빌더 API; 예제; `quickcheck.py --builder`.
- 스택 스모크가 §10 슬라이스를 core/MCP/skill로 관통.

---

## 12. 테스트 오라클 계층 (요약)

- **하드게이트(스키마 무관)**: XML well-formed · ID참조 무결성 · OPC/관계 무결성 · signed-int32 ID · 재오픈.
- **레퍼런스게이트**: hwpxlib 47샘플 읽기 · 생성기능 vs 대응 샘플 구조 diff.
- **권위게이트(CU)**: 한컴 복구없이 열림 + 라운드트립 · 비전 검수 observed_pass.
- **lint(비게이팅)**: 스키마 검증 → 경고 + 편차 레지스트리.

---

## 13. 리스크와 완화

| 리스크 | 완화 |
|---|---|
| 빌더가 미명세 레이아웃 언어로 비대해짐 | 1차 노드 집합을 작게 고정; 미지원 입력은 조기 거부. |
| 생성물이 구조검증은 통과하나 레이아웃이 나쁨 | §9 한컴 시각 검수 루프를 게이트로; `visual_review_required` 명시. |
| hwpxlib가 Java라 직접 재사용 불가 | 코드/구조 포팅 금지(clean-room); 동작만 관찰해 재구현 + 샘플 데이터 코퍼스 벤더링; 필요 시 jar로 canonical 생성. |
| 공표 스키마 편차로 false pass/fail | 스키마를 lint로 강등 + 편차 레지스트리 + 한컴 수용성을 권위 게이트로. |
| 한컴/CU 없는 CI | blocked evidence 폴백; 레퍼런스게이트(코퍼스 diff)는 CI에서도 동작. |
| 엔진 중복 | proposal/form-fit/MCP를 빌더 위 어댑터로 이전. |
| 벤더링 샘플 라이선스 | hwpxlib Apache-2.0; `NOTICE`에 귀속 명시. |

---

## 14. 완료 정의 (Definition of Done)

- `hwpx.builder` 1차 노드 집합이 안정적으로 문서화·구현됨.
- §10 슬라이스가 빌더로 생성되어 하드게이트·레퍼런스게이트·권위게이트(CU)·코드/JSON 패리티를 모두 통과.
- hwpxlib 47샘플을 python-hwpx가 전부 읽음.
- `document_plan.v2`가 빌더로 lower되고 v1 하위호환.
- `owpml-deviations.md` 레지스트리가 가동되고 스키마가 lint로 강등됨.
- MCP가 plan v2를 sanitized schema + JSON-RPC 커버리지로 노출.
- 스킬이 코드/플랜 라우팅을 가르치고 `visual_review_required`일 때 한컴 증거를 요구.
- 기존 proposal/quality-generation 테스트가 그린 유지(빌더 위 어댑터로).
