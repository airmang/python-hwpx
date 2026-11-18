# SPDX-License-Identifier: Apache-2.0
"""The engine contract of ``docs/stable-api.md`` (「엔진 계약」): nine promises, each kept by tests.

The promises that had no test of their own get one here, on Hancom-saved documents; the
section of ``docs/stable-api.md`` names every test that keeps a promise, and the last test
here checks those tests exist.
"""

from __future__ import annotations

import hashlib
import io
import re
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument

ROOT = Path(__file__).resolve().parents[1]
HANCOM = ROOT / "tests" / "fixtures" / "hancom_saved"
STABLE_API = ROOT / "docs" / "stable-api.md"

_SAMPLES = (
    "pages_square_picture_on_paper_lines_on_both_sides.hwpx",
    "pages_footnotes_in_table_cells.hwpx",
    "form_fields_spanning_after.hwpx",
    "pages_outline_labels_paragraph_end_shape.hwpx",
)


def _parts(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {info.filename: archive.read(info.filename) for info in archive.infolist() if not info.is_dir()}


def _texts(document: HwpxDocument) -> list[tuple[str, str]]:
    return [(place.where, place.paragraph.text) for place in document.text.iter_paragraphs()]


# 1. same bytes -> same model, text and bytes ------------------------------------------------


@pytest.mark.parametrize("name", _SAMPLES)
def test_same_bytes_open_to_the_same_model_text_and_bytes(name: str) -> None:
    data = (HANCOM / name).read_bytes()
    first, second = HwpxDocument.open(data), HwpxDocument.open(data)

    assert _texts(first) == _texts(second)
    assert [section.element.get("id") for section in first.sections] == [
        section.element.get("id") for section in second.sections
    ]
    assert first.to_bytes() == second.to_bytes()


def test_same_bytes_give_the_same_answer_in_another_process() -> None:
    code = textwrap.dedent(
        """
        import hashlib, sys
        from hwpx import HwpxDocument
        document = HwpxDocument.open(sys.argv[1])
        text = "\\n".join(place.where + ":" + place.paragraph.text for place in document.text.iter_paragraphs())
        print(hashlib.sha256(text.encode()).hexdigest(), hashlib.sha256(document.to_bytes()).hexdigest())
        """
    )
    path = str(HANCOM / _SAMPLES[1])
    answers = {
        subprocess.run(
            [sys.executable, "-c", code, path], capture_output=True, text=True, check=True,
            env={**__import__("os").environ, "PYTHONHASHSEED": seed}, encoding="utf-8",
        ).stdout.strip()
        for seed in ("1", "2")
    }
    document = HwpxDocument.open(path)
    text = "\n".join(place.where + ":" + place.paragraph.text for place in document.text.iter_paragraphs())
    here = f"{hashlib.sha256(text.encode()).hexdigest()} {hashlib.sha256(document.to_bytes()).hexdigest()}"
    assert answers == {here}


# 2. an unedited save keeps every part's bytes -------------------------------------------------


def _mimetype_compressed(data: bytes) -> bool:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.getinfo("mimetype").compress_type != zipfile.ZIP_STORED


def test_an_unedited_hancom_document_saves_its_parts_unchanged() -> None:
    files = sorted(HANCOM.glob("*.hwpx"))[::25]  # a spread of the Hancom-saved set
    for path in files:
        data = path.read_bytes()
        saved = HwpxDocument.open(data).to_bytes()
        assert _parts(saved) == _parts(data), path.name  # same parts, same bytes in each
        # The file itself, ZIP container and all: the save copies every unchanged entry's record, so this
        # holds whatever deflate this Python has. The one exception it makes on purpose: a `mimetype`
        # stored compressed is written STORED, as the package format asks.
        assert saved == data or _mimetype_compressed(data), path.name


# 3. a public edit changes only its part, and the report says which ----------------------------


def test_a_public_edit_changes_only_its_part_and_says_so(tmp_path: Path) -> None:
    source = HANCOM / _SAMPLES[0]
    document = HwpxDocument.open(source)
    document.paragraphs[3].text = "고친 문단"

    report = document.save(tmp_path / "edited.hwpx", mode="patch")

    changed = {part.path for part in report.changed_parts}
    assert changed == {"Contents/section0.xml"}
    before, after = _parts(source.read_bytes()), _parts((tmp_path / "edited.hwpx").read_bytes())
    assert {name for name in before if before[name] != after.get(name)} == changed


# 5. "opens in Hancom" only where a Hancom record says so --------------------------------------


def test_render_verified_claims_cite_real_hancom_evidence() -> None:
    matrix = (ROOT / "docs" / "support-matrix.md").read_text(encoding="utf-8")
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in matrix.splitlines()
        if line.startswith("| ") and line.count("|") >= 4
    ]
    claimed = [row for row in rows if len(row) >= 3 and "Render-verified" in row[1]]
    assert claimed
    evidence = ("openrate", "실한컴", "한컴", "Hancom", "오라클")
    unbacked = [row[0] for row in claimed if not any(word in row[2] for word in evidence)]
    assert unbacked == []


