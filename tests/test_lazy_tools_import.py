# SPDX-License-Identifier: Apache-2.0
"""``import hwpx`` does not load ``hwpx.tools``.

The stable names that live in ``hwpx.tools`` (text extraction, object finding,
document diff, mail merge, package validation) resolve on first access, with no
warning and as the same objects their modules define. ``dir(hwpx)`` and
``from hwpx import *`` still list them all.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap


def _run(code: str) -> str:
    result = subprocess.run(
        [sys.executable, "-W", "error", "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


_TOOLS_LOADED = "sorted(k for k in sys.modules if k == 'hwpx.tools' or k.startswith('hwpx.tools.'))"


def test_import_hwpx_loads_no_tools_module() -> None:
    assert _run(f"import sys, hwpx; print({_TOOLS_LOADED})") == "[]"


def test_every_stable_name_resolves_without_a_warning() -> None:
    out = _run(
        """
        import hwpx
        missing = [name for name in hwpx.__all__ if getattr(hwpx, name, None) is None]
        print(len(hwpx.__all__), missing)
        """
    )
    count, missing = out.split(" ", 1)
    assert int(count) > 0
    assert missing == "[]"


def test_star_import_and_dir_list_every_stable_name() -> None:
    out = _run(
        """
        import hwpx
        listed = set(dir(hwpx))
        namespace = {}
        exec("from hwpx import *", namespace)
        print(sorted(set(hwpx.__all__) - listed), sorted(set(hwpx.__all__) - set(namespace)))
        """
    )
    assert out == "[] []"


def test_tools_names_are_the_objects_their_modules_define() -> None:
    out = _run(
        """
        import importlib
        import hwpx
        mismatched = []
        for module_name in (
            "hwpx.tools.text_extractor",
            "hwpx.tools.object_finder",
            "hwpx.tools.doc_diff",
            "hwpx.tools.mail_merge",
            "hwpx.tools.package_validator",
        ):
            module = importlib.import_module(module_name)
            for name in hwpx.__all__:
                if name in vars(module) and getattr(hwpx, name) is not vars(module)[name]:
                    mismatched.append(name)
        print(mismatched)
        """
    )
    assert out == "[]"


def test_tools_subpackage_is_still_reachable_as_an_attribute() -> None:
    out = _run(
        """
        import hwpx
        print(hwpx.tools.validator.validate_document.__name__, hwpx.tools.exporter.export_text.__name__)
        """
    )
    assert out == "validate_document export_text"
