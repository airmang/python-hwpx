# SPDX-License-Identifier: Apache-2.0
"""Self-contained scrollable document-preview viewer for HWPX packages.

Wraps :func:`hwpx.tools.layout_preview.render_layout_preview` in a document
viewer shell -- a sticky top bar (title, live page indicator, honest fidelity
badge), continuous scroll, and keyboard navigation -- so an agent (or a human)
can read a whole HWPX document top-to-bottom without opening Hancom.

The output is a single HTML file with **no external resources**: all CSS/JS is
inlined and equations render as native MathML.  Pagination is approximate
(Constitution IX); the badge says so.
"""

from __future__ import annotations

from dataclasses import dataclass
import html
from pathlib import Path
from typing import Any

from .layout_preview import LayoutPreview, _base_css, render_layout_preview

# Honest fidelity statement shown in the top bar (Constitution IX).
FIDELITY_BADGE = "텍스트 근사 프리뷰 · 페이지네이션은 한컴과 다를 수 있음 · 수식 MathML 렌더"


@dataclass(frozen=True)
class DocumentViewer:
    """A rendered document viewer: self-contained HTML plus its source preview."""

    html: str
    preview: LayoutPreview
    title: str

    @property
    def page_count(self) -> int:
        return len(self.preview.pages)

    def as_dict(self) -> dict[str, Any]:
        return {
            "html": self.html,
            "title": self.title,
            "pageCount": self.page_count,
            "warnings": list(self.preview.warnings),
            "byteSize": len(self.html.encode("utf-8")),
        }


def _viewer_css() -> str:
    # Chrome styles layered on top of the shared layout-preview CSS.  The page
    # "paper" stays white in light and dark; only the surrounding chrome adapts.
    return (
        ":root { --hv-bar-bg: #ffffff; --hv-bar-fg: #1f2937; --hv-bar-border: #d5dae1;"
        " --hv-surface: #e9ebef; --hv-badge-fg: #6b7280; }\n"
        '@media (prefers-color-scheme: dark) { :root { --hv-bar-bg: #1b1f24;'
        " --hv-bar-fg: #e5e7eb; --hv-bar-border: #333a42; --hv-surface: #14171b;"
        " --hv-badge-fg: #9aa2ad; } }\n"
        ':root[data-theme="dark"] { --hv-bar-bg: #1b1f24; --hv-bar-fg: #e5e7eb;'
        " --hv-bar-border: #333a42; --hv-surface: #14171b; --hv-badge-fg: #9aa2ad; }\n"
        ':root[data-theme="light"] { --hv-bar-bg: #ffffff; --hv-bar-fg: #1f2937;'
        " --hv-bar-border: #d5dae1; --hv-surface: #e9ebef; --hv-badge-fg: #6b7280; }\n"
        "html { background: var(--hv-surface); }\n"
        "body { margin: 0; padding: 0; }\n"
        ".hwpx-viewer-bar { position: sticky; top: 0; z-index: 10;"
        " display: flex; align-items: center; gap: 12px; box-sizing: border-box;"
        " padding: 8px 16px; background: var(--hv-bar-bg); color: var(--hv-bar-fg);"
        " border-bottom: 1px solid var(--hv-bar-border);"
        " font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif;"
        " box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08); }\n"
        ".hwpx-viewer-title { font-weight: 600; font-size: 14px;"
        " white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 45%; }\n"
        ".hwpx-viewer-page { font-variant-numeric: tabular-nums; font-size: 13px;"
        " padding: 2px 10px; border: 1px solid var(--hv-bar-border); border-radius: 999px; }\n"
        ".hwpx-viewer-badge { margin-left: auto; font-size: 11.5px;"
        " color: var(--hv-badge-fg); text-align: right; line-height: 1.3; }\n"
        ".hwpx-viewer-scroll { padding: 16px 12px 40px; }\n"
        ".hwpx-viewer-scroll .hwpx-preview-page { scroll-margin-top: 56px; }\n"
    )


