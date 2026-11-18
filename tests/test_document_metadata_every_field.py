"""Document information writes reach every field of a key and keep the text as given.

A ``content.hpf`` may hold one key twice (made here by copying a field); clearing or setting that key must
not leave the other copy behind. A carriage return written into a field must read back as itself.
"""
from __future__ import annotations

import io
import zipfile
from copy import deepcopy

import pytest
from lxml import etree

from hwpx import HwpxDocument

PART = "Contents/content.hpf"
OPF = "{http://www.idpf.org/2007/opf/}"


def _edited(data: bytes, change) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            raw = source.read(info)
            if info.filename == PART:
                root = etree.fromstring(raw)
                change(root.find(f"{OPF}metadata"))
                raw = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            target.writestr(info, raw)
    return out.getvalue()


def _fields(data: bytes, *names: str) -> list[tuple[str, str]]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        metadata = etree.fromstring(archive.read(PART)).find(f"{OPF}metadata")
    found = []
    for child in metadata:
        key = child.get("name") or etree.QName(child).localname
        if key in names:
            found.append((key, child.text or ""))
    return found


def _source(**fields: str) -> bytes:
    document = HwpxDocument.new()
    document.parts.set_document_metadata(**fields)
    return document.to_bytes()


def _meta(metadata, name: str):
    return next(child for child in metadata if child.get("name") == name)


def _duplicate(name: str, text: str):
    def change(metadata) -> None:
        copy = deepcopy(_meta(metadata, name))
        copy.text = text
        _meta(metadata, name).addnext(copy)

    return change


def test_clearing_authors_empties_every_copy_of_a_key() -> None:
    document = HwpxDocument.open(_edited(_source(creator="C1", lastsaveby="C2"), _duplicate("creator", "C3")))
    assert document.parts.clear_document_authors() == ("creator", "creator", "lastsaveby")
    saved = document.to_bytes()
    assert all(text == "" for _key, text in _fields(saved, "creator", "lastsaveby"))
    assert HwpxDocument.open(saved).parts.clear_document_authors() == ()


def test_cleared_authors_come_back_in_document_order() -> None:
    def swap(metadata) -> None:
        _meta(metadata, "lastsaveby").addnext(_meta(metadata, "creator"))

    document = HwpxDocument.open(_edited(_source(creator="C1", lastsaveby="C2"), swap))
    assert document.parts.clear_document_authors() == ("lastsaveby", "creator")


def test_a_copy_left_empty_still_counts_only_the_ones_that_had_a_value() -> None:
    document = HwpxDocument.open(_edited(_source(creator="C1"), _duplicate("creator", "")))
    assert document.parts.clear_document_authors() == ("creator",)


@pytest.mark.parametrize("key, argument", [("creator", "creator"), ("subject", "subject"), ("keyword", "keyword"),
                                           ("description", "description"), ("lastsaveby", "lastsaveby")])
def test_setting_a_key_writes_every_copy_of_it(key: str, argument: str) -> None:
    document = HwpxDocument.open(_edited(_source(**{argument: "old"}), _duplicate(key, "other")))
    document.parts.set_document_metadata(**{argument: "new"})
    assert [text for _k, text in _fields(document.to_bytes(), key)] == ["new", "new"]


def test_setting_the_title_writes_every_title() -> None:
    def second_title(metadata) -> None:
        title = metadata.find(f"{OPF}title")
        copy = deepcopy(title)
        copy.text = "other"
        title.addnext(copy)

    document = HwpxDocument.open(_edited(_source(title="old"), second_title))
    document.parts.set_document_metadata(title="new")
    assert [text for _k, text in _fields(document.to_bytes(), "title")] == ["new", "new"]


@pytest.mark.parametrize("value", ["A\rB", "A\r\nB", "A\nB", "<&>", "A\r"])
@pytest.mark.parametrize("field", ["title", "description", "subject"])
def test_text_with_carriage_returns_reads_back_as_written(field: str, value: str) -> None:
    # the reading strips surrounding white space (a trailing "\r" reads as nothing either way)
    document = HwpxDocument.open(HwpxDocument.new().to_bytes())
    document.parts.set_document_metadata(**{field: value})
    assert getattr(HwpxDocument.open(document.to_bytes()).parts.metadata, field) == value.strip()
