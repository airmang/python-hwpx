# SPDX-License-Identifier: Apache-2.0
"""Cold-process import costs and compatibility of the tools package."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


def _run(code: str) -> None:
    src = str(Path(__file__).resolve().parents[1] / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-W",
            "error",
            "-c",
            f"import sys; sys.path.insert(0, {src!r})\n" + textwrap.dedent(code),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_tools_package_alone_loads_no_submodule() -> None:
    _run("""
        import hwpx.tools
        assert not any(n.startswith('hwpx.tools.') for n in sys.modules)
        assert set(hwpx.tools.__all__) <= set(dir(hwpx.tools))
        assert not any(n.startswith('hwpx.tools.') for n in sys.modules)
    """)


def test_first_save_loads_only_validators_and_still_reopens() -> None:
    _run("""
        import hwpx
        doc = hwpx.HwpxDocument.new()
        doc.add_paragraph('First save still validates and round-trips.')
        data = doc.to_bytes()
        assert sorted(n for n in sys.modules if n.startswith('hwpx.tools.')) == [
            'hwpx.tools.package_validator', 'hwpx.tools.validator'
        ]
        reopened = hwpx.HwpxDocument.open(data)
        assert any(p.text == 'First save still validates and round-trips.'
                   for p in reopened.paragraphs)
    """)


def test_plain_import_defers_metadata_but_version_lookup_still_works() -> None:
    _run("""
        import hwpx
        from hwpx.ingest.hwpx_converter import _python_hwpx_version
        assert 'importlib.metadata' not in sys.modules
        actual = _python_hwpx_version()
        from importlib.metadata import PackageNotFoundError, version
        try:
            expected = version('python-hwpx')
        except PackageNotFoundError:
            expected = '0+unknown'
        assert actual == expected
        assert hwpx.__version__ == expected
    """)


def test_tool_export_only_loads_its_owner() -> None:
    _run("""
        import hwpx
        from hwpx.tools import TextExtractor
        from hwpx.tools.text_extractor import TextExtractor as direct
        assert TextExtractor is direct is hwpx.TextExtractor
        assert sorted(n for n in sys.modules if n.startswith('hwpx.tools.')) == [
            'hwpx.tools.text_extractor'
        ]
    """)


def test_missing_distribution_keeps_unknown_version_fallback() -> None:
    _run("""
        from unittest.mock import patch
        from importlib.metadata import PackageNotFoundError
        from hwpx.ingest.hwpx_converter import _python_hwpx_version
        with patch('importlib.metadata.version', side_effect=PackageNotFoundError):
            assert _python_hwpx_version() == '0+unknown'
    """)


def test_all_exports_star_import_and_unknown_attribute() -> None:
    _run("""
        import hwpx.tools as tools
        names = list(tools.__all__)
        namespace = {}
        exec('from hwpx.tools import *', namespace)
        assert set(names) <= set(namespace) & set(dir(tools))
        for name in names:
            value = getattr(tools, name)
            assert value is namespace[name]
            assert vars(tools)[name] is value
        assert not hasattr(tools, 'not_a_public_tool')
    """)


@pytest.mark.parametrize(
    "first",
    [
        "from hwpx.tools import doc_diff",
        "from hwpx.tools.doc_diff import diff_paragraphs",
        "from hwpx.tools import diff_paragraphs",
        "from hwpx.tools import DOC_DIFF_REPORT_VERSION",
    ],
)
def test_doc_diff_function_survives_submodule_import_order(first: str) -> None:
    _run(
        first
        + "\n"
        + """
import hwpx
from hwpx.tools import doc_diff as package_export
from hwpx.tools.doc_diff import doc_diff as direct
assert callable(package_export)
assert package_export is direct is hwpx.doc_diff
"""
    )


def test_existing_submodule_attribute_access() -> None:
    _run("""
        import hwpx
        assert hwpx.tools.validator.validate_document.__name__ == 'validate_document'
        assert 'hwpx.tools.exporter' not in sys.modules
        assert hwpx.tools.exporter.export_text.__name__ == 'export_text'
        assert 'hwpx.tools.document_viewer' not in sys.modules
    """)


def test_other_diff_exports_still_resolve_when_function_is_replaced() -> None:
    _run("""
        import importlib
        module = importlib.import_module('hwpx.tools.doc_diff')
        module.doc_diff = lambda *args: {}
        from hwpx.tools import diff_paragraphs
        assert diff_paragraphs is module.diff_paragraphs
    """)
