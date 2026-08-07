# 문서 끼워 넣기(문서 병합) — 계약 문서

**사이클 6.9 트레인㉝**. 편집기 표면 인벤토리(트레인㉙)의 macOS 메뉴 전수
스캔(2026-08-07)이 찾은 신규 갭 — 한컴 편집기 1급 메뉴 "입력→문서 끼워
넣기…"인데 우리 세 자산(원장·capabilities·지원 매트릭스) 어디에도 대응
표면이 없었다. 이 문서는 구현 전 계약이다 — id 참조 체계를 실코퍼스·
스키마에서 전수 파악하고, v1 스코프와 정책 선택지를 여기 확정한다.

## 왜 어려운가

다른 HWPX 문서의 본문을 현재 문서에 끼워 넣으면, 그 본문이 참조하는
"헤더가 소유한 공유 자원"(글자 모양·문단 모양·스타일·테두리채우기·탭
정의·글머리표·번호매기기·메모 모양·글꼴)의 id가 대상 문서에서 이미
다른 뜻으로 쓰이고 있을 수 있다. 그대로 복사하면 참조가 조용히 엉뚱한
자원을 가리키게 된다(무음 오류 — 이 라이브러리 전체가 가장 경계하는
실패 양상). 그래서 핵심은 "복사"가 아니라 "재매핑"이다.

## id 참조 체계 전수 (스키마 + 실코드 대조)

### 축 1 — 헤더가 소유한 공유 자원(다대일 참조, 재매핑 테이블 필요)

`hh:refList`(Header XML schema.xml `MappingTableType`)가 선언하는 8개
id-space 전부와, 본문에서 그걸 가리키는 실제 속성:

| id-space(`hh:refList` 자식) | 항목 요소 | 참조 속성(실사용, 빈도순) | 참조하는 본문 요소 |
|---|---|---|---|
| `charProperties` | `charPr` | `charPrIDRef`(51건, 최다) | `hp:run`, `hh:style` |
| `paraProperties` | `paraPr` | `paraPrIDRef`(19건) | `hp:p`, `hh:style` |
| `styles` | `style` | `styleIDRef`(16건) | `hp:p`; `style` 자신도 `nextStyleIDRef`/`charStyleIDRef`로 다른 style·charPr을 참조 |
| `borderFills` | `borderFill` | `borderFillIDRef`(17건) | `hp:tbl`/`hp:tc`(표 셀), 페이지 테두리, 문단 테두리, 도형 등 다수 컨텍스트가 **같은 id-space를 공유** |
| `tabProperties` | `tabPr` | `tabPrIDRef`(3건) | `hh:paraPr` |
| `numberings` | `numbering` | `hh:heading/@idRef`(type="NUMBER"일 때) | `hh:paraPr/hh:heading` — **폴리모픽**: 속성 이름은 그냥 `idRef`, 어느 id-space를 가리키는지는 형제 속성 `type`이 결정한다(NUMBER→numberings, BULLET→bullets, OUTLINE도 numberings 계열로 추정 — 실증 필요) |
| `bullets` | `bullet` | `hh:heading/@idRef`(type="BULLET"일 때) | 상동 |
| `memoProperties` | `memoPr` | `memoShapeIDRef`(6건) | `hp:memo` |
| `fontfaces`(`hh:font`) | `font` | 직접 IDRef 없음 — `charPr`이 `fontRef`로 lang별 font id를 내장 | `hh:charPr/hh:fontRef` |

**`fontfaces` 구현 확정(실측)**: `hh:fontRef`의 7개 lang 속성
(hangul/latin/hanja/japanese/other/symbol/user)은 **서로 독립된 id-space다**
— 실측 확인: HANGUL 블록에 font id 0/1/2가 있어도 LATIN 블록은 0/1까지만
있을 수 있어(같은 숫자값이 lang마다 다른 글꼴을 가리킴), 재매핑 테이블도
lang별로 따로 만든다(`_remap_fonts`). 다른 7개 id-space와 달리 "하나의
평평한 맵"이 아니라 "lang마다 별도 맵" 모양이라 `_apply_remaps`의 공용
루프에 안 태우고 전용 적용 함수(`_apply_font_remap`)로 처리한다.

