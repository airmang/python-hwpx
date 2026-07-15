from __future__ import annotations

from importlib import import_module

import pytest


def test_internal_practice_namespace_is_not_importable() -> None:
    with pytest.raises(ModuleNotFoundError) as exc_info:
        import_module("hwpx.practice")

    assert exc_info.value.name == "hwpx.practice"
