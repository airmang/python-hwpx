# SPDX-License-Identifier: Apache-2.0
"""Same input, same file: ``HwpxDocument.new(seed=..., now=...)``.

Without the two options a new document draws its paragraph/object/memo ids
from ``uuid4`` and stamps ``content.hpf`` (and tracked changes in
``header.xml``) with the clock, so the same script run twice writes three
different parts. With them, every part is byte-identical, across processes too.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import textwrap
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxTypeError
from hwpx.oxml._document_primitives import active_id_source

ROOT = Path(__file__).resolve().parent.parent
FIXED = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

SCRIPT = textwrap.dedent(
    """
    import sys
    from datetime import datetime, timezone
    from hwpx import HwpxDocument

    kwargs = {}
    if sys.argv[2] == "fixed":
        kwargs = {"seed": 7, "now": datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)}
    with HwpxDocument.new(**kwargs) as doc:
        doc.add_paragraph("첫 문단")
        table = doc.add_table(2, 2)
        table.cell(0, 0).text = "가"
        doc.add_paragraph("둘째")
        doc.notes.add_memo("메모", paragraph=0)
        doc.notes.add_footnote("각주", paragraph=0)
        doc.tracking.insert(1, "끼움")
        doc.shapes.add_rectangle(width=3000, height=2000)
        doc.page.set_header(text="머리말")
        doc.page.set_page_number()
        data = doc.to_bytes()
    open(sys.argv[1], "wb").write(data)
    """
)


def _run(path: Path, mode: str, *, extra_env: dict[str, str] | None = None) -> dict[str, bytes]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUTF8"] = "1"
    env.pop("SOURCE_DATE_EPOCH", None)
    # A different hash seed per process: nothing may depend on set/dict order of str.
    env.update(extra_env or {})
    subprocess.run(
        [sys.executable, "-c", SCRIPT, str(path), mode], check=True, env=env, cwd=ROOT
    )
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _parts(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_two_processes_with_seed_and_now_write_identical_parts(tmp_path: Path) -> None:
    first = _run(tmp_path / "a.hwpx", "fixed", extra_env={"PYTHONHASHSEED": "1"})
    second = _run(tmp_path / "b.hwpx", "fixed", extra_env={"PYTHONHASHSEED": "2"})
    assert list(first) == list(second)
    differing = [name for name in first if first[name] != second[name]]
    assert differing == []
    assert (tmp_path / "a.hwpx").read_bytes() == (tmp_path / "b.hwpx").read_bytes()


def test_without_the_options_the_ids_still_differ(tmp_path: Path) -> None:
    first = _run(tmp_path / "a.hwpx", "random")
    second = _run(tmp_path / "b.hwpx", "random")
    assert first["Contents/section0.xml"] != second["Contents/section0.xml"]


def test_the_deterministic_document_opens_and_validates(tmp_path: Path) -> None:
    _run(tmp_path / "a.hwpx", "fixed")
    reopened = HwpxDocument.open(tmp_path / "a.hwpx")
    assert reopened.validate().ok
    metadata = reopened.parts.metadata
    assert metadata is not None
    assert metadata.created_date == "2026-01-02T03:04:05Z"
    assert metadata.modified_date == "2026-01-02T03:04:05Z"


def test_ids_keep_the_hancom_range_and_do_not_repeat() -> None:
    with HwpxDocument.new(seed=1) as doc:
        for index in range(200):
            doc.add_paragraph(f"문단 {index}")
            doc.add_table(1, 1)
        ids = [
            int(node.get("id"))
            for section in doc.sections
            for node in section.element.iter()
            if node.tag.endswith("}p") and node.get("id") not in (None, "0")
        ]
    assert ids and all(1 <= value <= 0x7FFFFFFF for value in ids)
    created = ids[1:]  # the skeleton's own first paragraph is not minted here
    assert len(created) == len(set(created))


def test_now_alone_fixes_the_dates_and_memo_times() -> None:
    with HwpxDocument.new(now=FIXED) as doc:
        memo = doc.notes.add_memo("메모", paragraph=0)
        doc.tracking.insert(0, "끼움")
        data = doc.to_bytes()
    parts = _parts(data)
    assert b"2026-01-02T03:04:05Z" in parts["Contents/content.hpf"]
    assert b"2026-01-02T03:04:05Z" in parts["Contents/header.xml"]
    # A memo's CreateDateTime is the local wall time, as Hangul writes it (its Command FILETIME is UTC).
    local = FIXED.astimezone().strftime("%Y-%m-%dT%H:%M:%SZ").encode()
    assert local in parts["Contents/section0.xml"]
    assert memo is not None


def test_a_naive_now_is_local_time() -> None:
    naive = datetime(2026, 1, 2, 12, 0, 0)
    with HwpxDocument.new(now=naive) as doc:
        stamp = doc.parts.metadata.created_date  # type: ignore[union-attr]
    expected = naive.astimezone().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert stamp == expected


def test_same_seed_in_one_process_gives_the_same_bytes() -> None:
    def build() -> bytes:
        with HwpxDocument.new(seed=11, now=FIXED) as doc:
            doc.add_paragraph("하나")
            doc.add_table(2, 3)
            doc.notes.add_memo("메모", paragraph=0)
            return doc.to_bytes()

    assert build() == build()


def test_close_restores_random_ids() -> None:
    assert active_id_source() is None
    doc = HwpxDocument.new(seed=3)
    assert active_id_source() is not None
    doc.close()
    assert active_id_source() is None
    with HwpxDocument.new(seed=3):
        with HwpxDocument.new(seed=4) as inner:
            assert active_id_source() is inner._id_source
        assert active_id_source() is not None
    assert active_id_source() is None


def test_open_with_seed_makes_edits_deterministic(tmp_path: Path) -> None:
    source = ROOT / "tests" / "fixtures" / "hancom_saved" / "basic.hwpx"
    if not source.exists():
        source = tmp_path / "base.hwpx"
        with HwpxDocument.new(seed=1, now=FIXED) as base:
            base.add_paragraph("바탕")
            source.write_bytes(base.to_bytes())

    def edit() -> bytes:
        with HwpxDocument.open(source, seed=5, now=FIXED) as doc:
            doc.add_paragraph("더한 문단")
            doc.add_table(1, 2)
            return doc.to_bytes()

    assert edit() == edit()


@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"seed": "7"}, "document-seed-invalid"),
        ({"seed": True}, "document-seed-invalid"),
        ({"now": "2026-01-01"}, "document-clock-invalid"),
    ],
)
def test_wrong_types_are_refused(kwargs: dict[str, object], code: str) -> None:
    with pytest.raises(HwpxTypeError) as caught:
        HwpxDocument.new(**kwargs)  # type: ignore[arg-type]
    assert caught.value.code == code
    assert active_id_source() is None