**공통 재매핑 규칙(v1)**: 스타일 중복 매칭/dedupe는 **안 한다**(정책
선택 — 아래 "정책 선택지" 참조). 원본 문서가 참조하는 항목만(전체
`refList`가 아니라, 끼워 넣는 본문 서브트리가 실제로 가리키는 것만)
대상 문서 해당 id-space에 **새 id로 복제**하고, old-id→new-id 맵을
만들어 복사되는 본문 서브트리 전체의 해당 속성을 일괄 치환한다. 새 id
채번은 기존 `HwpxOxmlHeader._allocate_ref_id`(최대값+1, 충돌 시 증가)
패턴을 그대로 재사용한다 — 이미 검증된 로직, 재발명 안 함.

### 축 2 — 이진 자원(`hh:binDataList`, 자체 id-space)

`binaryItemIDRef`(10건) — `hh:font`/`hh:substFont`(임베드 글꼴), `hp:pic`
류(그림)가 `hh:binDataList/hh:binItem`을 가리킨다. 이것도 축1과 같은
"다대일, 재매핑 테이블 필요" 부류이지만 **파트가 다르다** — 항목 자체
(이진 바이트)를 `Contents/`의 실제 파일로도 복사해야 한다(참조만
재매핑하고 바이트를 안 옮기면 손상 문서). `HwpxOxmlHeader`의 기존
`_allocate_bin_item_id` 재사용.

### 축 3 — 문서-로컬 구조 id(유일값, 충돌 회피만 필요 — 공유 테이블 아님)

다른 문서에서 복사해 온 요소 자신의 정체성 id들. 헤더 자원과 달리
"여러 본문 요소가 같은 값을 공유"하지 않고 보통 1:1이므로, **재매핑
테이블이 아니라 새로 채번**(충돌 회피)이 정답이다.

| 요소 | id 속성 | 이미 있는 도구 |
|---|---|---|
| `hp:p` | `id` | `_refresh_copied_paragraph_subtree_ids`(`_document_primitives.py`)가 **이미 재채번한다** — same-doc paragraph clone(body_patch 계열)이 쓰던 걸 그대로 재사용 |
| `hp:tbl`/`hp:pic`/`hp:container`/`hp:ole`/`hp:equation`/`hp:textart`/`hp:video`/`hp:header`/`hp:footer` | `id` | 상동, 이미 재채번됨 |
| 도형류 | `instId` | 상동, 이미 재채번됨(단 `subjectIDRef`류 참조는 **아직 안 따라감** — 아래 "보류" 참조) |
| `hp:memo` | `id` | **없음** — `_refresh_copied_paragraph_subtree_ids`가 memo id는 안 건드린다(same-doc clone 용례가 메모 포함 문단을 복제한 적이 없어서 이 갭이 안 드러났을 뿐). 문서 병합은 채번 로직을 확장해야 한다 |
| `hp:fieldBegin`/`hp:fieldEnd` | `id`/`fieldid` + `beginIDRef`(fieldEnd가 자신의 fieldBegin을 가리킴) | **없음** — 새로 만들어야 한다. 쌍 무결성 유지 필수(fieldEnd의 beginIDRef는 반드시 **같이 재채번된** 자기 fieldBegin의 새 id를 가리켜야 함) |
| `hp:bookmark` | `name`(문자열, id 아님) | **없음** — 대상 문서에 같은 이름의 북마크가 이미 있으면 충돌(무음 상호참조 오류 가능) — v1은 이름 충돌 시 접미사 부여로 회피 |

### 축 4 — 절 설정(`hp:secPr`, 공유 자원도 문서-로컬 id도 아닌 제3의 부류)

