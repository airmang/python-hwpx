<p align="center">
  <h1 align="center">python-hwpx</h1>
  <p align="center">
    <strong>한컴오피스 없이 한/글 문서(HWPX·HWP)를 읽고 고치고 만드는 파이썬 라이브러리</strong>
  </p>
  <p align="center">
    <a href="https://pypi.org/project/python-hwpx/"><img src="https://img.shields.io/pypi/v/python-hwpx?color=blue&label=PyPI" alt="PyPI"></a>
    <a href="https://pepy.tech/project/python-hwpx"><img src="https://static.pepy.tech/badge/python-hwpx/month" alt="Downloads"></a>
    <a href="https://pypi.org/project/python-hwpx/"><img src="https://img.shields.io/pypi/pyversions/python-hwpx" alt="Python"></a>
    <a href="https://github.com/airmang/python-hwpx/actions/workflows/tests.yml"><img src="https://img.shields.io/github/actions/workflow/status/airmang/python-hwpx/tests.yml?branch=main&label=tests" alt="Tests"></a>
    <a href="https://airmang.github.io/python-hwpx/corpus-metrics.html"><img src="https://img.shields.io/endpoint?url=https%3A%2F%2Fairmang.github.io%2Fpython-hwpx%2F_static%2Fbadge-hancom-open.json" alt="Hancom open"></a>
    <a href="https://github.com/airmang/python-hwpx/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="License"></a>
  </p>
</p>

<p align="center">한국어 | <a href="README_EN.md">English</a></p>

HWPX는 ZIP 안에 XML(OWPML)을 담은 형식이라, 한컴오피스가 없어도 파이썬만으로 다룰 수 있습니다.
python-hwpx는 Windows·macOS·Linux·CI 어디서나 돌고 의존성은 `lxml` 하나입니다. HWP 5.0(`.hwp`)도 같은
API로 열고 저장합니다.

만든 문서는 한컴오피스 2024에서 직접 열어 보고 그 결과를 날짜와 함께
[아래](#한글과-얼마나-같은가)에 적어 둡니다.

## 시작하기

```bash
pip install python-hwpx      # Python 3.10+
```

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

doc = HwpxDocument.new()
doc.add_heading("2026 운영계획", level=1)
doc.add_paragraph("추진 배경", style="개요 2")  # 한/글이 "가." 번호를 붙인다
doc.save_to_path("계획.hwpx")
```

스타일은 이름으로 고릅니다. 없는 이름을 쓰면 그 줄에서 바로 오류가 납니다.
있는 문서를 고칠 때는 `HwpxDocument.open("보고서.hwpx")`로 시작합니다. `.hwp`도 똑같이 열고,
`save_to_path("보고서.hwp")`로 HWP 5.0으로 저장할 수 있습니다.

문서 저작·양식 채움·시험지 조판 같은 상위 워크플로가 필요하면
[`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation)을 함께 설치하세요.

> 예전 설치 명령을 위해 `pip install "python-hwpx[visual]"`도 계속 됩니다. 다만 이 extra는 비어 있어
> 렌더·PDF 의존성을 설치하지 않습니다. 그 일은 `python-hwpx-automation[oracle]`이 맡습니다.

## 할 수 있는 것

- 읽기·추출: 텍스트·HTML·Markdown으로 내보냅니다. 서식, 표 안의 표, 각주를 살립니다.
- 편집: 문단·표·그림·머리말/꼬리말·메모·각주, 줄 간격·여백·쪽 번호 같은 서식을 고칩니다.
- 양식 채우기: 라벨로 칸을 찾아 값만 넣고 손대지 않은 부분은 바이트 그대로 둡니다. FormFit은 값이
  칸에 들어가도록 줄을 바꾸거나 글자를 줄일지 한/글의 글자 폭으로 재서 고릅니다.
- 표 구조 편집: 행·열 넣기와 지우기, 칸 나누기와 합치기. `doc.tables[0]`처럼 번호로 표를 꺼냅니다.
- 만들기·일괄 처리: 새 문서, 목차·상호 참조, 메일 머지, 문서 비교, 변경 추적.
- HWP 5.0: `.hwp`를 HWPX로 읽어 같은 API로 고치고 `.hwp`로 저장합니다. 옮기지 못한 내용은
  `document.conversion_report`에 남습니다.
