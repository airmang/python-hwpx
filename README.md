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

기존 문서는 손댄 곳만 고치고(미수정 영역은 바이트 그대로), 새 문서는 실제
한컴오피스가 받아들이는 형태로 만듭니다. HWPX는 ZIP+XML(OWPML/OPC) 구조라
Windows·macOS·Linux·CI 어디서든 순수 파이썬으로 동작합니다. 한컴오피스도
Windows도 필요하지 않으므로 **ChatGPT 채팅 환경에서도 HWPX 문서를 만들고
고칠 수 있습니다** — 파이썬이 도는 곳이면 됩니다.

| 계층 | 저장소 | 정본 책임 |
|---|---|---|
| Core | [`python-hwpx`](https://github.com/airmang/python-hwpx) | HWPX package/object model·OPC/OXML·직렬화·재사용 primitive |
| Automation | [`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation) | Python 자동화·워크플로·profile/policy·렌더·선택형 MCP adapter |
| Judgment | [`hwpx-plugins`](https://github.com/airmang/hwpx-plugins) | 에이전트 intent/genre 판단·ambiguity 처리·plugin/skill 가이드 |

이 저장소는 위 표의 Core 정본입니다. 5.0의 모듈 소유권, 삭제 경로 재등장
방지, 의존성 허용 범위는
[제품 경계 문서](docs/architecture/product-boundary.md)에 고정돼 있습니다.

> **Python 블록 판정:** 이 current manual의 모든 Python 블록은
> [실행 분류 ledger](docs/python-example-ledger.json)에 exact source digest와 함께
> 동결돼 있습니다. **독립 실행 예제** 표시가 없는 블록은 기존 입력 파일이나 앞
> 문맥을 요구하는 조각이며, 그대로 실행할 수 있는 예제로 간주하지 않습니다.

## 시작하기

```bash
pip install python-hwpx      # Python 3.10+
```

> **5.x 호환 extra:** `pip install "python-hwpx[visual]"`은 기존 설치 명령을
> 깨뜨리지 않기 위해 계속 허용되지만, `visual` extra는 비어 있어 PDF·이미지
> 렌더링 의존성을 설치하지 않습니다. 렌더·PDF 이미징 실행은
> `python-hwpx-automation[oracle]`이 소유합니다.

```python
from hwpx import HwpxDocument

doc = HwpxDocument.open("보고서.hwpx")
doc.add_paragraph("자동화로 추가한 문단입니다.")
doc.save_to_path("보고서-수정.hwpx")
```

백지에서 새 문서를 만들 때는 `HwpxDocument.new()`로 시작해 같은 API로
문단·표·머리말을 채우고 `save_to_path()`로 저장합니다.

문서 저작·양식 채움·시험지 조판 같은 상위 워크플로가 필요하면
[`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation)을
함께 설치하세요. MCP SDK 없이 같은 환경에서 그대로 동작합니다.

## 무엇을 하나

- **읽기·추출** — 텍스트/HTML/rich Markdown 내보내기(서식·중첩 표·각주 보존), XPath 객체 탐색
- **편집** — 문단·표·이미지·머리글/바닥글·메모·각주, 줄간격·여백·쪽번호 등 서식
- **양식 채우기** — 라벨·경로 기반 셀 채움, 바이트 보존 구조 편집(행·열·오토핏·shrink-to-fit)
- **생성·일괄 처리** — 문단·표·이미지·목차·상호참조 저작, 명시적 sanitizer 기반 mail merge, 텍스트 diff
- **변경추적·목차** — redline 저작, 네이티브 목차·상호참조
- **검증·안전** — 패키지 구조 검증 CLI, 열림 안전 게이트, 모든 쓰기에 영수증(`MutationReport`) — 번들 XSD는 느슨한 구조 스키마이며 OWPML 전체 검증은 아닙니다

자세한 내용: [사용 가이드](docs/usage.md) · [API 레퍼런스](https://airmang.github.io/python-hwpx/) · [안정 API 표면](docs/stable-api.md) · [예제](docs/examples.md)

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
전체 규칙은 [안전한 쓰기 계약](docs/safe-write-contract.md)에 있습니다.

## 실측으로 말합니다

산출물 전수를 실제 한컴오피스로 측정해 그대로 공개합니다(동결 코퍼스 N=497):

- **한컴 오픈 476/476 all-pass** — 우리가 만든 파일을 실한컴이 전부 엽니다
- **미수정 영역 바이트 보존 497/497** · 개인정보 0-leak
- **렌더 검증 416/476** + 정직 버킷 43 — 한컴 자체가 PDF export를 거부한 케이스도 숨기지 않고 집계
- 낮은 숫자도 그대로 발행합니다 — 전체 수치·주의사항: [실측 코퍼스 메트릭](https://airmang.github.io/python-hwpx/corpus-metrics.html)

기능별로 되는 것과 안 되는 것은 [지원 매트릭스](docs/support-matrix.md)에 등급으로
명시되어 있습니다. 현재 개발 상태는 Alpha입니다 — API는 바뀔 수 있습니다.

> 위 수치는 *생성물 수용률* 축입니다(만든 파일을 실한컴이 받는가). 문서 *파싱 recall*과는
> 다른 축이므로 파서 프로젝트 수치와 병치 비교하지 마세요.

## 어디서 쓰나

| 환경 | 무엇을 하면 되나 |
|---|---|
| 일반 ChatGPT 대화 | `.hwpx`를 올리고 `pip install python-hwpx` 후 파이썬으로 편집해 되받기 |
| 로컬·서버 파이썬 | `pip install python-hwpx` — 스크립트·배치·CI |
| 파이썬 자동화 (MCP 없이) | `pip install python-hwpx-automation` — 저작·양식 채움·검증 워크플로를 그냥 파이썬으로 |
| ChatGPT MCP 앱 | [`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation)의 MCP adapter를 커넥터로 등록 |
| Codex 마켓플레이스 플러그인 | [`hwpx-plugins`](https://github.com/airmang/hwpx-plugins) 설치 |
| Claude Code · Hermes · OpenClaw | 같은 MCP 서버를 각 클라이언트에 등록 ([`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation)) |

실측: 일반 ChatGPT 대화에 `.hwpx`를 올리고 python-hwpx 설치를 요청했을 때 PyPI
설치가 성공했고, 문서를 편집해 되받았습니다. 다만 파이썬 실행과 네트워크 허용
범위는 플랜·설정에 따라 다르므로 모든 계정에서 보장되는 경로는 아닙니다.
네트워크가 막힌 실행 환경에서는 wheel 파일을 함께 업로드하면 오프라인 설치로
같은 여정이 됩니다.

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

- `add_shape()` / `add_control()`은 한/글이 요구하는 모든 하위 요소를 생성하지 않는
  저수준 탈출구입니다. 그대로 저장한 문서는 한/글이 열지 못하며, 신호는 호출 시점의
  경고 하나뿐입니다(저장도 패키지 검증도 막지 않습니다). 도형은 `add_line()` /
  `add_rectangle()` / `add_ellipse()`를 쓰세요.
- 그림은 단순 개체 생성까지 지원하며, 그룹·효과 같은 복잡 개체 생성은 미지원입니다.
- 암호화된 HWPX는 지원하지 않습니다.

## 기여하기

[help wanted](https://github.com/airmang/python-hwpx/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22) ·
[로드맵](https://github.com/airmang/python-hwpx/milestones) ·
[Discussions](https://github.com/airmang/python-hwpx/discussions) ·
[내부 실전 가이드](docs/internals/) ·
[CONTRIBUTING](CONTRIBUTING.md)

HWPX 내부 구조가 처음이라면 [내부 실전 가이드](docs/internals/)부터 — 실제 한/글
동작에서 확인된 조판 캐시·목차 필드·OPC 재패킹 같은 실전 지식을 정리해 두었습니다.

## 감사의 말

아래 공개 표준·프로젝트에 빚지고 있습니다.

- **[OWPML — 개방형 워드프로세서 마크업 언어 (KS X 6101)](https://www.kssn.net/search/stddetail.do?itemNo=K001010119985)** — HWPX가 기반하는 한국 산업 표준
- **[hancom-io/hwpx-owpml-model](https://github.com/hancom-io/hwpx-owpml-model)** — OWPML 요소 구조 참조 모델 · **[neolord0/hwpxlib](https://github.com/neolord0/hwpxlib)** — 오라클 샘플 코퍼스
- **[edwardkim/rhwp](https://github.com/edwardkim/rhwp)** — 멱등성·검증 게이트 설계 영감
- **범정부오피스** — 공무 문서 편집 워크플로 아이디어

## License · Maintainer

Apache-2.0 ([LICENSE](LICENSE) · [NOTICE](NOTICE)) — **Kohkyuhyun** [@airmang](https://github.com/airmang) · [kokyuhyun@hotmail.com](mailto:kokyuhyun@hotmail.com)