실측(라이브 병합 스모크)에서 발견: 절의 **첫 문단**은 텍스트 없는 전용
`hp:run`(형제로 `hp:secPr`+`hp:ctrl/hp:colPr`을 담음)을 하나 더 갖고
있다 — 여백·각주/미주 정책·페이지 테두리 등 그 절 전체의 페이지 설정을
싣는 자리다. 다른 문단은 이 run이 없다(`hp:t`만 있는 run뿐). `hp:secPr`
자신도 `outlineShapeIDRef`(→numberings)·`memoShapeIDRef`(→memoProperties)·
중첩 `pageBorderFill/@borderFillIDRef`(→borderFills) 등 id 참조를 여러 개
내장한다. v1은 항상 **이미 있는 대상 절에 끼워 넣는다**(새 절을 만들지
않는다)는 스코프이므로, 복사되는 문단이 대상 절의 "첫 문단"이 되는
경우는 없다 — 즉 원본의 이 secPr을 그대로 들고 오면 (a) 한 절에 secPr이
둘 생기는 구조적 모순이거나 (b) 삽입 위치가 index 0이면 대상의 페이지
설정을 조용히 원본 것으로 갈아치우는 부작용, 둘 중 하나다. **정책(v1
확정)**: 복사되는 문단에서 `hp:secPr`(과 그것이 감싼 `hp:colPr` 단
컨트롤)을 무조건 제거한다(대상의 secPr이 항상 그 절의 유일한 권위로
남는다) — 내장된 id 참조까지 재매핑할 근거·스코프가 없으므로 "재매핑"
대신 "제거"를 택했다. 병합 보고서의 `sectionPropertiesStripped`에 제거
횟수를 남긴다(무음 처리 금지).

**제거 단위는 run 전체가 아니라 `hp:secPr` 요소 자신(실측으로 정정)**:
최초 구현은 secPr을 담은 run 전체를 통째로 지웠다 — 새 문서
스켈레톤에서는 그 run이 텍스트 없이 secPr+ctrl/colPr만 담고 있어서
문제가 없어 보였다. 그런데 실코퍼스 표본
(`reader_writer__SimpleTable.hwpx`)이 반증했다: 그 문서의 첫 문단은
`secPr`/`ctrl`(colPr)/`tbl`/`t`을 **전부 한 run 안에** 담고 있었고,
통째 제거가 표와 텍스트까지 함께 지워버렸다 — 병합은 "성공"하고
참조무결성도 "통과"했지만(사라진 내용은 애초에 댕글링을 안 만드니까)
내용이 무음으로 증발한 것이다. 정확히 이 모듈이 막으려던 실패 양상을
이 모듈 자신이 저지른 셈이다. 수정: `hp:secPr`과, 그것을 감싼
`hp:ctrl`(내부에 `hp:colPr`이 있는 것만, 다른 컨트롤 타입은 안 건드림)만
개별 제거하고, 그 결과 run이 완전히 비면(원래 스켈레톤 사례처럼) 그때만
run 자체를 정리한다.

## 한컴 편집기 실측 — 병합 정책 4축

**루트가 Mac 실한컴 GUI로 직접 확보(2026-08-07)**: "입력→문서 끼워
넣기…"를 실행하면 뜨는 파일 선택 패널에 한컴 고유 옵션 체크박스 4개가
붙어 있다(macOS 표준 패널 확장):

- **글자 모양 유지**
- **스타일 유지**
- **쪽 모양 유지**
- **문단 모양 유지**

**넷 다 기본값 해제(0)** — 즉 한컴의 기본 동작은 "끼워 넣는 문서의
서식을 버리고 받는 문서 서식에 흡수"이고, 유지는 옵트인이다. 이
이름들은 한컴 UI에서 그대로 가져온 것이다(우리가 새로 발명하지 않음).

**v1이 각 축을 어디에 매핑하는지, 정직하게**:

