# 알려진 함정 사전 (Known Traps)

에이전트·자동화 코드가 python-hwpx로 문서를 다룰 때 실제로 밟아 본 함정들의
사전이다. 각 항목은 "무엇이, 왜, 어떻게 피하나"만 말한다. 이 문서는 패키지에
동봉되어 `hwpx.capabilities.contract_document("known-traps")`와 MCP 리소스로도
제공된다.

## 편집·저장

- **바이트-스플라이스 op의 `output_path`는 게이트 실패에도 쓴다.**
  `paragraph_patch`·`fill_cells`·`apply_table_ops`·`apply_body_ops` 계열은
  결과가 skip·불안전이어도 `output_path`를 주면 파일을 쓴다(전 op 스킵 시
  원본 바이트 그대로 기록). 합성 실행이 필요하면 `output_path` 없이 부르고
  쓰기를 직접 소유하거나, 처음부터 `hwpx.plan.apply_edit_plan`(all-or-nothing
  원자 실행)을 쓰라.
- **결과 `ok`는 "스킵 0 + open-safety 통과"다.** 스킵은 부분 적용이 아니라
  "그 항목은 건드리지 않았다"는 뜻이다 — `ok=False`인데 산출물을 채택하면
  무음 부분 적용이 된다.
- **`SavePipeline`의 `quality=None` 기본값은 strict다.** 내부 호출은 전부
  `QualityPolicy.transparent()`를 명시한다. 파이프라인을 직접 부를 때 기본값에
  의존하면 의도보다 강한 게이트로 거부될 수 있다.
- **`apply_table_ops`의 `delete_table` 여러 건은 역순으로.** 표 삭제는 후행
  `table_index`를 시프트한다 — 내림차순으로 배열하라(`hwpx.plan`의 정적
  린트가 위반을 경고한다).
- **`apply_body_ops` 인덱스는 실행 시점 문서 순서다.** 문단 삭제/삽입 op를
  섞으면 뒤 op의 인덱스가 밀린다 — 인덱스 기반 op는 문서 끝에서 앞으로.
- **저수준 `add_shape`/`add_control`은 OWPML 필수 하위 요소를 만들지 않는다.**
  그대로 저장하면 실한컴이 문서를 거부한다(경고 `UserWarning` 하나가 유일한
  신호). 도형은 전용 `add_line`/`add_rectangle`/`add_ellipse`를 쓰라.
- **텍스트를 갈아 끼우면 lineseg 캐시가 무효다.** 스플라이스 계열은 편집 문단의
  `<hp:linesegarray>`를 스스로 떨군다(안 떨구면 한컴이 옛 줄 자리에 새 글자를
  그려 겹침이 생긴다). 직접 XML을 만질 때도 같은 규칙을 지켜야 한다.

## 검증·오라클

- **렌더 검증 없이 "렌더된다"고 주장하지 말 것.** core는 렌더 백엔드를 동봉하지
  않는다(`RenderBackend` 주입 seam, 기본은 Unavailable). `render_checked=False,
  ok=True`는 "구조만 봤다"는 정직 degrade이지 시각 합격이 아니다. 시각 합격이
  필요하면 `require=True`(fail-closed) + 실한컴 오라클이 있는 환경에서.
- **`visual_complete_status="unverified"`는 합격이 아니다.** 렌더가 돌지 않은
  것이며, 어떤 경로도 이를 pass로 승격하지 않는다.
- **기본 테스트 스위트에서 라이브 한컴 렌더를 켜지 말 것.** 오라클은 환경
  의존이라 flake의 근원이다 — 라이브 렌더는 opt-in 게이트로만.

## 문서 구조

- **새 문서는 빈 줄로 시작한다.** `HwpxDocument.new()`의 첫 문단은 구역 설정
  (`hp:secPr`)을 담은 빈 문단이고, `add_paragraph()`는 그 뒤에 새 문단을 붙인다.
  첫 줄부터 쓰려면 첫 글은 `doc.paragraphs[0].text = ...`로 넣는다.
- **네이티브 목차는 `dirty="1"`이 재계산 트리거다.** 목차 삽입/문서 변경 후
  `mark_toc_dirty`를 잊으면 한컴이 옛 페이지 번호를 그대로 보여준다. dirty
  재생성 직후 같은 세션에서 export하면 한컴이 크래시할 수 있다(refresh와
  render는 세션 분리).
