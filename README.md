<p align="center">
  <h1 align="center">python-hwpx</h1>
  <p align="center">
    <strong>한컴 없이 HWPX를 읽고, 고치고, 만드는 순수 파이썬 라이브러리</strong>
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

한컴오피스가 없어도 됩니다. HWPX는 ZIP+XML(OWPML) 포맷이라 순수 파이썬만으로
읽고, 고치고, 새로 만들 수 있습니다 — Windows·macOS·Linux·CI, 그리고
**파이썬이 도는 ChatGPT 채팅 안에서도** 그대로 동작합니다. 기존 문서는 손댄
곳만 바뀌고 나머지는 바이트 그대로 유지되며, 새 문서는 실제 한컴오피스가 여는
형태로 만들어집니다.

<p align="center">
  <img src="https://raw.githubusercontent.com/airmang/python-hwpx/main/docs/assets/chatgpt-formfill.png" width="760" alt="일반 ChatGPT 대화에 hwpx 양식을 올려 지도안 작성을 부탁하고, 양식이 유지된 채 채워진 문서를 돌려받는 화면">
</p>
<p align="center"><sub>일반 ChatGPT 대화 — 양식 <code>.hwpx</code>를 올리고 말로 부탁하면, 서식을 유지한 채 채워진 문서가 돌아옵니다.</sub></p>

**ChatGPT에서 그대로 따라 하기** — 문서를 올리면서 이렇게 부탁하면 됩니다:

```text
이 .hwpx 파일을 python-hwpx 라이브러리로 열어서 작업해줘.
(pip install python-hwpx 로 설치하면 돼)
양식과 서식은 그대로 두고, ○○만 바꿔서 새 파일로 돌려줘.
```

