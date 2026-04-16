# HWPX Stack Validation Report (2026-04-15)

검증 목적:
- `python-hwpx 2.9.0` 기준으로 `hwpx-mcp-server`, `hwpx-skill`이 현재 로컬에서 실제로 동작하는지 확인

검증 환경:
- venv: `shared/hwpx/.venv-compat311`
- Python: `3.11.15`
- install 방식: local editable install

## 1. 설치

실행:
```bash
uv venv shared/hwpx/.venv-compat311 --python python3.11
source shared/hwpx/.venv-compat311/bin/activate
uv pip install -e . -e '../hwpx-mcp-server[test]'
```

결과:
- `python-hwpx==2.9.0` 설치 성공
- `hwpx-mcp-server==2.2.5` 설치 성공

## 2. hwpx-mcp-server 회귀 검증

실행:
```bash
cd ../hwpx-mcp-server
pytest -q
```

결과:
- 전체 테스트 통과
- 출력 요약: `........................................................................ [ 55%]` / `.......................................................... [100%]`

판단:
- `python-hwpx 2.9.0` 기준으로 현재 `hwpx-mcp-server 2.2.5`는 로컬 회귀 테스트를 통과했다.

## 3. hwpx-skill 스모크 테스트

### 3-1. 문서 생성
```bash
shared/hwpx/.venv-compat311/bin/python ../hwpx-skill/examples/01_create_and_save.py
```
결과:
- `examples/out/01_created.hwpx` 생성 성공

### 3-2. 생성 문서 추출/점검
```bash
shared/hwpx/.venv-compat311/bin/python ../hwpx-skill/examples/02_extract_and_inspect.py ../hwpx-skill/examples/out/01_created.hwpx
```
결과:
- 텍스트 추출 성공
- 표 개수 `1`

### 3-3. 외부 샘플 문서 추출
```bash
shared/hwpx/.venv-compat311/bin/python ../hwpx-skill/scripts/text_extract.py ../hwpx-mcp-server/tests/sample.hwpx
```
결과:
- 샘플 문서 텍스트 추출 성공

### 3-4. 치환 + namespace 정리
```bash
shared/hwpx/.venv-compat311/bin/python ../hwpx-skill/examples/03_template_replace.py ../hwpx-skill/examples/out/01_created.hwpx ../hwpx-skill/examples/out/03_replaced.hwpx --replace '학부모님께 안내드립니다.=학부모님께 수정 안내드립니다.'
```
결과:
- 출력 파일 생성 성공
- replacements: `1`
- namespace 정리 성공

### 3-5. 치환 결과 재검증
```bash
shared/hwpx/.venv-compat311/bin/python ../hwpx-skill/examples/02_extract_and_inspect.py ../hwpx-skill/examples/out/03_replaced.hwpx
```
결과:
- 치환된 문구 확인
- 표 개수 `1`

판단:
- `python-hwpx 2.9.0` 기준으로 현재 `hwpx-skill`의 핵심 예제/스크립트 흐름은 로컬에서 정상 동작했다.

## 4. 바로 도출되는 결론

1. `hwpx-mcp-server`의 README에 있는 `python-hwpx 2.7.1` 검증 문구는 업데이트 후보다.
2. 최소 지원 버전 `>=2.6`과 최신 검증 버전 `2.9.0`을 분리해 문서화하는 편이 낫다.
3. `hwpx-skill`도 최신 코어 기준 smoke path가 확인됐으므로, 이 결과를 설치/운영 문서에 반영할 가치가 있다.

한 줄 결론:

**`python-hwpx 2.9.0` 기준으로 `hwpx-mcp-server`와 `hwpx-skill`의 로컬 호환성은 현재 통과 상태다.**
