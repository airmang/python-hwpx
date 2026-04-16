# HWPX Stack Compatibility Checklist

`python-hwpx`, `hwpx-mcp-server`, `hwpx-skill`을 묶어서 변경하거나 릴리스할 때 쓰는 공통 체크리스트다.

## 1. 변경 분류

먼저 바뀐 것이 무엇인지 분류한다.

- [ ] 코어 API (`python-hwpx`) 변경
- [ ] 코어 저장/파싱/round-trip 동작 변경
- [ ] CLI 동작 변경
- [ ] MCP 도구 이름/인자/응답 스키마 변경
- [ ] Skill 설치/트리거/스크립트 변경
- [ ] README, 예제, 레퍼런스 문서 변경만 있음

## 2. python-hwpx 체크

- [ ] `pyproject.toml` 버전과 의존성이 의도와 맞다
- [ ] 새 기능 또는 회귀에 대응하는 테스트가 있다
- [ ] 저장 후 재열기(round-trip) 검증이 필요하면 수행했다
- [ ] 샘플 `.hwpx`에서 파싱/편집/저장이 실제로 된다
- [ ] 공개 API 이름이나 인자 변경이 있으면 문서에 반영했다
- [ ] CLI 출력/인자 변경이 있으면 하위 레이어 영향 검토를 했다

권장 명령:
```bash
cd /path/to/python-hwpx
python -m pip install -e ".[test]"
python -m pytest -q
```

## 3. hwpx-mcp-server 체크

- [ ] `python-hwpx` 최소 지원 버전 문구가 최신 상태다
- [ ] 최신 검증 코어 버전 문구가 최신 상태다
- [ ] MCP 도구 스키마/파라미터 설명이 실제 구현과 맞다
- [ ] 주요 읽기/검색/편집 도구가 동작한다
- [ ] 고급 모드(`HWPX_MCP_ADVANCED=1`) 영향이 있으면 별도 확인했다
- [ ] README, `docs/use-cases.md`, `docs/upstream-audit.md`, CHANGELOG 반영이 필요하면 했다

권장 명령:
```bash
cd /path/to/hwpx-mcp-server
python -m pip install -e ".[test]"
python -m pytest -q
```

## 4. hwpx-skill 체크

- [ ] 설치 가이드가 현재 코어 버전/스크립트 흐름과 맞다
- [ ] `SKILL.md`의 트리거 설명이 여전히 적절하다
- [ ] 예제 스크립트가 현재 코어에서 실제로 돈다
- [ ] 텍스트 추출 스크립트가 동작한다
- [ ] 플레이스홀더 치환 + namespace 정리 흐름이 동작한다
- [ ] README와 examples 설명이 실제 결과와 맞다

권장 명령:
```bash
cd /path/to/hwpx-skill
python -m pip install -U python-hwpx lxml
python examples/01_create_and_save.py
python examples/02_extract_and_inspect.py examples/out/01_created.hwpx
python scripts/text_extract.py <sample.hwpx>
python examples/03_template_replace.py <input.hwpx> <output.hwpx> --replace '{키}=값'
```

## 5. 스택 통합 체크

하나의 변경이 세 레이어를 관통하는 경우 반드시 본다.

- [ ] 코어 변경이 MCP 도구 표면에 영향을 주는지 확인했다
- [ ] 코어 변경이 Skill 스크립트/예제에 영향을 주는지 확인했다
- [ ] 최소 지원 버전과 최신 검증 버전을 분리해 설명했다
- [ ] 동일 샘플 문서 기준으로 코어, MCP, Skill 경로를 최소 1회는 확인했다
- [ ] 사용자 관점의 대표 시나리오 하나 이상을 다시 점검했다
  - 예: 문서 읽기
  - 예: 표 셀 채우기
  - 예: 플레이스홀더 치환
  - 예: Markdown/HTML 추출

## 6. 릴리스 전 문서 체크

- [ ] 세 레포 README가 서로 모순되지 않는다
- [ ] 버전 표기와 검증 버전이 최신이다
- [ ] 설치 명령이 현재 배포 방식과 맞다
- [ ] 변경점이 CHANGELOG 또는 릴리스 노트에 정리됐다
- [ ] 알려진 제한 사항이 있으면 숨기지 않고 적었다

## 7. 최종 판단

아래 질문에 모두 예라고 답할 수 있어야 한다.

- [ ] 이 변경은 코어 단독 변경이 아니라 스택 관점에서도 설명 가능한가?
- [ ] 실제 사용자가 바로 밟는 경로가 깨지지 않았는가?
- [ ] 문서가 코드보다 뒤처지지 않았는가?
- [ ] 다음 레이어가 우회 코드로 버티고 있지 않은가?

한 줄 원칙:

**코어가 바뀌면 MCP와 Skill까지 같이 본다. 문서도 릴리스 산출물이다.**
