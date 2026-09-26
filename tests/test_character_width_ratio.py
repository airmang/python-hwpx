# SPDX-License-Identifier: Apache-2.0
"""A character width ratio (장평) above 255 is refused: Hancom keeps it in one byte.

Hancom stores and draws ratios up to 255 as given; 256 and up come out as ``ratio - 256``,
so 300 % would be drawn at 44 %.
"""
from __future__ import annotations

import io
import re
import zipfile

import pytest

from hwpx.document import HwpxDocument


@pytest.mark.parametrize("ratio", [256, 300, 400])
def test_a_ratio_hancom_cannot_keep_is_refused(ratio: int) -> None:
    document = HwpxDocument.new()
    with pytest.raises(ValueError, match="between 10 and 255"):
        document.styles.ensure_run(ratio=ratio)


@pytest.mark.parametrize("ratio", [10, 200, 255])
def test_a_ratio_hancom_keeps_is_written(ratio: int) -> None:
    document = HwpxDocument.new()
    char_pr_id = document.styles.ensure_run(ratio=ratio)

    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        header = archive.read("Contents/header.xml").decode("utf-8")
    char_pr = re.search(rf'<hh:charPr [^>]*\bid="{char_pr_id}"[^>]*>.*?</hh:charPr>', header, re.S)

    assert char_pr is not None
    assert f'<hh:ratio hangul="{ratio}"' in char_pr.group(0)
