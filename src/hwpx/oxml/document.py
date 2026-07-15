# SPDX-License-Identifier: Apache-2.0
"""Compatibility facade for HWPX OpenXML document wrappers.

The implementation lives in :mod:`hwpx.oxml._document_impl`; element-focused
modules such as :mod:`hwpx.oxml.table` and :mod:`hwpx.oxml.section` re-export
the same classes for narrower imports.
"""

from __future__ import annotations

import sys
from types import ModuleType

from . import _document_impl as _impl
from ._document_impl import *  # noqa: F401,F403

__all__ = [name for name in dir(_impl) if not name.startswith("_")]


class _DocumentFacade(ModuleType):
    def __getattr__(self, name: str):
        return getattr(_impl, name)

    def __setattr__(self, name: str, value):
        if not name.startswith("__"):
            setattr(_impl, name, value)
        super().__setattr__(name, value)

    def __delattr__(self, name: str):
        if not name.startswith("__") and hasattr(_impl, name):
            delattr(_impl, name)
        super().__delattr__(name)


def __getattr__(name: str):
    return getattr(_impl, name)


sys.modules[__name__].__class__ = _DocumentFacade