| 한컴 축 | 대응하는 우리 재매핑 | v1의 실제 동작 | 한컴 기본값과 일치? |
|---|---|---|---|
| 글자 모양 유지 | charPr/fontfaces 재매핑(축1) | **항상 새 id로 별도 보존**("유지" 쪽 고정) | 아니오 — 한컴 기본은 흡수(0), v1은 유지(항상 ON)에 해당 |
| 스타일 유지 | style 재매핑(축1) | **항상 새 id로 별도 보존**("유지" 쪽 고정) | 아니오 — 상동 |
| 쪽 모양 유지 | `hp:secPr`(축4) | **항상 버림**(대상의 기존 절 설정이 유일한 권위) | **예** — 한컴 기본(흡수/버림, 0)과 일치 |
| 문단 모양 유지 | paraPr 재매핑(축1) | **항상 새 id로 별도 보존**("유지" 쪽 고정) | 아니오 — 상동 |

**핵심 정직 고지**: v1은 이 4축을 **사용자가 선택할 수 있는 옵션으로
전혀 노출하지 않는다** — 축마다 하나의 고정 정책만 구현했다(글자/
스타일/문단 모양은 "유지 항상 ON", 쪽 모양은 "유지 항상 OFF"). 한컴처럼
4개를 독립적으로 토글하는 표면은 v1 범위 밖이다 — v1 스코프 절의
"dedupe 없음" 결정(글자/스타일/문단 모양 3축)과 축4의 "대상 secPr이
유일한 권위" 결정(쪽 모양 1축)이 왜 그 값으로 고정됐는지의 실측 근거가
바로 이 표다. v2 후보: 4축을 함수 매개변수로 노출(예:
`keep_character_shape=False`/`keep_style=False`/`keep_page_shape=False`/
`keep_paragraph_shape=False`, 한컴 기본값과 동일하게 전부 기본 False로).

## 보류(v1 범위 밖, fail-closed로 거부)

- **`hp:memogroup`(메모 내용)** — 실측(라이브 병합 스모크)에서 발견:
  메모의 실제 텍스트는 문단 안에 있지 않다. 앵커 문단은
  `hp:fieldBegin type="MEMO"`(그 `hp:parameters/hp:stringParam name="ID"`가
  `hp:memogroup/hp:memo/@id`와 일치)만 갖고, `hp:memogroup` 자신은 절
  레벨에서 `hp:p`들과 **형제**다(문단 안에 중첩되지 않음). 이 모듈이
  다루는 단위는 문단이라, 순진하게 문단만 복사하면 메모 내용이 무음으로
  누락된다 — 정확히 이 모듈이 막으려는 무음 손상 모양. v1은
  `fieldBegin type="MEMO"`가 있으면 **fail-closed 거부**한다(memogroup
  자체를 찾아 같이 복사하는 완전 지원은 실재하지만 스코프 밖 — v13+ 후보).
- **`subjectIDRef`(connectLine의 스마트 연결선)** — DEV-013이 이미 저작
  API를 보류한 이유와 같은 근거(관계식 불확실) + 참조 자체가
  `instId`를 가리키는 특수 케이스라 재매핑이 한 겹 더 필요. 끼워 넣을
  본문에 `hp:connectLine`이 있으면 v1은 **typed 오류로 거부**(무음
  손상 대신 명시적 실패).
