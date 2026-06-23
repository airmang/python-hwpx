"""Negative-control toggle for HWPX lineSegArray (layout cache) invalidation.

The current python-hwpx engine removes ``<hp:lineSegArray>`` layout caches when a
document is mutated and, more importantly, strips ALL section layout caches
*unconditionally* at the OPC write boundary
(``opc.package._sanitize_part_for_write`` -> ``_strip_section_layout_caches``).
That blanket strip forces Hancom to recompute layout on open, so anything saved
through ``HwpxPackage`` cannot carry a stale layout cache.

This module lets a measurement harness run the SAME mutation twice:

  * ON  (default engine): layout caches removed   -> Hancom re-layouts
  * OFF (this toggle):    layout caches RETAINED   -> Hancom may trust stale cache

Comparing the two PDF renders from Hancom is the negative control that proves
whether retaining stale ``lineSegArray`` actually causes 글자 겹침 (overlap), or
whether Hancom always re-layouts on open (which would make the blanket strip
belt-and-braces rather than load-bearing).

Usage::

    from lineseg_toggle import lineseg_invalidation
    with lineseg_invalidation(enabled=False):   # control arm: caches retained
        doc = HwpxDocument.open(src)
        ...
        doc.save(out)
"""
from __future__ import annotations

import contextlib
import importlib


# (module_path, attribute_name, replacement_factory)
# The replacement must accept the same call signature and be a no-op that
# returns a benign value, so the engine behaves as if the strip never happened.
_PATCH_TARGETS = [
    # PRIMARY: blanket package-level strip on every section write. This is the
    # real gate — neutralizing it is what actually retains stale caches on save.
    ("hwpx.opc.package", "_strip_section_layout_caches",
     lambda: (lambda payload: payload)),
    # SECONDARY: paragraph/section-level strips used by edit & form-fill paths
    # (these run before the package boundary; neutralized for completeness).
    ("hwpx.oxml._document_impl", "_clear_paragraph_layout_cache",
     lambda: (lambda paragraph: 0)),
    ("hwpx.oxml._document_impl", "_remove_stale_paragraph_layout_cache",
     lambda: (lambda paragraph: False)),
    ("hwpx.form_fill", "_remove_linesegarray",
     lambda: (lambda paragraph: None)),
    ("hwpx.document", "_clear_form_field_layout_cache",
     lambda: (lambda paragraph: 0)),
]


@contextlib.contextmanager
def lineseg_invalidation(*, enabled: bool):
    """Context manager controlling lineSegArray invalidation.

    ``enabled=True``  -> real engine behaviour (layout caches stripped).
    ``enabled=False`` -> layout caches RETAINED (pre-fix / negative-control).

    Yields a small dict describing the mode and which symbols were patched, so
    the harness can record provenance in its manifest.
    """
    if enabled:
        yield {"mode": "ON", "patched": []}
        return

    saved = []
    patched_names = []
    for module_path, attr, factory in _PATCH_TARGETS:
        try:
            module = importlib.import_module(module_path)
        except Exception:
            continue
        if not hasattr(module, attr):
            # Symbol moved/renamed: record nothing, the control self-check in
            # run_pairs.py will flag if caches were not actually retained.
            continue
        saved.append((module, attr, getattr(module, attr)))
        setattr(module, attr, factory())
        patched_names.append(f"{module_path}.{attr}")

    try:
        yield {"mode": "OFF", "patched": patched_names}
    finally:
        for module, attr, original in reversed(saved):
            setattr(module, attr, original)
