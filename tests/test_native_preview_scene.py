"""Synthetic layout contracts; no font files, rasterizer or office application."""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.layout.body_scene import BodySceneSession, build_body_scene
from hwpx.layout.object_scene import build_document_scene


class SyntheticGlyphs:
    """Deliberately simple metrics for semantic contracts, not visual fidelity."""

    def shape(self, text, attributes, style):
        height = attributes['height']
        return [dict(glyphId=ord(c), cluster=i, fontFile='synthetic', faceIndex=0,
                     advance=height / 2, spacingAdvance=0, rawAdvance=height / 2,
                     offset=[0, 0], inkBounds=[0, -height, height / 2, 0],
                     height=height, ratio=100, italic=False,
                     underlinePosition=0, underlineThickness=1)
                for i, c in enumerate(text)]

    def manifest(self):
        return {'fonts': [], 'shapingBackend': {'name': 'synthetic contract metrics'}}


def body_document():
    document = HwpxDocument.new()
    document.add_paragraph('한글 scene contract ' * 5)
    stream = io.BytesIO()
    document.save_to_stream(stream)
    return stream.getvalue()


def test_table_scene_preserves_cells_and_rejects_fidelity_claim():
    data = (Path(__file__).parent / 'fixtures/native_preview/table.hwpx').read_bytes()
    scene = build_document_scene(data, SyntheticGlyphs())
    assert scene['status'] == 'supported'
    assert len(scene['pages']) == 1
    objects = scene['pages'][0]['objects']
    assert sum(len(obj.get('cells', [])) for obj in objects) == 4
    assert scene['qualityValidated'] is False
    assert scene['cacheInputReads'] == 0


def test_source_layout_cache_cannot_change_semantics_or_geometry():
    data = body_document()
    scenes = [build_body_scene(data, SyntheticGlyphs(), cache_mode=mode,
                               inject_test_cache=True)
              for mode in ['ignore', 'remove', 'poison']]
    assert all(s['status'] == 'supported' and s['cacheInputReads'] == 0 for s in scenes)
    assert scenes[0]['pages'] == scenes[1]['pages'] == scenes[2]['pages']
    assert len({s['semanticSha256'] for s in scenes}) == 1


def test_incremental_scene_is_not_mutable_cache_storage():
    data = body_document()
    session = BodySceneSession(SyntheticGlyphs())
    first = session.render(data)
    expected = build_body_scene(data, SyntheticGlyphs())
    first['pages'].clear()
    again = session.render(data)
    assert again['status'] == 'supported'
    assert again['pages'] == expected['pages']
    assert again['incremental']['paragraphsReused'] > 0


def test_shaping_failure_cannot_return_partial_pages():
    class MissingFont(SyntheticGlyphs):
        def shape(self, text, attributes, style):
            raise ValueError('required font unavailable')

    scene = build_body_scene(body_document(), MissingFont())
    assert scene['status'] == 'unsupported'
    assert scene['pages'] == []
    assert any('font unavailable' in reason['reason'] for reason in scene['unsupported'])


def test_unknown_cache_mode_is_rejected():
    with pytest.raises(ValueError, match='cache'):
        build_body_scene(body_document(), SyntheticGlyphs(), cache_mode='reuse-source')


def test_document_scene_uses_one_guarded_document_parse(monkeypatch):
    data = body_document()
    original = HwpxDocument.open
    calls = []

    def counted(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(HwpxDocument, 'open', counted)
    assert build_document_scene(data, SyntheticGlyphs())['status'] == 'supported'
    assert len(calls) == 1
