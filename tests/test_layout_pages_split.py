# SPDX-License-Identifier: Apache-2.0
"""The page estimate is one model in two files, reached through ``hwpx.layout.pages`` as before.

``layout/pages.py`` passed the size a plugin directory reads of one file, so its lower half lives in
``layout/_page_measure.py`` (see ``tests/test_distribution_file_sizes.py``). The split moves text only.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

from hwpx.layout import _page_measure, pages


def _defined(module: object) -> list[str]:
    """The names *module*'s source defines at its top level (not the ones it imports)."""

    names = []
    for node in ast.parse(Path(module.__file__).read_text(encoding="utf-8")).body:  # type: ignore[attr-defined]
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            names.extend(target.id for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
    return names


def test_pages_holds_every_name_the_lower_half_defines() -> None:
    lower = _defined(_page_measure)
    assert len(lower) > 100
    missing = [name for name in lower if getattr(pages, name, None) is not getattr(_page_measure, name)]
    assert missing == [], f"add to the import from ._page_measure in layout/pages.py: {missing}"
    assert not set(lower) & set(_defined(pages)), "a name is defined in both halves"


def test_pages_keeps_the_names_it_imported_before_the_split() -> None:
    # Tests and callers reach these as hwpx.layout.pages.<name> (text_style_from_refs, for one).
    before = ("Any", "COLUMN_SHARES", "Collection", "HH", "HP", "HwpxOxmlHeader", "_DEFAULT_TAB_STOP",
              "_GLYPH_SPACE", "_TYPED_NO_BREAK_SPACE", "_drawn_page_size", "_page_margin",
              "_remove_short_paragraph_layout_cache", "_remove_stale_paragraph_layout_cache", "cell_margins_of",
              "char_advance", "copy", "dataclass", "etree", "field", "font_line_height", "grid_widths_of",
              "hancom_line_starts", "in_char_units", "indented_widths", "margins_doubled", "math", "os",
              "paragraph_heading", "paragraph_label", "replace", "text_style_from_refs")
    assert [name for name in before if not hasattr(pages, name)] == []


def test_the_public_names_stay_in_pages() -> None:
    assert pages.__all__ == ["EstimatedLine", "PageEstimate", "estimate_pages"]
    assert {getattr(pages, name).__module__ for name in pages.__all__} == {"hwpx.layout.pages"}
    import hwpx
    from hwpx import experimental

    assert experimental.estimate_pages is pages.estimate_pages
    assert hwpx.PageEstimate is pages.PageEstimate and hwpx.EstimatedLine is pages.EstimatedLine


def test_the_lower_half_does_not_refer_to_pages() -> None:
    code = ("import sys; import hwpx.layout._page_measure; "
            "assert 'hwpx.layout.pages' not in sys.modules, 'the lower half imports pages'")
    subprocess.run([sys.executable, "-c", code], check=True)
