"""하위 호환을 위한 패키지 모듈.

신규 코드는 :mod:`hwpx.opc.package` 를 직접 사용하세요.
"""

from __future__ import annotations

import logging
import sys
from warnings import warn

from .opc.package import HwpxPackage, HwpxPackageError, HwpxStructureError, RootFile, VersionInfo

__all__ = ["HwpxPackage", "HwpxPackageError", "HwpxStructureError", "RootFile", "VersionInfo"]

logger = logging.getLogger(__name__)

# hwpx.__init__에서의 내부 import와 사용자의 직접 import를 구분합니다.
# 'hwpx' 패키지 초기화 중이 아닌 경우에만 경고를 표시합니다.
_parent = sys.modules.get("hwpx")
if _parent is not None and hasattr(_parent, "__all__"):
    # 이미 hwpx 패키지 초기화가 완료된 후 별도로 import한 경우
    warn(
        "'hwpx.package' 모듈은 더 이상 권장되지 않습니다. 'hwpx.opc.package'를 사용하세요.",
        DeprecationWarning,
        stacklevel=2,
    )
    logger.warning(
        "'hwpx.package' 모듈은 더 이상 권장되지 않습니다. 'hwpx.opc.package'를 사용하세요."
    )