def _viewer_script() -> str:
    # No external resources; IntersectionObserver keeps the page indicator live,
    # and keyboard navigation moves page-by-page.
    return (
        "(function () {\n"
        "  var pages = Array.prototype.slice.call("
        "document.querySelectorAll('.hwpx-preview-page'));\n"
        "  var indicator = document.getElementById('hwpx-viewer-page');\n"
        "  var total = pages.length;\n"
        "  var current = 0;\n"
        "  function setCurrent(index) {\n"
        "    current = Math.max(0, Math.min(index, total - 1));\n"
        "    if (indicator) { indicator.textContent = (current + 1) + ' / ' + total; }\n"
        "  }\n"
        "  setCurrent(0);\n"
        "  if ('IntersectionObserver' in window && total > 0) {\n"
        "    var ratios = new Array(total).fill(0);\n"
        "    var observer = new IntersectionObserver(function (entries) {\n"
        "      entries.forEach(function (entry) {\n"
        "        var i = pages.indexOf(entry.target);\n"
        "        if (i >= 0) { ratios[i] = entry.isIntersecting ? entry.intersectionRatio : 0; }\n"
        "      });\n"
        "      var best = 0, bestRatio = -1;\n"
        "      for (var i = 0; i < total; i++) {\n"
        "        if (ratios[i] > bestRatio) { bestRatio = ratios[i]; best = i; }\n"
        "      }\n"
        "      setCurrent(best);\n"
        "    }, { threshold: [0, 0.25, 0.5, 0.75, 1] });\n"
        "    pages.forEach(function (page) { observer.observe(page); });\n"
        "  }\n"
        "  function goto(index) {\n"
        "    setCurrent(index);\n"
        "    if (pages[current]) { pages[current].scrollIntoView({ behavior: 'smooth', block: 'start' }); }\n"
        "  }\n"
        "  window.addEventListener('keydown', function (event) {\n"
        "    if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) { return; }\n"
        "    switch (event.key) {\n"
        "      case 'PageDown': case 'ArrowRight': goto(current + 1); event.preventDefault(); break;\n"
        "      case 'PageUp': case 'ArrowLeft': goto(current - 1); event.preventDefault(); break;\n"
        "      case 'Home': goto(0); event.preventDefault(); break;\n"
        "      case 'End': goto(total - 1); event.preventDefault(); break;\n"
        "      default: break;\n"
        "    }\n"
        "  });\n"
        "})();\n"
    )


def _viewer_html(title: str, mode: str, pages_html: str, page_count: int) -> str:
    safe_title = html.escape(title)
    count = max(page_count, 1)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="ko">\n'
        "<head>\n"
        '  <meta charset="utf-8" />\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1" />\n'
        f"  <title>{safe_title}</title>\n"
        f"  <style>{_base_css(mode)}{_viewer_css()}</style>\n"
        "</head>\n"
        '<body class="hwpx-viewer" data-hwpx-preview-mode="'
        f'{html.escape(mode)}">\n'
        '  <header class="hwpx-viewer-bar">\n'
        f'    <div class="hwpx-viewer-title">{safe_title}</div>\n'
        f'    <div class="hwpx-viewer-page" id="hwpx-viewer-page">1 / {count}</div>\n'
        f'    <div class="hwpx-viewer-badge">{html.escape(FIDELITY_BADGE)}</div>\n'
        "  </header>\n"
        '  <main class="hwpx-viewer-scroll">\n'
        f"{pages_html}\n"
        "  </main>\n"
        f"  <script>{_viewer_script()}</script>\n"
        "</body>\n"
        "</html>\n"
    )


def render_document_viewer(
    source: str | Path | bytes,
    *,
    title: str = "HWPX 문서 프리뷰",
    mode: str = "pages",
) -> DocumentViewer:
    """Render an HWPX package into a self-contained scrollable document viewer.

    Args:
        source: HWPX file path or raw HWPX bytes.
        title: document title shown in the top bar.
        mode: ``"pages"`` for discrete page boxes (each tracked by the page
            indicator) or ``"long"`` for one continuous page.

    Returns:
        A :class:`DocumentViewer` whose ``html`` is a standalone, CSP-safe HTML
        document (no external resources; equations render as native MathML).
    """

    preview = render_layout_preview(source, mode=mode, title=title)
    pages_html = "".join(preview.page_fragments)
    document = _viewer_html(title, mode, pages_html, len(preview.pages))
    return DocumentViewer(html=document, preview=preview, title=title)


__all__ = ["DocumentViewer", "FIDELITY_BADGE", "render_document_viewer"]
