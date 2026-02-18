"""하위 호환을 위한 패키지 모듈.

신규 코드는 :mod:`hwpx.opc.package` 를 직접 사용하세요.
"""

from __future__ import annotations

import logging
from warnings import warn

from .opc.package import HwpxPackage, HwpxPackageError, HwpxStructureError, RootFile, VersionInfo

__all__ = ["HwpxPackage", "HwpxPackageError", "HwpxStructureError", "RootFile", "VersionInfo"]

logger = logging.getLogger(__name__)

warn(
    "'hwpx.package' 모듈은 더 이상 권장되지 않습니다. 'hwpx.opc.package'를 사용하세요.",
    DeprecationWarning,
    stacklevel=2,
)
logger.warning(
    "'hwpx.package' 모듈은 더 이상 권장되지 않습니다. 'hwpx.opc.package'를 사용하세요."
)
