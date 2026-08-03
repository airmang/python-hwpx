"""docs/error-codes.md 를 hwpx.errors.ERROR_CODES 에서 생성한다."""
import sys, pathlib, collections
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))
from hwpx.errors import ERROR_CODES, ERROR_CODE_DOMAINS, GRANDFATHERED_CODES
from hwpx.quality.report import ERROR_CODES as QUALITY_CODES

by_domain = collections.defaultdict(list)
for code, meaning in ERROR_CODES.items():
    by_domain[code.split("-", 1)[0]].append((code, meaning))

head = f'''# 오류 코드 (`HwpxError.code`)

`python-hwpx` 의 구조화 예외는 사람이 읽는 문장(`message`) 위에 기계가 읽는
세 필드를 얹는다 — `code`, `context`, `suggestion`. 호출자는 **`code` 로
분기**하면 되고, 그 문자열은 계약이라 **major 경계에서만** 바뀐다.

```python
from hwpx import HwpxDocument
from hwpx.errors import HwpxError

document = HwpxDocument.new()
try:
    document.add_paragraph("본문", style="개요1")
except HwpxError as exc:
    if exc.code == "style-not-found":
        print(exc.context["closest"])   # ['개요 1', '개요 10']
        print(exc.suggestion)           # 가장 가까운 이름: '개요 1' ...
```

5.x 코드는 그대로 돌아간다. typed 예외는 자기가 대체한 builtin 을 함께
상속하므로 `except ValueError` 가 여전히 잡는다.

## 두 어휘는 통합하지 않는다

이 문서의 코드는 **kebab-case** 이고 `HwpxError.code` 에만 쓰인다.
`hwpx.quality.report` 에는 **SCREAMING_SNAKE** 코드가 따로 있다.

| | `HwpxError.code` | `QualityError.code` |
|---|---|---|
| 형태 | `style-not-found` | `VISUAL_COMPLETE_FAILED` |
| 쓰임 | 예외 분기 | **발행된 영수증 스키마의 필드값** |
| 관리 | major 경계 | 영수증 스키마 버전 |
| 개수 | {len(ERROR_CODES)} | {len(QUALITY_CODES)} |

통합하지 않는 이유: quality 코드는 `hwpx.mutation-report/v1` 과
`VisualCompleteReport` 에 이미 실려 나간 값이다. 이름을 바꾸면 영수증을 읽는
쪽이 깨지고, 그건 이 라인이 막 복구한 영수증 무결성을 다시 흔드는 일이다.

**둘이 만나는 곳은 한 군데뿐이다** — 품질 게이트가 저장을 막으면
`hwpx._document.persistence` 가 그것을 `quality-gate-failed` 로 감싸고,
원래의 SCREAMING_SNAKE 코드는 `context` 에 담아 보낸다.

## 형식

`<도메인>-<조건>`, 전부 소문자 kebab-case. 도메인은 6.0 네임스페이스와
패키지 수준 관심사에서 온다:

`{"`, `".join(sorted(ERROR_CODE_DOMAINS))}`

유예 {len(GRANDFATHERED_CODES)}건 — {", ".join(f"`{c}`" for c in sorted(GRANDFATHERED_CODES))} —
은 5.6.0 에 이미 나간 이름이라 문법에 맞지 않아도 바꾸지 않는다(7.0 정리).

## 전체 목록

이 표는 `hwpx.errors.ERROR_CODES` 에서 **생성**된다. 레지스트리가 정본이고
문서가 사본이다 — 문서끼리 대조하는 가드는 "양쪽에 다 없으면 통과"하므로,
문서를 코드에서 유도하는 쪽이 옳다.
'''
lines = [head]
for domain in sorted(by_domain):
    lines.append(f"\n### `{domain}-*`\n")
    lines.append("| 코드 | 뜻 |")
    lines.append("|---|---|")
    for code, meaning in sorted(by_domain[domain]):
        lines.append(f"| `{code}` | {meaning} |")
(ROOT / 'docs/error-codes.md').write_text("\n".join(lines) + "\n", encoding='utf-8')
print(f"docs/error-codes.md: {len(ERROR_CODES)} codes / {len(by_domain)} domain groups")
