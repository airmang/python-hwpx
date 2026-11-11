# SPDX-License-Identifier: Apache-2.0
"""ENG-36의 작은 결함들: 새 문서 메타데이터, 이력 스냅숏 파트, 병합 표 HTML."""

from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from hwpx import HwpxDocument
from hwpx.templates import blank_document_bytes, new_document_bytes
from hwpx.tools.package_validator import validate_editor_open_safety

ROOT = Path(__file__).resolve().parents[1]
VERSION_HISTORY = ROOT / "tests" / "fixtures" / "gui_probes" / "version_history.hwpx"


def _content_hpf(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.read("Contents/content.hpf").decode("utf-8")


def test_new_document_does_not_carry_the_skeleton_author_or_dates() -> None:
    before = datetime.now(timezone.utc).replace(microsecond=0)
    with HwpxDocument.new() as document:
        metadata = document.package.document_metadata()
        saved = document.to_bytes()
    after = datetime.now(timezone.utc)

    assert metadata is not None
    assert metadata.creator is None
    assert metadata.lastsaveby is None
    assert metadata.date is None
    assert metadata.created_date == metadata.modified_date
    created = datetime.strptime(metadata.created_date, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    assert before <= created <= after

    hpf = _content_hpf(saved)
    assert "synthetic-fixture-author" not in hpf
    assert "2025-09-17" not in hpf
    assert validate_editor_open_safety(saved).ok


def test_new_document_bytes_changes_only_the_metadata(monkeypatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    fresh = new_document_bytes()
    assert fresh == new_document_bytes()  # reproducible under SOURCE_DATE_EPOCH
    assert "2023-11-14T22:13:20Z" in _content_hpf(fresh)

    with zipfile.ZipFile(io.BytesIO(blank_document_bytes())) as skeleton, zipfile.ZipFile(
        io.BytesIO(fresh)
    ) as made:
        assert [i.filename for i in skeleton.infolist()] == [i.filename for i in made.infolist()]
        assert [i.compress_type for i in skeleton.infolist()] == [
            i.compress_type for i in made.infolist()
        ]
        changed = [
            info.filename
            for info in skeleton.infolist()
            if skeleton.read(info.filename) != made.read(info.filename)
        ]
    assert changed == ["Contents/content.hpf"]


def test_history_snapshot_part_does_not_break_to_model() -> None:
    with HwpxDocument.open(VERSION_HISTORY) as document:
        histories = document.parts.histories
        by_name = {history.part_name: history for history in histories}
        snapshot = by_name["DocHistory/historylastdoc.hml"]
        assert not snapshot.is_version_log
        model = snapshot.to_model()
        assert model.version is None and model.entries == []
        logs = [history for history in histories if history.is_version_log]
        assert len(logs) == 2
        assert [len(log.to_model().entries) for log in logs] == [1, 1]


def test_html_export_keeps_merged_cells_in_their_columns() -> None:
    with HwpxDocument.new() as document:
        table = document.add_table(rows=3, cols=3)
        for row in range(3):
            for col in range(3):
                table.cell(row, col).text = f"r{row}c{col}"
        table.merge_cells(0, 0, 0, 1)
        table.merge_cells(1, 0, 2, 0)
        html = document.text.html()

    rows = re.findall(r"<tr>(.*?)</tr>", html, flags=re.S)
    cells = [re.findall(r"<td([^>]*)>", row) for row in rows]
    assert cells == [
        [' colspan="2"', ""],
        [' rowspan="2"', "", ""],
        ["", ""],
    ]
    # 병합이 없는 표는 전과 같은 마크업이다.
    with HwpxDocument.new() as document:
        document.add_table(rows=1, cols=2)
        assert "colspan" not in document.text.html() and "rowspan" not in document.text.html()


def test_tables_all_is_body_level_only_as_documented() -> None:
    with HwpxDocument.new() as document:
        outer = document.add_table(rows=1, cols=1)
        outer.cell(0, 0).add_table(rows=1, cols=1)
        assert len(document.tables.all) == 1
        assert len(outer.cell(0, 0).tables) == 1
