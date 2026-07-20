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
| 문단·표 저작/편집 | Parse·Preserve·Edit·Create·Render-verified | corpus-metrics「오픈 수용률」476/476, 「저작 품질 게이트」실저작 58/58, 「렌더 검증」416건 |
| 표 구조 변경(행·열·표 삭제/삽입, 열 오토핏) | Preserve·Edit | `hwpx.table_patch`; corpus-metrics「바이트 보존」497/497(patch 경로) |
| 양식 채움(byte-splice) | Preserve·Edit | `hwpx.patch`·`table_patch`·`body_patch`; corpus-metrics「바이트 보존」497/497. wild 공개 양식의 서식 충실은 구조결함 픽스 후 **무음 서식파괴 16.7%**(판정 66조합, 불가능 타깃은 typed 거부 35건·산출분 pass 17/28) — 잔여는 페이지 리플·표 shape 2부류로 명명(「구조결함 1차 실측」절) |
| 그림 삽입/치환 | Edit·Create | `add_picture`·`add_image`·`replace_picture`. `<hp:pic>` 완전 자동 생성과 복잡 개체는 미제공이므로 한컴에서 확인 권장(README「알려진 제약」) |
| 차트 | Unsupported-but-preserved | 차트 생성 API 없음(kordoc 흡수 갭). 기존 차트 part는 patch 저장 시 바이트 보존(497/497) |
| 수식 | Parse·Unsupported-but-preserved | 코어에 수식 저작 API 없음. 기존 수식 개체는 파싱·patch 보존됨(수식 미리보기 렌더는 뷰어/플러그인 계층) |
| 변경추적(redline) | Edit·Create | `add_tracked_insert`·`add_tracked_delete`·`add_tracked_replace`; 실 Windows 한컴 COM `IsTrackChange=1`·검토 리본 수락/거부 스파이크. **렌더 주의**: 한컴이 변경추적 문서의 PDF export 자체를 거부 → corpus-metrics「렌더 검증」에서 `render_unavailable`로 정직 집계(결함 아님, 한컴 제약) |
| 메모(코멘트) | Edit·Create·Render-verified | `add_memo`·`add_memo_with_anchor`; subList 코멘트 텍스트 + `MemoShapeIDRef` 버그 수정을 실 Windows 한컴에서 검증(CHANGELOG) |
| 각주/미주 | Edit·Create | `add_footnote`·`add_endnote`; M6 읽기 경로에서 note 노출. 렌더 독립 게이트는 미측정 |
| 네이티브 목차(TOC)/상호참조 | Create·Render-verified | `hwpx.tools.toc_author.add_native_toc`·`mark_toc_dirty`·`toc_verify`; corpus-metrics「네이티브 목차」구조 15/15, 실한컴 재계산 후 페이지 정합 5/5 |
| 암호화 HWPX | Unsupported-and-rejected | 복호화 API 없음. 암호화된 content part는 파싱 단계에서 예외(`XMLSyntaxError`)로 거부 — 무음으로 잘못된 문서를 만들지 않음(fail-closed) |
| HWP 5.x 바이너리 | Unsupported-and-rejected | HWP v5는 ZIP이 아니므로 열기 시 `BadZipFile` 예외. 한컴에서 HWPX로 변환 후 사용(README「대항 라이브러리 비교」주석) |
| 누름틀(form field) 생성 | Parse·Edit | `list_form_fields`·`fill_form_field`로 기존 누름틀 조회·서식 보존 채움. **신규 누름틀 생성 전용 도구는 미제공**(list/fill 한정) |

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
  보존됨을 뜻한다(차트·수식). 새로 만들거나 편집하는 기능은 제공하지 않는다.

## 관련 문서

- [실측 코퍼스 메트릭](corpus-metrics.md) — 각 수치의 분모·판정자·측정 방법론
- [안전한 쓰기 계약](safe-write-contract.md) — 보존 등급과 `MutationReport` 영수증