# 6. unknown elements are written as read ------------------------------------------------------


_UNKNOWN = '<x:note xmlns:x="urn:example:unknown" x:level="2" kind="memo">읽은 대로<x:inner a="1"/></x:note>'


def _with_unknown_content(data: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as source:
        section = source.read("Contents/section0.xml").decode("utf-8")
        header = source.read("Contents/header.xml").decode("utf-8")
        starts = [match.start() for match in re.finditer(r"<hp:p ", section)]
        run_end = section.index("</hp:run>", starts[3])
        section = section[:run_end] + _UNKNOWN + section[run_end:]
        section = section[: starts[3]] + '<hp:p data-extra="kept" ' + section[starts[3] + len("<hp:p "):]
        header = header.replace(
            "</hh:refList>", '<hh:futureList itemCnt="1"><hh:future id="0" value="v"/></hh:futureList></hh:refList>', 1
        )
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as target:
            for info in source.infolist():
                payload = source.read(info.filename)
                if info.filename == "Contents/section0.xml":
                    payload = section.encode("utf-8")
                elif info.filename == "Contents/header.xml":
                    payload = header.encode("utf-8")
                target.writestr(info, payload)
    return out.getvalue()


def test_unknown_elements_are_written_as_read() -> None:
    from lxml import etree

    data = _with_unknown_content((HANCOM / _SAMPLES[0]).read_bytes())
    document = HwpxDocument.open(data)
    document.paragraphs[5].text = "다른 문단을 고친다"  # the section is written again
    document.styles.ensure_run(bold=True)  # and the header

    saved = _parts(document.to_bytes())
    section = etree.fromstring(saved["Contents/section0.xml"])
    notes = section.findall(".//{urn:example:unknown}note")
    assert len(notes) == 1
    note = notes[0]
    assert dict(note.attrib) == {"{urn:example:unknown}level": "2", "kind": "memo"}
    assert note.text == "읽은 대로"
    assert [(child.tag, dict(child.attrib)) for child in note] == [("{urn:example:unknown}inner", {"a": "1"})]
    assert section.find(".//*[@data-extra='kept']") is not None
    header = etree.fromstring(saved["Contents/header.xml"])
    assert header.find(".//{http://www.hancom.co.kr/hwpml/2011/head}future").get("value") == "v"


# the document names the tests that keep each promise ----------------------------------------


def test_every_test_the_engine_contract_names_exists() -> None:
    text = STABLE_API.read_text(encoding="utf-8")
    section = text.split("## 엔진 계약", 1)[1].split("\n## ", 1)[0]
    named = re.findall(r"`(tests/[\w/]+\.py)::(\w+)`", section)
    assert len({promise for promise in re.findall(r"^(\d)\. \*\*", section, re.MULTILINE)}) == 9
    assert len(named) >= 9
    missing = [
        f"{path}::{name}" for path, name in named
        if not re.search(rf"^\s*def {name}\(", (ROOT / path).read_text(encoding="utf-8"), re.MULTILINE)
    ]
    assert missing == []