설치부터 결과 파일까지 대화 안에서 끝납니다 — 내 컴퓨터에 파이썬이 없어도 됩니다.
AI 도구가 정확한 API를 배우도록 [llms.txt](https://airmang.github.io/python-hwpx/llms.txt)도 제공합니다.

| | 저장소 | 역할 |
|---|---|---|
| 📦 | [`python-hwpx`](https://github.com/airmang/python-hwpx) | HWPX 문서를 읽고·고치고·만드는 순수 파이썬 엔진 |
| 🔌 | [`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation) | 저작·양식 채움 워크플로, `hwpx` CLI, 선택형 MCP 서버 |
| 🎯 | [`hwpx-plugins`](https://github.com/airmang/hwpx-plugins) | 에이전트가 알맞은 도구를 고르도록 돕는 플러그인/스킬 번들 |

## 시작하기

```bash
pip install python-hwpx      # Python 3.10+
```

```python
from hwpx import HwpxDocument

doc = HwpxDocument.open("보고서.hwpx")
doc.add_paragraph("자동화로 추가한 문단입니다.")
doc.save_to_path("보고서-수정.hwpx")
```

백지에서 시작할 때는 `HwpxDocument.new()`로 만들어 같은 API로 문단·표·머리말을
채우면 됩니다. 문서 저작·양식 채움·시험지 조판 같은 상위 워크플로가 필요하면
[`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation)을
함께 설치하세요.

> 기존 설치 명령 호환을 위해 `pip install "python-hwpx[visual]"`도 계속
> 동작합니다. 다만 이 extra는 비어 있어 렌더·PDF 의존성을 설치하지 않습니다 —
> 그 역할은 `python-hwpx-automation[oracle]`이 맡습니다.

## 무엇을 하나

- **읽기·추출** — 텍스트/HTML/Markdown 내보내기 (서식·중첩 표·각주 보존)
- **편집** — 문단·표·이미지·머리글/바닥글·메모·각주, 줄간격·여백·쪽번호 같은 서식
- **양식 채우기** — 라벨로 셀을 찾아 값만 채우기, 행·열 조정 같은 구조 편집도 바이트 보존으로
- **생성·일괄 처리** — 새 문서 저작, 목차·상호참조, mail merge, 텍스트 diff, 변경추적(redline)
- **검증·안전** — 패키지 구조 검증 CLI, 열림 안전 게이트, 모든 저장에 영수증(`MutationReport`)

자세한 내용: [5분 퀵스타트](docs/quickstart.md) · [사용 가이드](docs/usage.md) · [API 레퍼런스](https://airmang.github.io/python-hwpx/) · [예제](docs/examples.md)

### 양식 채우기 — 서식은 그대로, 값만

```python
doc = HwpxDocument.open("신청서.hwpx")
result = doc.fill_by_path({
    "성명 > right": "홍길동",
    "소속 > right": "플랫폼팀",
})
doc.save_to_path("신청서-작성완료.hwpx")
```

라벨 기준으로 셀을 찾아 채우고, 손대지 않은 영역은 원본 바이트가 그대로 유지됩니다.

### 저장에는 영수증이 따라옵니다

```python
report = doc.save_to_path("결과.hwpx", return_report=True)
print(report.actual_mode)        # "patch" — 문서 재조립 없이 저장됨
print(report.preservation.untouched_part_payloads.to_dict())
                                 # {"verified": 17, "changed": 0}
```

요청한 보존 등급을 지킬 수 없으면 아무것도 쓰지 않고 실패합니다(fail-closed).
전체 규칙: [안전한 쓰기 계약](docs/safe-write-contract.md).

*예제 중 **독립 실행 예제** 표시가 없는 블록은 여러분의 기존 문서를 입력으로
쓰는 조각입니다. 예제별 Python 블록 판정은
[실행 ledger](docs/python-example-ledger.json)에 동결돼 있습니다.*

## 실측으로 말합니다

만든 파일이 실제 한컴오피스에서 열리는지 재서 그대로 공개합니다. 측정마다
스택과 날짜를 병기합니다:

- **한컴 열림 120/120 · 렌더 검증 120/120** — 현행 스택(5.7.0 · 실한컴
  12.0.0.3288 · 2026-08-03)의 축소 측정: 기준 스트라텀 + 신규 저작 표면
  6종(각주·누름틀·수식·차트·체크박스·편집 계획). 영수증은 행마다 bucket이
  있어 `jq` 한 줄로 재현됩니다
- **한컴 열림 476/476** — 전수 동결 코퍼스(N=497) 측정
  (3.4.1 · 실한컴 12.0.0.3288 · 2026-07-19)
- **미수정 영역 바이트 보존 497/497** · 개인정보 유출 0
- **렌더 검증 416/476** — 한컴 자체가 PDF 내보내기를 거부한 43건도 숨기지 않고 집계
- 전체 수치와 주의사항: [실측 코퍼스 메트릭](https://airmang.github.io/python-hwpx/corpus-metrics.html) · 기능별 등급: [지원 매트릭스](docs/support-matrix.md)

<p align="center">
  <img src="https://raw.githubusercontent.com/airmang/python-hwpx/main/docs/assets/hancom-open-generated.png" width="760" alt="ChatGPT 실행 환경에서 python-hwpx로 생성한 HWPX 문서를 실제 한컴오피스에서 연 모습">
</p>
<p align="center"><sub>ChatGPT 실행 환경에서 생성한 문서를 실제 한컴오피스로 연 모습.</sub></p>

현재 개발 상태는 Alpha입니다 — API는 바뀔 수 있습니다.

> 위 수치는 "만든 파일을 실한컴이 받아주는가"라는 축입니다. 문서 파싱 성능과는
> 다른 축이므로 파서 프로젝트 수치와 직접 비교하지 마세요.

## 어디서 쓰나

| 환경 | 무엇을 하면 되나 |
|---|---|
| 일반 ChatGPT 대화 | `.hwpx`를 올리고 `pip install python-hwpx` 후 파이썬으로 편집해 되받기 |
| 로컬·서버 파이썬 | `pip install python-hwpx` — 스크립트·배치·CI |
| 파이썬 자동화 (MCP 없이) | `pip install python-hwpx-automation` — 저작·양식 채움·검증 워크플로를 그냥 파이썬으로 |
| ChatGPT MCP 앱 | [`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation)의 MCP adapter를 커넥터로 등록 |
| Codex 마켓플레이스 플러그인 | [`hwpx-plugins`](https://github.com/airmang/hwpx-plugins) 설치 |
| Claude Code · Hermes · OpenClaw | 같은 MCP 서버를 각 클라이언트에 등록 ([`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation)) |

실제로 일반 ChatGPT 대화에 `.hwpx`를 올리고 설치를 부탁했을 때 PyPI 설치와
편집·되받기까지 동작하는 것을 확인했습니다. 파이썬 실행과 네트워크 허용 범위는
플랜·설정에 따라 다르며, 네트워크가 막힌 환경에서는 wheel 파일을 함께 올리면
오프라인 설치로 같은 여정이 됩니다.

## 비교

| | python-hwpx | pyhwpx | pyhwp |
|---|---|---|---|
| **대상 포맷** | `.hwpx` (OWPML/OPC) | `.hwpx` | `.hwp` (v5 바이너리) |
| **한/글 설치** | 불필요 | 필요 (Windows COM) | 불필요 |
| **크로스 플랫폼** | ✅ Linux / macOS / Windows / CI | ❌ Windows 전용 | ✅ |
| **편집/생성 API** | ✅ | ✅ (COM) | ❌ 대부분 읽기 |
| **AI 에이전트 연동 (MCP)** | ✅ companion 경유 | ❌ | ❌ |

> HWP(v5 바이너리)는 지원하지 않습니다. 한컴오피스에서 HWPX로 변환 후 사용하세요.

## 알려진 제약

- `add_shape()` / `add_control()`은 저수준 탈출구라, 그대로 저장하면 한/글이
  열지 못하는 파일이 됩니다(호출 시 경고만 나옵니다). 도형은 `add_line()` /
  `add_rectangle()` / `add_ellipse()`를 쓰세요.
- 그림은 단순 개체 생성까지 지원합니다 (그룹·효과 미지원).
- 암호화된 HWPX는 지원하지 않습니다.

## 기여하기

[help wanted](https://github.com/airmang/python-hwpx/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22) ·
[로드맵](https://github.com/airmang/python-hwpx/milestones) ·
[Discussions](https://github.com/airmang/python-hwpx/discussions) ·
[CONTRIBUTING](CONTRIBUTING.md)

HWPX 내부 구조가 처음이라면 [내부 실전 가이드](docs/internals/)부터 — 실제 한/글
동작에서 확인된 조판 캐시·목차 필드·OPC 재패킹 같은 실전 지식을 정리해 두었습니다.
공개 API의 안정 범위는 [안정 API 표면](docs/stable-api.md), 계층 간 소유권은
[제품 경계 문서](docs/architecture/product-boundary.md)에 있습니다.

## 감사의 말

아래 공개 표준·프로젝트에 빚지고 있습니다.

- **[OWPML — 개방형 워드프로세서 마크업 언어 (KS X 6101)](https://www.kssn.net/search/stddetail.do?itemNo=K001010119985)** — HWPX가 기반하는 한국 산업 표준
- **[hancom-io/hwpx-owpml-model](https://github.com/hancom-io/hwpx-owpml-model)** — OWPML 요소 구조 참조 모델 · **[neolord0/hwpxlib](https://github.com/neolord0/hwpxlib)** — 오라클 샘플 코퍼스
- **[edwardkim/rhwp](https://github.com/edwardkim/rhwp)** — 멱등성·검증 게이트 설계 영감
- **범정부오피스** — 공무 문서 편집 워크플로 아이디어

## License · Maintainer

Apache-2.0 ([LICENSE](LICENSE) · [NOTICE](NOTICE)) — **Kohkyuhyun** [@airmang](https://github.com/airmang) · [kokyuhyun@hotmail.com](mailto:kokyuhyun@hotmail.com)
