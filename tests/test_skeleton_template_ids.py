from __future__ import annotations

import re
import zipfile
from importlib.resources import files


def test_skeleton_template_ids_fit_in_signed_int32() -> None:
    """The bundled HWPX skeleton (`hwpx/data/Skeleton.hwpx`) is the seed
    used by ``HwpxDocument.new()``. Every numeric ``id`` inside it must
    fit in signed int32 so consumers that parse ids as ``int`` see a
    non-negative value."""

    skeleton = files("hwpx.data") / "Skeleton.hwpx"
    with zipfile.ZipFile(skeleton.open("rb")) as zf:
        for name in zf.namelist():
            if not name.endswith(".xml"):
                continue
            data = zf.read(name).decode("utf-8")
            for match in re.finditer(r'\sid="(-?\d+)"', data):
                value = int(match.group(1))
                assert 0 <= value < 2**31, (
                    f"{name} contains id={value} (0x{value:x}); "
                    "Skeleton.hwpx values must stay in [0, 2^31)"
                )