- **`linkListIDRef`/`linkListNextIDRef`(연결된 글상자 체인)** — 벤더드
  코퍼스 전수 재측정(팀장 독립 검증, 2026-08-07): **5,891/5,891건이
  전부 `"0"`**이다 — 실제 글상자 체인 실사용은 코퍼스 어디에도 없다.
  `"0"`은 "연결 없음" 관용값이며, 우리 자신의 `add_table` 산출물의 모든
  표 셀 `hp:subList`도 이 값을 기본으로 단다. **원래 구현은 이 속성의
  존재만으로 거부했는데, 그 결과 표가 든 모든 문서(우리 자신의
  `add_table` 산출물 포함)의 병합이 불가능했다** — 진짜 결함, 팀장의
  검증 프로브가 잡음(아래 "실측으로 찾은 결함" 참조). 수정: `"0"`(과
  빈 문자열)은 안전하게 통과, 그 외 실체인 값만 거부. `chartIDRef`는
  같은 재점검에서 정반대로 확인됨(코퍼스의 유일한 실사용 1건이 실제
  경로값 `"Chart/chart1.xml"`, `"0"` 같은 관용값 없음) — 존재만으로도
  거부하는 현행이 정확해 그대로 둔다. `subjectIDRef`는 `hp:connectLine`
  요소 자체의 존재로 거부되므로(속성 스캔이 아니라 요소 존재 검사) 같은
  과잉거부 위험이 없다 — 요소 하나 통째가 있다는 것 자체가 이미 실사용
  신호다(linkListIDRef처럼 모든 subList가 기본으로 다는 관용 속성과는
  다른 부류).
- **`chartIDRef`** — 차트가 참조하는 이진 자원의 정확한 재매핑 경로가
  이번 조사로 확정 안 됨(빈도 낮음, `add_chart`가 만드는 최근 구조와
  실코퍼스 구조가 다를 수 있음). 있으면 거부(과설계 금지 — v1은 명시
  스코프만).
- **`ha:CaretPosition`의 `paraIDRef`/`listIDRef`** — settings.xml의
  커서 위치 북마크일 뿐, 구조 참조가 아니다. 병합 후 stale해도 커서가
  엉뚱한 곳에 있을 뿐 문서 손상이 아니다 — v1은 그대로 둔다(정직
  기록, 수리 안 함).
- **각주/미주 번호, 쪽번호 재시작(`hp:newNum`)** — 자동 계산 필드라
  값 자체는 한컴이 다음 열기에서 재계산한다(M7 TOC의 `dirty` 재계산과
  같은 부류 — DEV-010/DEV-031 전례). id 충돌만 피하면 되고 표시 번호는
  건드리지 않는다. `hp:newNum`이 병합 지점에 있으면 삽입 지점 이후
  번호매기기가 사용자 의도와 다르게 재시작될 수 있음을 알려진 한계로
  기록(차단하지 않음 — 문서 손상이 아니라 표시 정책 문제).

## v1 스코프

- **절 끝에 추가(append)**: 대상 문서의 마지막 절 끝에 원본 문서
  전체(모든 절)의 문단을 순서대로 추가.
- **문단 위치에 삽입(insert)**: 대상 문서의 지정한 문단 뒤에 원본
  문서의 (기본: 전체, 필요시 절 범위 지정) 문단을 삽입.
- 스타일 병합 정책 — **선택: dedupe 없음.** 원본이 참조하는 모든
  charPr/paraPr/style/borderFill/tabPr/numbering/bullet/memoPr/font를
  이름·값이 대상 문서와 같아 보여도 **전부 새 id로 별도 보존**한다.
  근거: (a) "같다"의 판정 기준(모든 속성 완전 일치? 육안상 동일?)이
  실증 없이는 억측이고, (b) 오판정(다른데 같다고 병합)의 대가가
  "안 예쁨"이 아니라 "무음 서식 오염"이라 이 라이브러리의 실패 우선순위
  철칙과 정면으로 충돌한다. 병합/dedupe는 후속 트레인 후보로 명시
  보류.

## 게이트