- 배치 추정(실험): `estimate_pages`는 한/글 없이 쪽 수와 줄마다의 쪽·세로 위치를 추정합니다.
  `write_line_caches`는 한/글이 저장할 때 쓰는 줄 배치 정보를, 한/글과 같은 값을 확실히 아는 문단에만 씁니다.
  rhwp처럼 이 정보로 그림 자리를 찾는 뷰어에서도 그림이 보이게 됩니다. 기본으로는 쓰지 않습니다.
- 검증·안전: 패키지 구조 검사 CLI, 저장 전 열림 검사, 저장 결과 보고(`return_report=True`).

자세한 내용: [5분 퀵스타트](docs/quickstart.md) · [사용 가이드](docs/usage.md) · [API 레퍼런스](https://airmang.github.io/python-hwpx/) · [예제](docs/examples.md) · [지원 매트릭스](docs/support-matrix.md)

### 양식 채우기 예

```python
doc = HwpxDocument.open("신청서.hwpx")
values = {
    "성명 > right": "홍길동",
    "소속 > right": "플랫폼팀",
}
result = doc.tables.fill_by_path(values)
if result["failed_count"] or result["applied_count"] != len(values):
    raise ValueError(result["failed"])
report = doc.save_to_path("신청서-작성완료.hwpx", mode="patch", fallback="error", return_report=True)
```

라벨이 겹치거나 없으면 실패로 돌려주고 저장하기 전에 멈출 수 있습니다. `mode="patch"`는 고치지 않은
ZIP 파트를 바이트 그대로 두라는 뜻입니다. 고친 파트 안쪽과 화면 배치는 따로 확인해야 합니다. 저장한 파일을
다시 열어 내용까지 확인하는 방법은 [안전한 쓰기 계약](docs/safe-write-contract.md)에 있습니다.

*독립 실행 예제로 표시하지 않은 블록은 여러분이 가진 문서를 입력으로 쓰는 조각입니다. 예제별 Python 블록 판정은
[실행 기록](docs/python-example-ledger.json)에 남겨 둡니다.*

## 한/글과 얼마나 같은가

만든 파일을 실제 한컴오피스로 열어 보고 그대로 적습니다. 숫자마다 잰 날짜와 프로그램 판을 붙입니다.

**배치: python-hwpx 6.9 이후 main · 2026-10-25**

| 무엇을 | 정답 | 결과 |
|---|---|---|
| 공개 실문서 77건의 줄 나눔이 같은 문단 | 한컴오피스 2024 (Windows)가 배치해 저장한 것 | 8,246 / 8,263 (99.8 %) |
| 그 77건 중 모든 줄의 쪽·위치가 같은 문서 | 같음 | 76 / 77 (나머지 1건은 표가 깨진 문서) |
| 줄 배치 정보를 지운 사본으로 추정한 쪽 수가 같은 문서 (공개 79 · 비공개 실문서 522 · 기능 시험 문서 780) | 그 문서를 저장한 한/글의 쪽 수 | 1,344 / 1,381 (추정하지 않음 16) |

**열림: 한컴오피스 12 (macOS)**

- 한컴에서 열림 120/120, 렌더 검증 120/120: 기준 문서와 저작 기능 6종(각주·누름틀·수식·차트·체크박스·편집
  계획)을 줄여서 잰 것 (5.7.0 · 2026-08-03)
- 한컴에서 열림 476/476: 동결한 코퍼스 전체(N=497) (3.4.1 · 2026-07-19)
- 고치지 않은 영역의 바이트 보존 497/497, 개인정보 유출 0
- 렌더 검증 416/476: 한컴이 PDF 내보내기를 거부한 43건도 빼지 않고 셌습니다.

<p align="center">
  <img src="https://raw.githubusercontent.com/airmang/python-hwpx/main/docs/assets/hancom-open-generated.png" width="760" alt="ChatGPT 실행 환경에서 python-hwpx로 생성한 HWPX 문서를 실제 한컴오피스에서 연 모습">
</p>
<p align="center"><sub>ChatGPT 실행 환경에서 만든 문서를 실제 한컴오피스로 연 모습.</sub></p>

전체 숫자와 주의할 점은 [실측 코퍼스 메트릭](https://airmang.github.io/python-hwpx/corpus-metrics.html)에,
기능별 등급은 [지원 매트릭스](docs/support-matrix.md)에 있습니다. 이 숫자들은 "만든 파일을 한/글이 어떻게
받는가"를 잰 것이고 파서가 문서를 얼마나 잘 읽는지와는 다른 지표입니다.

개발 단계는 Beta입니다. 하위 호환을 지키는 범위는 [안정 API 표면](docs/stable-api.md)에 적혀 있고,
`hwpx.experimental`과 위에서 "실험"이라고 적은 기능은 바뀔 수 있습니다.

## 어디서 쓰나

| 환경 | 방법 |
|---|---|
| 로컬·서버 파이썬 | `pip install python-hwpx` (스크립트·배치·CI) |
| 파이썬 자동화 (MCP 없이) | `pip install python-hwpx-automation` (저작·양식 채움·검증 워크플로) |
| 일반 ChatGPT 대화 | `.hwpx`와 [Release wheel](https://github.com/airmang/python-hwpx/releases/latest)을 함께 올려 대화 안에서 설치([안내](docs/ai-assistants.md)) |
| ChatGPT MCP 앱 | [`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation)의 MCP adapter를 커넥터로 등록 |
| Codex 마켓플레이스 플러그인 | [`hwpx-plugins`](https://github.com/airmang/hwpx-plugins) 설치 |
| Claude Code · Hermes · OpenClaw | 같은 MCP 서버를 각 클라이언트에 등록 ([`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation)) |

<p align="center">
  <img src="https://raw.githubusercontent.com/airmang/python-hwpx/main/docs/assets/chatgpt-formfill.png" width="760" alt="일반 ChatGPT 대화에 hwpx 양식을 올려 지도안 작성을 부탁하고, 양식이 유지된 채 채워진 문서를 돌려받는 화면">
</p>
<p align="center"><sub>일반 ChatGPT 대화에서 양식 <code>.hwpx</code>를 올리고 부탁하면, 서식은 그대로이고 값만 채운 문서가 돌아옵니다.</sub></p>

ChatGPT 채팅의 파이썬 환경은 PyPI에 접속하지 못합니다. 그래서 [최신 Release](https://github.com/airmang/python-hwpx/releases/latest)의
`python_hwpx-*.whl`을 문서와 함께 올리고 이렇게 부탁합니다.

```text
첨부한 python_hwpx-*.whl 을 pip 로 설치한 다음(pip install /mnt/data/python_hwpx-*.whl),
이 .hwpx 파일을 python-hwpx 라이브러리로 열어서 작업해줘.
양식과 서식은 그대로 두고, ○○만 바꿔서 새 파일로 돌려줘.
```

설치부터 결과 파일까지 대화 안에서 끝나므로 내 컴퓨터에 파이썬이 없어도 됩니다. wheel의 의존성은 `lxml`
하나이고 실행 환경에 없으면 lxml wheel도 함께 올립니다. 에이전트용 지시문은 [AI 채팅 환경에서 쓰기](docs/ai-assistants.md)에,
AI 도구가 API를 정확히 익히도록 만든 [llms.txt](https://airmang.github.io/python-hwpx/llms.txt)도 있습니다.

| | 저장소 | 역할 |
|---|---|---|
| 📦 | [`python-hwpx`](https://github.com/airmang/python-hwpx) | HWPX 문서를 읽고·고치고·만드는 순수 파이썬 엔진 |
| 🔌 | [`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation) | 저작·양식 채움 워크플로, `hwpx` CLI, 선택형 MCP 서버 |
| 🎯 | [`hwpx-plugins`](https://github.com/airmang/hwpx-plugins) | 에이전트가 알맞은 도구를 고르도록 돕는 플러그인/스킬 번들 |

## 비교

| | python-hwpx | pyhwpx | pyhwp |
|---|---|---|---|
| **다루는 형식** | `.hwpx`, `.hwp` (HWP 5.0) 읽기·쓰기 | `.hwpx` | `.hwp` (v5 바이너리) |
| **한/글 설치** | 필요 없음 | 필요 (Windows COM) | 필요 없음 |
| **운영체제** | Linux / macOS / Windows / CI | Windows 전용 | Linux / macOS / Windows |
| **편집·생성** | ✅ | ✅ (한/글이 함) | 대부분 읽기 |
| **한/글 없이 쪽 수 추정** | ✅ (실험) | 한/글이 계산 | ❌ |
| **AI 에이전트 연동 (MCP)** | ✅ (automation 경유) | ❌ | ❌ |

## 알려진 제약

- `add_shape()`·`add_control()`은 저수준 탈출구라, 그대로 저장하면 한/글이 열지 못하는 파일이 됩니다(부를 때
  경고만 나옵니다). 도형은 한/글이 요구하는 하위 요소까지 만드는 `add_line()`·`add_rectangle()`·`add_ellipse()`·
  `add_arc()`·`add_polygon()`·`add_curve()`·`add_connector()`·`add_container()`(묶음)를, 컨트롤은
  `add_column_definition()`·`add_bookmark()`·`add_hyperlink()`를 쓰세요.
- 그림은 밝기·대비·회색조·흑백·투명도, 실선 테두리, 자르기(`crop`), 그림자·빛남·부드러운 가장자리·반사
  (`shadow`·`glow`·`soft_edge`·`reflection`)를 `add_picture()` 인자로 줄 수 있습니다. 뒤집기와 회전은 아직 안 됩니다.
- 쪽 수 추정과 줄 배치 정보 쓰기는 실험 기능입니다. 따르지 못하는 요소가 있으면 추정하지 않고 까닭을 돌려줍니다.
  지금은 줄 배치 정보 없이 글자 격자를 쓰는 문단, 그리고 표 칸 안에서 글 사이에 놓이거나 떠 있는 표 가운데 쪽 끝이
  어울림·글 뒤·앞 표나 여러 줄짜리 행을 가로지르는 경우가 여기에 듭니다. 그 밖의 칸 안 표는 쪽 끝에서 행 사이로 나뉘는
  것까지 한/글처럼 배치합니다. 표를 읽고 고치는 기능은 이와 상관없이 표 안의 표까지 다룹니다.
- 암호를 건 HWPX와 암호·배포용 HWP는 지원하지 않습니다(HWP는 `Hwp5Error`로 거부합니다).

## 기여하기

[help wanted](https://github.com/airmang/python-hwpx/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22) ·
[로드맵](https://github.com/airmang/python-hwpx/milestones) ·
[Discussions](https://github.com/airmang/python-hwpx/discussions) ·
[CONTRIBUTING](CONTRIBUTING.md)

HWPX 내부 구조가 처음이라면 [내부 실전 가이드](docs/internals/)부터 보세요. 실제 한/글 동작으로 확인한 조판
캐시, 목차 필드, OPC 재압축 같은 내용을 정리해 두었습니다. 공개 API의 안정 범위는 [안정 API 표면](docs/stable-api.md),
계층 사이의 소유권은 [제품 경계 문서](docs/architecture/product-boundary.md)에 있습니다.

## 감사의 말

아래 공개 표준과 프로젝트에 빚지고 있습니다.

- [OWPML, 개방형 워드프로세서 마크업 언어 (KS X 6101)](https://www.kssn.net/search/stddetail.do?itemNo=K001010119985): HWPX의 바탕인 한국 산업 표준
- [hancom-io/hwpx-owpml-model](https://github.com/hancom-io/hwpx-owpml-model): OWPML 요소 구조 참조 모델
- [neolord0/hwpxlib](https://github.com/neolord0/hwpxlib): 견본 코퍼스
- [edwardkim/rhwp](https://github.com/edwardkim/rhwp): 멱등성·검증 게이트 설계에서 영감을 받았고 다른 뷰어 호환을 확인할 때 씁니다
- 범정부오피스: 공무 문서 편집 워크플로 아이디어

## License · Maintainer

Apache-2.0 ([LICENSE](LICENSE) · [NOTICE](NOTICE)) · Kohkyuhyun [@airmang](https://github.com/airmang) · [kokyuhyun@hotmail.com](mailto:kokyuhyun@hotmail.com)
