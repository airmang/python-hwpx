from __future__ import annotations

import os
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
