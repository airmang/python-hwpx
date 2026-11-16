# 기여 안내

**python-hwpx** 개선에 관심 가져주셔서 감사합니다! 이 문서는 현재 개발 및 테스트
흐름을 간단히 설명하여 새로운 기여자가 빠르게 생산성을 낼 수 있도록 돕습니다.
코드베이스가 성장함에 따라 절차는 변경될 수 있으니, 더 나은 방식이 발견되면
주저 말고 이 문서를 확장하거나 수정해 주세요.

## 개발 워크플로우

1. **저장소를 포크하고 클론**한 뒤, 변경 범위를 반영한 기능 브랜치를 만드세요.
2. **가상 환경을 설정**합니다 (Python 3.11 이상 권장) 그리고 활성화하세요:
  ```bash
  python -m venv .venv
  source .venv/bin/activate  # Windows에서는: .venv\Scripts\activate
  python -m pip install --upgrade pip
  ```
3. **개발 도구를 설치**합니다. 배포 메타데이터가 `pyproject.toml`에 정의되어 있어
  편집 가능한 설치로 개발 의존성을 한 번에 구성할 수 있습니다:
  ```bash
  python -m pip install -e ".[dev]"
  ```
  `dev`에는 CI가 설치하는 `test`·`typecheck`(pytest, ruff, mypy, pyright, 테스트가
  쓰는 pillow·pyyaml·latex2mathml 등)와 배포 점검용 twine이 들어 있습니다. CI와 똑같이
  맞추려면 `python -m pip install -e ".[test,typecheck]"`를 써도 됩니다.
4. **임포트 확인**. `pip install -e`를 실행하면 `hwpx` 패키지가 가상 환경에
  설치되어 추가적인 `PYTHONPATH` 설정이 필요 없습니다. 인터프리터에서
  `import hwpx`가 정상적으로 동작하는지 확인하세요.

5. **공개 저장소 게이트를 실행**합니다:
  ```bash
  python scripts/check_public_hygiene.py
  ruff check --select E9,F .
  pytest -q
  ```

실제 문서나 고객·학교·기관에서 유래한 파일, 개인정보, 로컬 절대 경로, 내부
작업 기록은 커밋하지 마세요. 회귀 fixture는 재현 가능한 합성 데이터로 만들고
출처·기대 동작을 가까운 README나 테스트에 기록해 주세요.


## 풀 리퀘스트 체크리스트

- 동작이 변경되거나 새 모듈이 추가될 때는 문서(이 파일 포함)를 업데이트하세요.
- 리뷰를 쉽게 하기 위해 PR 설명에 관련 DevDoc 섹션 및 외부 명세를 참조하세요.
- 커밋은 집중적이고 설명적으로 유지하세요; 가능한 경우 관련 이슈 번호를 적어주세요.
- 풀 리퀘스트를 열기 전에 작업 트리가 깨끗한지(`git status`) 확인하세요.

오타 수정부터 새 파서 추가까지 모든 기여를 환영합니다. HWPX 생태계를 위한
더 나은 도구를 함께 만들어 주셔서 감사합니다!

## 공개 표면 잠금

공개 이름(최상위 `hwpx.__all__`, `HwpxDocument`, 묶음 `doc.styles`·`doc.tables` …, `hwpx.model`의
계약 멤버, `hwpx.objects` 값 형식, 모듈 경로로 가져오는 stable 이름)은 `tests/data/public_surface.json`
한 파일이 잠급니다. `tests/test_public_surface.py`는 설치본이 잠금과 하나라도 다르면(늘어도 줄어도)
실패하고, 무엇이 어떻게 다른지와 고치는 명령을 알려 줍니다.

- 이름·인자·반환을 바꿨으면 잠금을 손으로 고치지 말고 다시 만드세요. 바뀐 것마다
  `tests/data/public_surface_changes.jsonl`에 까닭과 함께 한 줄이 남고, `docs/stable-api.md`의 잠금 표도
  함께 다시 씁니다. 세 파일을 함께 커밋하세요.
  ```bash
  python scripts/public_surface_lock.py check --update --reason "<무엇을 왜>"
  ```
- 지우기·이름 바꾸기·서명 바꾸기(깨지는 변경)는 패키지 메이저가 잠금의 `major`보다 클 때만 받습니다.
  다음 메이저를 만드는 동안(예: 7.0을 만드는 6.x)에는 `--allow-major-break`를 붙입니다. 잠금의 `major`가
  패키지 메이저 + 1이 되고, 그 메이저가 나올 때까지 깨지는 변경마다 이 표시를 다시 요구합니다.
- `hwpx.model` 계약 멤버의 이름을 바꾸면 새 이름은 계약 밖(`internal`)으로 잡힙니다.
  `--contract 클래스.새이름`으로 계약에 올리세요(`클래스.*`는 그 클래스의 공개 이름 전부). 계약에서
  내리려면 `--internal 클래스.이름`입니다(깨지는 변경).
- 모듈 경로로 가져오는 stable 이름을 더하거나 빼려면 `scripts/public_surface_lock.py`의 `MODULE_NAMES`와
  `docs/stable-api.md`를 함께 고친 뒤 다시 만듭니다.
