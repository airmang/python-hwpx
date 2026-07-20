<p align="center">
  <h1 align="center">python-hwpx</h1>
  <p align="center">
    <strong>한컴 없이 HWPX를 읽고, 고치고, 만드는 순수 파이썬 라이브러리</strong>
  </p>
  <p align="center">
    <a href="https://pypi.org/project/python-hwpx/"><img src="https://img.shields.io/pypi/v/python-hwpx?color=blue&label=PyPI" alt="PyPI"></a>
    <a href="https://pypi.org/project/python-hwpx/"><img src="https://img.shields.io/pypi/pyversions/python-hwpx" alt="Python"></a>
    <a href="https://github.com/airmang/python-hwpx/actions/workflows/tests.yml"><img src="https://img.shields.io/github/actions/workflow/status/airmang/python-hwpx/tests.yml?branch=main&label=tests" alt="Tests"></a>
    <a href="https://airmang.github.io/python-hwpx/corpus-metrics.html"><img src="https://img.shields.io/endpoint?url=https%3A%2F%2Fairmang.github.io%2Fpython-hwpx%2F_static%2Fbadge-hancom-open.json" alt="Hancom open"></a>
    <a href="https://github.com/airmang/python-hwpx/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="License"></a>
  </p>
</p>

<p align="center">한국어 | <a href="README_EN.md">English</a></p>

기존 문서는 손댄 곳만 고치고(미수정 영역은 바이트 그대로), 새 문서는 실제
한컴오피스가 받아들이는 형태로 만듭니다. 산출물은 실제 한컴으로 전수 측정해
그대로 공개합니다 — [실측 코퍼스 메트릭](https://airmang.github.io/python-hwpx/corpus-metrics.html).

| | 레포 | 역할 |
|---|---|---|
| 📦 | **`python-hwpx`** | 순수 파이썬 HWPX 코어 (이 레포) |
| 🔌 | [`hwpx-mcp-server`](https://github.com/airmang/hwpx-mcp-server) | MCP 클라이언트(Claude Desktop 등)에서 HWPX 조작 |
| 🎯 | [`hwpx-plugin`](https://github.com/airmang/hwpx-plugins) | 에이전트용 플러그인·스킬 번들 |

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

## 무엇을 하나

- **읽기·추출** — 텍스트/HTML/rich Markdown 내보내기(서식·중첩 표·각주 보존), XPath 객체 탐색
- **편집** — 문단·표·이미지·머리글/바닥글·메모·각주, 줄간격·여백·쪽번호 등 서식
- **양식 채우기** — 라벨·경로 기반 셀 채움, 바이트 보존 구조 편집(행·열·오토핏·shrink-to-fit)
- **생성** — 조립형 builder, 공문 lint·결재란, 사진대지·명패·조직도, mail merge, 신구대조표
- **변경추적·목차** — redline 저작, 네이티브 목차·상호참조
- **검증·안전** — XSD·패키지 검증 CLI, 열림 안전 게이트, 모든 쓰기에 영수증(`MutationReport`)

자세한 내용: [사용 가이드](docs/usage.md) · [API 레퍼런스](https://airmang.github.io/python-hwpx/) · [예제](docs/examples.md)

## 신뢰의 근거

- [안전한 쓰기 계약](docs/safe-write-contract.md) — 보존 등급을 쓰기 전에 판정하고, 실제 변경을 측정한 영수증을 반환합니다(fail-closed)
- [지원 매트릭스](docs/support-matrix.md) — 기능별 실제 지원 등급, 안 되는 것도 등급으로 명시
- [실측 코퍼스 메트릭](https://airmang.github.io/python-hwpx/corpus-metrics.html) — 실한컴 전수 측정 수치와 주의사항, 낮은 숫자도 그대로 발행

현재 개발 상태는 Alpha입니다 — API는 바뀔 수 있습니다.

## 비교

| | python-hwpx | pyhwpx | pyhwp |
|---|---|---|---|
| **대상 포맷** | `.hwpx` (OWPML/OPC) | `.hwpx` | `.hwp` (v5 바이너리) |
| **한/글 설치** | 불필요 | 필요 (Windows COM) | 불필요 |
| **크로스 플랫폼** | ✅ Linux / macOS / Windows / CI | ❌ Windows 전용 | ✅ |
| **편집/생성 API** | ✅ | ✅ (COM) | ❌ 대부분 읽기 |
| **AI 에이전트 연동 (MCP)** | ✅ | ❌ | ❌ |

> HWP(v5 바이너리)는 지원하지 않습니다. 한컴오피스에서 HWPX로 변환 후 사용하세요.

## 알려진 제약

- `add_shape()` / `add_control()`은 한/글이 요구하는 모든 하위 요소를 생성하지 않습니다.
- `<hp:pic>` 그림 개체의 완전 자동 생성은 제공하지 않습니다.
- 암호화된 HWPX는 지원하지 않습니다.

## 기여하기

[help wanted](https://github.com/airmang/python-hwpx/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22) ·
[로드맵](https://github.com/airmang/python-hwpx/milestones) ·
[Discussions](https://github.com/airmang/python-hwpx/discussions) ·
[내부 실전 가이드](docs/internals/) ·
[CONTRIBUTING](CONTRIBUTING.md)

## 감사의 말

[OWPML (KS X 6101)](https://www.kssn.net/search/stddetail.do?itemNo=K001010119985) — 기반 표준 ·
[hancom-io/hwpx-owpml-model](https://github.com/hancom-io/hwpx-owpml-model) — 구조 참조 ·
[neolord0/hwpxlib](https://github.com/neolord0/hwpxlib) — 오라클 샘플 ·
[edwardkim/rhwp](https://github.com/edwardkim/rhwp) — 검증 게이트 영감 ·
범정부오피스 — 워크플로 아이디어

## License · Maintainer

Apache-2.0 ([LICENSE](LICENSE) · [NOTICE](NOTICE)) — **Kohkyuhyun** [@airmang](https://github.com/airmang) · [kokyuhyun@hotmail.com](mailto:kokyuhyun@hotmail.com)
