from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

project = "python-hwpx"
author = "python-hwpx Maintainers"
current_year = datetime.now().year
copyright = f"{current_year}, {author}"


def _read_version() -> str:
    try:
        from importlib.metadata import version  # type: ignore

        return version("python-hwpx")
    except Exception:
        pyproject = ROOT / "pyproject.toml"
        if pyproject.exists():
            try:
                import tomllib
            except ModuleNotFoundError:  # pragma: no cover
                import tomli as tomllib  # type: ignore
            data = tomllib.loads(pyproject.read_text())
            project_data = data.get("project", {})
            version_value = project_data.get("version")
            if version_value:
                return str(version_value)
        try:
            from hwpx import __version__

            return __version__
        except Exception:
            return "0.0.0"


release = _read_version()
version = release

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
exclude_patterns: list[str] = ["_build", "Thumbs.db", ".DS_Store"]

language = "ko"

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
# llms.txt(llmstxt.org 관례)는 사이트 루트에 verbatim으로 놓인다.
html_extra_path = ["_extra"]
html_theme_options = {
    "collapse_navigation": False,
    "navigation_depth": 2,
    "style_external_links": True,
}

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

autosummary_generate = True
autodoc_member_order = "bysource"
autodoc_typehints = "description"

myst_enable_extensions = [
    "colon_fence",
    "deflist",
]
myst_heading_anchors = 3

nitpicky = False


def _write_llms_full(app, exception):
    """빌드 산출물 루트에 llms-full.txt를 생성한다.

    llms.txt와 ledger-게이트 매뉴얼(퀵스타트·레시피·의미론·지원 매트릭스)을
    이어붙인다 — 저장소에 사본을 두지 않으므로 드리프트가 없다.
    """
    if exception is not None or app.builder.name != "html":
        return
    from pathlib import Path

    docs = Path(__file__).parent
    sources = [
        docs / "_extra" / "llms.txt",
        docs / "quickstart.md",
        docs / "recipes-traversal.md",
        docs / "mutation-semantics.md",
        docs / "support-matrix.md",
    ]
    parts = []
    for source in sources:
        parts.append(f"\n\n<!-- ===== {source.name} ===== -->\n\n")
        parts.append(source.read_text(encoding="utf-8"))
    out = Path(app.outdir) / "llms-full.txt"
    out.write_text("".join(parts).lstrip(), encoding="utf-8")


def setup(app):
    app.connect("build-finished", _write_llms_full)