- **dirty 목차는 한컴이 수집 규칙대로 다시 만든다.** `add_native_toc(headings=...)`로
  개요가 아닌 문단을 제목으로 준 목차에 `dirty="1"`을 두면 한컴이 열면서 항목과
  링크를 버린다. 그래서 `headings`를 직접 주면 `dirty` 기본값은 `False`다.
- **본문 문단이 스타일 0(바탕글)이면 목차에 수집될 수 있다.** 한컴 목차 수집은
  스타일 기반이다 — 본문은 본문 스타일, 제목은 개요 스타일로.
- **메모 필드는 무음 수용 캐비앗이 있다.** `attach_memo_field`가 앵커를 못
  찾아도 조용히 넘어가는 경로가 있다(recipes의 mutation-semantics 표 참조) —
  결과 리포트의 실측 필드를 확인하라.
- **암호화 HWPX·HWP5 바이너리는 열리지 않는 게 정상이다.** 각각 파싱 예외·
  `BadZipFile`로 fail-closed 거부한다. 우회 API는 없다.
- **글자처럼 취급한 표는 쪽에서 나뉘지 않는다.** 한컴은 글자처럼 취급한 표
  (`add_table()`의 기본)와 `pageBreak="NONE"` 표를 쪽에서 나누지 않는다. 쪽 본문보다
  높은 표도 한 쪽에 그린다. 쪽 첫머리가 아니면 다음 쪽으로 옮기고, 아래 여백까지
  내려 그리며, 종이 아래 끝을 넘는 행은 그리지 않는다. `add_table()`은 만들 때
  행들만으로 쪽 본문보다 높은 표(행마다 적어도 셀 글 한 줄과 셀 위아래 여백)를
  흐르는 표로 만든다. 만든 뒤 행을 늘리거나 글을 채워 쪽을 넘게 된 표는 글자처럼
  취급 그대로이니 `table.set_treat_as_char(False)`로 흐르게 하라.
  `hwpx.layout.lint_layout`이 이런 표를 `TABLE_TALLER_THAN_PAGE`로 알린다.
- **`set_page_number()`의 번호는 한컴의 쪽 번호 감추기로 숨지 않는다.** 이 번호는
  머리말/꼬리말 안의 자동 번호 글이고, `set_visibility(hide_first_page_num=True)`와
  `hide_page_elements(page_num=True)`는 한컴 쪽 번호 컨트롤("쪽 번호 매기기")만
  감춘다. 첫 쪽에서 감추려면 `set_visibility(hide_first_footer=True)`(머리말이면
  `hide_first_header`), 한 쪽만 감추려면 `hide_page_elements(paragraph, footer=True)`를
  쓴다. `set_page_number()`는 그 머리말/꼬리말의 내용을 번호로 바꾼다.
- **`hide_page_elements()`는 그 쪽만 감춘다.** 한컴의 "현재 쪽만 감추기"와 같아서,
  문단이 있는 쪽에서만 숨고 다음 쪽부터는 다시 보인다.
- **줄 번호는 `show_line_number=True`일 때만 보인다.** `set_line_numbers()`는 모양
  (재시작·간격·거리·시작 번호)만 정한다. `set_visibility(show_line_number=True)`를
  함께 준다. `restart_type=1`이면 쪽마다 1부터 다시 센다.

## 계획 실행기(hwpx.plan) 자체의 정직 범위

- **저널은 재개(resume) 계약이 아니다.** 진단용 JSONL이다. 부분 재실행은
  지원하지 않는다 — 실패하면 계획을 고쳐 처음부터 다시 실행하라(실패 시 파일
  무접촉이므로 안전하다).
- **`journalPath`는 실패 시에도 쓰이는 유일한 파일 표면이다.** 문서 파일의
  무접촉 보장과 별개다(원하지 않으면 지정하지 말 것).
- **step `args`의 중첩 op 어휘는 스키마가 깊게 검증하지 않는다.** 실행-시
  해당 op의 fail-closed 검증이 진실 원천이다 — dry_run으로 전체 체인을 미리
  실행해 transcript를 확인하는 것이 가장 확실한 선검증이다.
