#!/usr/bin/env bash
# 간단한 PyPI 배포 스크립트.
#
# 기본 사용법:
#   ./scripts/build-and-publish.sh            # PyPI 업로드
#   ./scripts/build-and-publish.sh testpypi   # TestPyPI 업로드
#
# 업로드 전에 TWINE_USERNAME/TWINE_PASSWORD 또는 PyPI API 토큰을 환경 변수로 설정하세요.

set -euo pipefail

REPOSITORY=${1:-pypi}
PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "${PROJECT_ROOT}"

python -m pip install --upgrade build twine >/dev/null

rm -rf dist build
python -m build

twine check dist/*

if [[ "${REPOSITORY}" != "pypi" ]]; then
    twine upload --repository "${REPOSITORY}" dist/*
else
    twine upload dist/*
fi
