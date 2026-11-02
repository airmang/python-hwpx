"""Regression contracts for the readable source split (no runtime host claim)."""
import hashlib
import json
from pathlib import Path

from hwpx.form_fit import _glyph_table
from hwpx.layout import pages


def test_glyph_constants_unchanged_from_98874a0():
    constants = {k: v for k, v in vars(_glyph_table).items() if k.isupper() and not k.startswith('_')}
    encoded = json.dumps(constants, sort_keys=True, ensure_ascii=False).encode()
    assert hashlib.sha256(encoded).hexdigest() == '0bf1ad707a9509893487d4851faf05cdf5f7ae6fef3fc4d6ea8d5330ec61f4ce'


def test_source_chunks_are_readable_and_bounded():
    root = Path(pages.__file__).parents[1]
    paths = [root / 'layout/pages.py', root / 'layout/_page_flow.py', root / 'form_fit/_glyph_table.py']
    paths += list((root / 'form_fit').glob('_glyph_advances_*.py'))
    for path in paths:
        assert path.stat().st_size < 240 * 1024
        compile(path.read_text(), str(path), 'exec')


def test_facade_hooks_remain_late_bound(monkeypatch):
    marker = object()
    monkeypatch.setattr(pages, '_cached_metrics', lambda para: ())
    assert pages._drawn_lines(None, [marker]) == ((), ())
    assert pages._Paginator.__module__ == pages.__name__
    assert pages._drawn_lines.__module__ == pages.__name__


def test_private_flow_module_can_be_imported_first():
    import subprocess
    import sys
    subprocess.run([sys.executable, "-c", "import hwpx.layout._page_flow; from hwpx.layout import pages; assert pages._Paginator.__module__ == pages.__name__"], check=True)