1. **참조 무결성 전수 검사**: 병합 결과 문서의 모든 `*IDRef`/`idRef`가
   유효한 대상을 가리키는지(대상 id-space에 실재하는 id인지) 기계적으로
   전수 확인. **재발명 안 함** — 이미 `hwpx.tools.id_integrity.
   check_id_integrity`가 이 검사를 더 완전하게 한다(lang별 fontfaces
   테이블·미참조 BinData 검출·charPrIDRef unset sentinel 허용까지) —
   구현 도중 자체 프로브를 하나 만들었다가, 이 기존 도구가 있다는 걸
   뒤늦게 발견하고 **폐기·대체**했다(자체 프로브는 header-level 테이블을
   직접 읽어 항상 최신이었던 반면, `check_id_integrity`는 document-level
   캐시(`char_properties`, `HwpxOxmlDocument._char_property_cache`)를 거쳐
   읽는다는 차이가 있었는데, 그 차이 자체가 진짜 결함을 하나 더
   찾아냈다 — 아래 "실측으로 찾은 결함" 참조). v1은 이 도구를
   `target`에 병합 전/후로 돌려 비교하는 것으로 게이트를 만족한다.

**실측으로 찾은 결함 6건(설계서 작성 이후, 구현 중 발견)**:

- **스타일 자신의 기본 charPr/paraPr 누락**: `hh:style`은 `styleIDRef`로
  본문이 가리키는 것과 별개로 자기 자신의 `charPrIDRef`/`paraPrIDRef`(그
  스타일의 기본 서식)를 갖는다. 본문 문단이 스타일만 참조하고(자기
  run/문단에 그 charPr/paraPr id를 직접 안 쓰면) 이 기본 id들은 본문
  스캔만으로는 절대 안 잡힌다 — 기본 스켈레톤은 모든 스타일의
  기본이 우연히 "0"(본문 기본값과 같음)이라 단순 병합에서는 안 드러나고,
  실제 커스텀 스타일(기본이 "0"이 아닌)에서만 드러난다. 수정:
  `_extra_ids_from_style_bases`가 병합 대상 스타일들의 자기 참조를
  미리 걷어 `_remap_char_properties`/`_remap_para_properties`의 스캔
  대상에 합친다.
- **`char_properties` 캐시 미무효화**: `HwpxOxmlDocument.char_properties`는
  이 라이브러리에서 유일하게 지연 캐시되는 헤더 테이블이다(다른 모든
  테이블은 매번 새로 계산). 이 모듈은 헤더 lxml 트리를 직접 조작하므로
  (`ensure_char_property` 같은 파사드 경로를 안 거침) 캐시를 무효화하는
  기존 관행(`document.invalidate_char_property_cache()`)을 안 타면
  방금 추가한 charPr이 이 캐시를 거치는 모든 소비자(스타일 조회·읽기
  경로 등)에게 "없는 것"처럼 보인다. 자체 프로브는 헤더를 직접 읽어서
  이 결함이 안 보였다 — `check_id_integrity`로 바꾸고 나서야 드러났다
  (재발명 안 함 원칙이 실제로 결함을 잡아낸 사례). 수정: charPr을
  하나라도 새로 추가했으면 병합 끝에
  `target_header.document.invalidate_char_property_cache()`를 호출.
- **`linkListIDRef`/`linkListNextIDRef` 과잉거부(팀장 독립 검증 발견)**:
  위 "보류" 절의 정정 항목과 동일 — 존재만으로 거부하던 원래 구현이
  표가 든 모든 문서(우리 자신의 `add_table` 산출물 포함)를 병합
  불가능하게 만들었다. 5,891/5,891건이 `"0"`(연결 없음 관용값)이라는
  실측을 근거로, `"0"`/빈 문자열은 통과·그 외만 거부하도록 수정.