- **병합 충돌이 나면 손으로 합치지 않습니다.** 병합 직후에(충돌 상태 그대로든, 저절로 커밋된 뒤든)
  다시 만드세요.
  ```bash
  python scripts/public_surface_lock.py rebuild
  git add tests/data/public_surface.json docs/stable-api.md tests/data/public_surface_changes.jsonl
  ```
  `rebuild`는 두 쪽의 계약 분류를 세 갈래로 합쳐(두 쪽이 다 남긴 것 + 어느 쪽이든 새로 올린 것)
  병합된 코드에서 잠금을 다시 만들고, `docs/stable-api.md` 잠금 표 안의 충돌도 다시 씁니다. 장부는
  `.gitattributes`의 `merge=union`으로 두 쪽 줄이 모두 남습니다. 두 쪽이 각자 장부에 적은 변경은 그대로
  받고, 어느 쪽 잠금에도 적히지 않은 변경(잠금을 다시 만들지 않은 가지)이 있으면 종료 코드 1로 멈춥니다.
  그 변경을 받으려면 `--reason "<가지>: <무엇을 왜>"`(깨지는 변경이면 `--allow-major-break`도)를 붙입니다.
  이 잠금보다 먼저 갈라진 가지는 옛 `tests/data/model_surface.json`에서 계약에 올리고 내린 것을 옮겨
  옵니다(그 파일의 고침/지움 충돌은 `git rm`으로 풉니다). 잠금 표 밖의 문서 충돌은 풀지 않고 1로 알립니다.

## 유지보수자를 위한 릴리스 절차

태그를 찍고 발행하는 절차, 태그 전 로컬 게이트 전수 목록, 그리고 **작업
브랜치를 시작하거나 릴리스를 준비할 때 가장 먼저 할 일(`origin/main` 대조)**은
[`docs/release-runbook.md`](docs/release-runbook.md)에 있습니다. 장수
브랜치가 origin과 갈라진 채 오래 살면 그 사이 독립적으로 나간 변경(예:
보안 패치)을 태그 직전까지 모르고 지나칠 수 있으므로, 사이클을 시작할 때도
같은 대조를 먼저 하세요.

## 기여자 명단

머지된 PR이나 반영된 이슈 제보로 기여해 주신 분들은 [`CONTRIBUTORS.md`](CONTRIBUTORS.md)에
릴리즈 단위로 등재됩니다. 릴리즈 노트와 `CONTRIBUTORS.md` 모두에서 이름을 확인하실 수 있습니다.

## 타입 힌트 및 `from __future__ import annotations` 정책

- 이 저장소는 Python 3.10을 최소 지원 버전으로 유지하므로, 타입 힌트는 `list`/`dict`/`tuple` 같은 **내장 제네릭(PEP 585)** 을 우선 사용합니다.
- 신규 파일에서 타입 힌트에 전방 참조(아직 정의되지 않은 클래스 이름)나 `|` 유니온 표기를 사용한다면 `from __future__ import annotations`를 파일 상단에 추가하세요.
- 기존 파일을 수정할 때도 같은 기준을 적용해 파일 단위로 일관성을 맞춥니다. 즉, 해당 파일이 미래 지연 평가가 필요하면 유지하고, 필요하지 않으면 제거합니다.
- 점진 변환 범위(현재: `src/hwpx/document.py`, `src/hwpx/oxml/document.py`)는 CI에서 다음 항목으로 검증합니다.
  - `scripts/check_typing_generics_scope.py`: `List`/`Dict`/`Tuple` 별칭 사용 금지 확인
  - `mypy`, `pyright`: 지정된 파일 범위 타입 검사

## 배포 파일 크기

Claude 플러그인은 릴리스한 wheel을 풀어서 싣고, 플러그인 디렉터리는 파일 하나에서 256 KiB까지만 읽습니다
(hwpx-plugins `scripts/vendor_claude_engine.py`의 `MAX_FILE_BYTES`). 묶음 전체는 512개 파일까지입니다.

- `tests/test_distribution_file_sizes.py`는 `src/hwpx`와 빌드한 wheel의 파일이 256 KiB에 닿으면 실패하고,
  80%(약 205 KiB)를 넘으면 경고합니다. 경고가 뜨면 한도에 닿기 전에 나누세요. 파일 수 한도가 있으므로 여러
  모듈보다 새 모듈 하나로 나누는 편이 낫습니다.
- FormFit 글리프 표는 `scripts/glyph_table_source.py`(읽을 수 있는 Python, 배포하지 않음)에서 고칩니다. 고친 뒤
  `python scripts/build_glyph_table.py`를 돌려 `src/hwpx/form_fit/_glyph_table.json.gz`를 다시 만들고 둘을 함께
  커밋하세요. `tests/test_glyph_table_data.py`가 두 파일의 표를 값 하나하나 비교합니다.
- 쪽 수 추정은 `layout/pages.py`(공개 이름, 쪽·단 흐름)와 `layout/_page_measure.py`(상수, 문단·표 모델)로 나뉘어
  있습니다. `_page_measure.py`는 `pages.py`를 참조하지 않고, 거기에 새로 정의한 이름은 `pages.py`의 import
  목록에도 넣습니다(`tests/test_layout_pages_split.py`).
