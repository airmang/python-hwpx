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
  python -m pip install -e .[dev]
  ```
4. **임포트 확인**. `pip install -e`를 실행하면 `hwpx` 패키지가 가상 환경에
  설치되어 추가적인 `PYTHONPATH` 설정이 필요 없습니다. 인터프리터에서
  `import hwpx`가 정상적으로 동작하는지 확인하세요.


## 풀 리퀘스트 체크리스트

- 동작이 변경되거나 새 모듈이 추가될 때는 문서(이 파일 포함)를 업데이트하세요.
- 리뷰를 쉽게 하기 위해 PR 설명에 관련 DevDoc 섹션 및 외부 명세를 참조하세요.
- 커밋은 집중적이고 설명적으로 유지하세요; 가능한 경우 관련 이슈 번호를 적어주세요.
- 풀 리퀘스트를 열기 전에 작업 트리가 깨끗한지(`git status`) 확인하세요.

오타 수정부터 새 파서 추가까지 모든 기여를 환영합니다. HWPX 생태계를 위한
더 나은 도구를 함께 만들어 주셔서 감사합니다!

## 타입 힌트 및 `from __future__ import annotations` 정책

- 이 저장소는 Python 3.10을 최소 지원 버전으로 유지하므로, 타입 힌트는 `list`/`dict`/`tuple` 같은 **내장 제네릭(PEP 585)** 을 우선 사용합니다.
- 신규 파일에서 타입 힌트에 전방 참조(아직 정의되지 않은 클래스 이름)나 `|` 유니온 표기를 사용한다면 `from __future__ import annotations`를 파일 상단에 추가하세요.
- 기존 파일을 수정할 때도 같은 기준을 적용해 파일 단위로 일관성을 맞춥니다. 즉, 해당 파일이 미래 지연 평가가 필요하면 유지하고, 필요하지 않으면 제거합니다.
- 점진 변환 범위(현재: `src/hwpx/document.py`, `src/hwpx/oxml/document.py`)는 CI에서 다음 항목으로 검증합니다.
  - `scripts/check_typing_generics_scope.py`: `List`/`Dict`/`Tuple` 별칭 사용 금지 확인
  - `mypy`, `pyright`: 지정된 파일 범위 타입 검사