- **저장 경로 dirty-tracking 미설정(가장 심각, 위 결함을 수리하며 발견)**:
  이 모듈의 모든 재매핑 함수는 대상 헤더의 lxml 트리를 직접 조작한다
  (`target_container.append(clone)` 등) — `ensure_char_property`처럼
  파사드를 거치는 경로는 스스로 `mark_dirty()`를 부르지만, 이 모듈은
  어디서도 `target_header.mark_dirty()`를 부르지 않았다. 저장 경로
  (`HwpxOxmlDocument.to_bytes`)는 `header.dirty`가 참일 때만 헤더를
  라이브 트리에서 다시 직렬화하고, 아니면 그 파트의 원본/캐시 바이트를
  그대로 재사용한다 — 즉 이 모듈이 방금 추가한 요소를 **조용히
  누락시킨다**. 메모리 상태(`check_id_integrity(target)`)는 깨끗하게
  통과하고 저장된 파일만 손상되는 형태라 즉시 안 보였다 — 실제로,
  기존 왕복 테스트 하나가 `add_picture`를 같이 썼는데
  `_remap_binary_items`의 `add_image` 호출이 자기 부수효과로 헤더를
  dirty로 표시해 이 결함을 우연히 가려 왔다. 그림이 없는 병합은 전부
  잠재적으로 손상됐다(참조 대상 요소가 실제로는 저장되지 않음).
  수정: `_merge_paragraphs` 진입 직후 `target_header.mark_dirty()`를
  무조건 호출(v1의 dedupe-없음 정책상 사실상 모든 비공 병합이 헤더를
  건드리므로 조건부로 아낄 이유가 없다).
- **`hp:secPr` 제거가 통째 run을 지워 표·텍스트를 함께 삭제(팀장
  결함을 수리하는 과정에서 회귀 테스트 작성 중 발견)**: 위 "축4" 절에
  전체 설명 — 최초 구현은 secPr을 담은 run 전체를 지웠는데, 실코퍼스
  표 문서에서 secPr·표·텍스트가 한 run에 같이 있어 표·텍스트까지
  함께 증발했다. 수정: secPr(과 colPr 감싼 ctrl)만 개별 제거, run은
  비었을 때만 정리.
- **새 id 채번 순서가 프로세스마다 비결정적(정리 트레인, v13 openrate
  생성기 제작 중 발견)**: 모든 재매핑 함수가 `_used_ids()`가 돌려주는
  평범한 `set[str]`을 그대로 순회하며 순차("최댓값+1") 채번기를 호출한다
  — 문자열 키의 set 순회 순서는 해시 무작위화에 좌우되는데, 이는
  프로세스 안에서는 고정이지만 **프로세스마다 달라진다**. 즉 같은 병합을
  새 프로세스에서 다시 돌리면 같은 old-id에 다른 new-id가 배정될 수
  있다(결과 문서 자체는 내부적으로 여전히 일관되고 참조도 무결하다 —
  숫자 배정만 달라진다). v13 생성기 자신의 결정성 검사(독립 두 회차
  sha256 대조)로 실증: authored-docmerge 10건 중 8건이 수정 전엔
  달랐고, 수정 후엔 0건. 수정: 채번기를 호출하는 모든 자리에서
  `sorted(used)`로 순회.
2. **왕복 보존**: 병합 결과를 저장 후 재오픈해도 무손실(`roundtrip_report`).
3. **기존 문서 바이트 불변**: 안 건드린 파트(끼워 넣지 않은 절, 무관한
   헤더 항목)는 patch 계열과 같은 원칙으로 그대로 — 다만 이 기능은
   전체 트리 재작성(tree-level)이라 byte-splice patch 계열의
   "untouched part = 압축 페이로드 그대로"와는 다른 증거 축이다.
   대신 "건드리지 않은 헤더 항목의 id·내용이 병합 전후 동일"을
   구조적으로 확인.
4. **실한컴 수용** — 이번 트레인은 생성만(오라클 없음). v13 스트라텀
   후보로 보고, 실측은 루트가 다음 배치에서 수행.

## 관련 문서

- [OWPML 편차 레지스트리](owpml-deviations.md) — DEV-013(subjectIDRef/
  instId), DEV-011(hp:parameterset)
- [편집기 표면 인벤토리](editor-surface-inventory.md) — 이 갭을 찾은
  메뉴 스캔
- [알려진 함정](known-traps.md)
