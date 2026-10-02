# SPDX-License-Identifier: Apache-2.0
"""``import hwpx`` does not load the HWP 5.0 package.

Reading and writing ``.hwp`` loads ``hwpx.hwp5`` on first use. The public names
``hwpx.Hwp5Error`` and ``hwpx.Hwp5ConversionWarning`` are the same objects
``hwpx.hwp5.errors`` exports, and catching them needs no HWP 5.0 code.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap


def _run(code: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


_HWP5_LOADED = "sorted(k for k in sys.modules if k == 'hwpx.hwp5' or k.startswith('hwpx.hwp5.'))"


def test_import_hwpx_loads_no_hwp5_module() -> None:
    assert _run(f"import sys, hwpx; print({_HWP5_LOADED})") == "[]"


def test_importing_the_document_class_loads_no_hwp5_module() -> None:
    assert _run(f"import sys; from hwpx import HwpxDocument; print({_HWP5_LOADED})") == "[]"


def test_catching_hwp5_error_needs_no_hwp5_module() -> None:
    out = _run(
        f"""
        import sys
        import hwpx
        try:
            raise hwpx.Hwp5Error("x")
        except hwpx.Hwp5Error as error:
            print(error.code, {_HWP5_LOADED})
        """
    )
    assert out == "hwp5-damaged []"


def test_hwp5_names_keep_their_identity() -> None:
    import hwpx
    from hwpx.hwp5 import errors

    assert hwpx.Hwp5Error is errors.Hwp5Error
    assert hwpx.Hwp5ConversionWarning is errors.Hwp5ConversionWarning
    assert issubclass(hwpx.Hwp5Error, hwpx.HwpxError)


def test_hwp5_loads_when_a_document_is_written_and_opened_as_hwp() -> None:
    out = _run(
        """
        import sys
        import hwpx
        document = hwpx.HwpxDocument.new()
        document.add_paragraph("한글 5.0")
        payload = document.to_bytes(format="hwp")
        loaded_after_save = "hwpx.hwp5.writer" in sys.modules
        reopened = hwpx.HwpxDocument.open(payload)
        print(loaded_after_save, "한글 5.0" in reopened.text.plain())
        """
    )
    assert out == "True True"


def test_opening_a_damaged_compound_file_raises_hwp5_error() -> None:
    out = _run(
        """
        import hwpx
        try:
            hwpx.HwpxDocument.open(b"\\xd0\\xcf\\x11\\xe0\\xa1\\xb1\\x1a\\xe1" + bytes(600))
        except hwpx.Hwp5Error as error:
            print(error.code)
        """
    )
    assert out == "hwp5-damaged"
