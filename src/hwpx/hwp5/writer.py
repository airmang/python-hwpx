# SPDX-License-Identifier: Apache-2.0
"""HWPX package parts -> an HWP 5.0 (``.hwp``) file.

:func:`write_hwp5` reads the manifest for the header, the sections in spine
order, the master pages they refer to and the embedded binary items, builds
DocInfo and BodyText records, compresses them and writes the compound
file. A chart goes in as the OLE object it falls back to, whose storage
holds the chart part; a chart with no OLE object gets one whose storage
holds only the chart part, which Hancom draws the chart from. Content the writer cannot express makes it raise
:class:`~hwpx.hwp5.errors.Hwp5Error` with the code
``hwp5-write-unsupported`` before anything is written.
"""

from __future__ import annotations

import struct
from collections import Counter
from typing import Callable, Mapping

from lxml import etree  # type: ignore[reportAttributeAccessIssue]

from . import controls as ct
from . import docinfo as di
from . import records as rec
from . import shapes as sh
from . import summary as sm
from .cfb import build_compound_file
from .docinfo_writer import build_docinfo, forbidden_chars, set_bin_count, track_changes
from .errors import Hwp5Error
from .fileheader import FileHeader
from .owpml import NS
from .section_writer import SectionRecords, stand_in

VERSION = (5, 1, 1, 0)
#: The FileHeader's encrypt version word: 4 (the scheme of Hangul 7.0 and
#: later), which Hancom writes whether the document is encrypted or not.
ENCRYPT_VERSION = 4
_OPF = NS["opf"]
_HA = NS["ha"]
_HH = NS["hh"]
_CONFIG = NS["config"]



def _manifest(files: Mapping[str, bytes]) -> tuple[str, list[str], list[tuple[str, str]]]:
    """Header path, section paths in spine order, and ``(item id, href)`` of binary items."""

    root = etree.fromstring(files["Contents/content.hpf"])
    items = {item.get("id"): item for item in root.iter(f"{{{_OPF}}}item")}
    base = "Contents/"
    header = "Contents/header.xml"
    sections: list[str] = []
    for ref in root.iter(f"{{{_OPF}}}itemref"):
        item = items.get(ref.get("idref"))
        if item is None:
            continue
        href = item.get("href", "")
        path = href if href.startswith("Contents/") or "/" in href else base + href
        if "header" in (item.get("id") or "") and path.endswith(".xml"):
            header = path
        elif path.endswith(".xml") and "section" in path:
            sections.append(path)
    binaries: list[tuple[str, str]] = []
    for item_id, item in items.items():
        href = item.get("href", "")
        linked = item.get("isEmbeded") == "0" and bool(href) and href not in files and not href.startswith("BinData/")
        if (href.startswith("BinData/") and href in files) or linked:
            binaries.append((item_id or "", href))
    return header, sections, binaries


def _master_pages(files: Mapping[str, bytes]) -> Callable[[str], etree._Element | None]:
    """The root of the part a manifest item id names (a section's master
    page), parsed when first asked for; None when there is no such part."""

    root = etree.fromstring(files["Contents/content.hpf"])
    paths: dict[str, str] = {}
    for item in root.iter(f"{{{_OPF}}}item"):
        href = item.get("href", "")
        paths[item.get("id") or ""] = href if href.startswith("Contents/") or "/" in href else "Contents/" + href
    parsed: dict[str, etree._Element | None] = {}

    def find(item_id: str) -> etree._Element | None:
        if item_id not in parsed:
            path = paths.get(item_id)
            parsed[item_id] = etree.fromstring(files[path]) if path is not None and path in files else None
        return parsed[item_id]

    return find


def _chart_kept(files: Mapping[str, bytes], binaries: list[tuple[str, str]]) -> Callable[[str, str], bool]:
    """Whether an OLE item (its id) holds a chart part (its path) as it is,
    byte for byte: HWP keeps a chart only in its OLE storage."""

    hrefs = dict(binaries)

    def kept(item_id: str, path: str) -> bool:
        href, part = hrefs.get(item_id), files.get(path)
        return href is not None and part is not None and sh.chart_xml(files[href]) == part

    return kept


def _fresh_id(taken: set[str]) -> str:
    n = 1
    while f"ole{n}" in taken:
        n += 1
    return f"ole{n}"


def _bare_charts(roots: list[etree._Element]) -> list[str]:
    """The chart parts of the charts with no OLE object (a chart straight in
    a run, not the chart case of a switch), in document order."""

    return [
        chart.get("chartIDRef", "")
        for root in roots
        for chart in root.iter(f"{{{NS['hp']}}}chart")
        if chart.getparent() is not None and etree.QName(chart.getparent()).localname == "run"
    ]


def _caret(files: Mapping[str, bytes]) -> tuple[int, int, int]:
    data = files.get("settings.xml")
    if not data:
        return 0, 0, 0
    caret = etree.fromstring(data).find(f"{{{_HA}}}CaretPosition")
    if caret is None:
        return 0, 0, 0
    return (int(caret.get("listIDRef", 0)), int(caret.get("paraIDRef", 0)), int(caret.get("pos", 0)))


def _print_info(files: Mapping[str, bytes], unsupported: Counter[str]) -> bytes | None:
    """The DOC_DATA payload of the print settings in settings.xml; None when it
    has none. Settings DOC_DATA has no place for count as unsupported."""

    data = files.get("settings.xml")
    if not data:
        return None
    values: dict[str, int] = {}
    for group in etree.fromstring(data):
        if not isinstance(group.tag, str) or not group.tag.startswith(f"{{{_CONFIG}}}"):
            continue
        name = group.get("name", "")
        if etree.QName(group).localname != "config-item-set" or name != "PrintInfo":
            unsupported[f"settings/{name or etree.QName(group).localname}"] += 1
            continue
        for item in group:
            if not isinstance(item.tag, str):
                continue
            known = ct.PRINT_INFO_ITEMS.get(item.get("name", ""))
            text = (item.text or "").strip()
            if etree.QName(item).localname != "config-item" or known is None:
                unsupported[f"settings/PrintInfo/{item.get('name', '')}"] += 1
            elif known[1] == "boolean":
                values[item.get("name", "")] = int(text == "true")
            elif text.lstrip("-").isdigit():
                values[item.get("name", "")] = int(text)
            else:
                unsupported[f"settings/PrintInfo/{item.get('name', '')}"] += 1
    return ct.print_info_data(values) if values else None


def _summary(files: Mapping[str, bytes]) -> bytes:
    """``\\x05HwpSummaryInformation`` from the package metadata: title,
    subject, author, date text, keywords, description, last author and the
    creation and modification times."""

    metadata = etree.fromstring(files["Contents/content.hpf"]).find(f"{{{_OPF}}}metadata")
    if metadata is None:
        return sm.write_summary({})
    title = metadata.find(f"{{{_OPF}}}title")
    meta = {m.get("name"): (m.text or "") for m in metadata.findall(f"{{{_OPF}}}meta")}
    values: dict[int, object] = {
        sm.TITLE: (title.text or "") if title is not None else "",
        sm.SUBJECT: meta.get("subject", ""),
        sm.AUTHOR: meta.get("creator", ""),
        sm.DATE_TEXT: meta.get("date", ""),
        sm.KEYWORDS: meta.get("keyword", ""),
        sm.COMMENTS: meta.get("description", ""),
        sm.LAST_AUTHOR: meta.get("lastsaveby", ""),
        sm.CREATED: sm.filetime_value(meta.get("CreatedDate", "")),
        sm.LAST_SAVED: sm.filetime_value(meta.get("ModifiedDate", "")),
    }
    return sm.write_summary(values)


def _link_doc(head: etree._Element) -> bytes:
    """``DocOptions/_LinkDoc``: the path of the linked document (room for 260
    characters) and a flag word, bit 0 for page numbers and bit 1 for footnote
    numbers going on from it."""

    link = head.find(f"{{{_HH}}}docOption/{{{_HH}}}linkinfo")
    if link is None:
        return bytes(524)
    path = link.get("path", "").encode("utf-16-le", errors="surrogatepass")[:518]
    flags = int(link.get("pageInherit") in ("1", "true")) | int(link.get("footnoteInherit") in ("1", "true")) << 1
    return path.ljust(520, b"\0") + struct.pack("<I", flags)


def _file_header(head: etree._Element, *, tracked: bool = False) -> FileHeader:
    """FileHeader flags: compressed, plus the CCL or KOGL licence mark when the
    document has one, and changes tracked when it lists them."""

    flags = 1 | (1 << 14 if tracked else 0)
    flags2 = country = 0
    mark = head.find(f".//{{{NS['hh']}}}licensemark")
    if mark is not None:
        flags |= 1 << (11 if mark.get("type") == "CCL" else 15)
        flags2 = int(mark.get("flag", "0") or 0)
        country = int(mark.get("lang", "0") or 0)
    return FileHeader(VERSION, flags, flags2, ENCRYPT_VERSION, country)


def write_hwp5(files: Mapping[str, bytes]) -> bytes:
    """Build the bytes of a ``.hwp`` file from the parts of an HWPX package."""

    header_path, section_paths, binaries = _manifest(files)
    head = etree.fromstring(files[header_path])
    unsupported: Counter[str] = Counter()
    tracked = track_changes(head)
    if tracked is None:
        unsupported["header/trackChanges"] += 1
    if forbidden_chars(head) is None:
        unsupported["header/forbiddenWordList"] += 1
    print_info = _print_info(files, unsupported)
    roots = [etree.fromstring(files[path]) for path in section_paths]
    # A chart with no OLE object gets a storage of its own, after the others.
    storages: dict[str, bytes] = {}
    chart_items: dict[str, str] = {}
    taken = {item_id for item_id, _ in binaries}
    for path in _bare_charts(roots):
        if path in files and path not in chart_items:
            item_id = _fresh_id(taken)
            taken.add(item_id)
            chart_items[path] = item_id
            storages[item_id] = sh.chart_storage(files[path])
            binaries.append((item_id, f"BinData/{item_id}.ole"))
    # Hancom finds a picture's, fill's or bullet's image by the place of its
    # BinData record (1 first), so the binary items are numbered by place.
    bin_ids = {item_id: number for number, (item_id, _) in enumerate(binaries, 1)}
    master_page = _master_pages(files)
    chart_kept = _chart_kept(files, binaries)
    sections: list[list[rec.Record]] = []
    writers: list[SectionRecords] = []
    for root in roots:
        writer = SectionRecords(bin_ids, master_page, chart_kept, chart_items)
        sections.append(writer.section(root))
        writers.append(writer)
    # Memo bodies of every section hang on the last paragraph of the last one.
    memos = [body for writer in writers for body in writer.memo_bodies]
    if memos and sections:
        sections[-1].extend(writers[-1].memo_records(memos))
    for writer in writers:
        unsupported.update(writer.unsupported)
    if unsupported:
        summary = ", ".join(f"{kind} x{count}" for kind, count in sorted(unsupported.items()))
        raise Hwp5Error(
            f"The document holds content the HWP 5.0 writer cannot express yet: {summary}",
            code="hwp5-write-unsupported",
            context={"unsupported": dict(unsupported)},
            suggestion="Save the document as .hwpx instead, or remove the listed content first.",
        )
    docinfo = build_docinfo(head, section_count=len(sections), caret=_caret(files), bin_ids=bin_ids, doc_data=print_info)
    items: list[di.BinDataItem] = []
    streams: list[tuple[str, bytes]] = []
    number = 0
    for item_id, href in binaries:
        if href not in files and item_id not in storages:
            # A linked file: the record keeps its path; it has no stream.
            items.append(di.BinDataItem(di.BIN_LINK, abs_path=href))
            continue
        # A stream is numbered among the items that have one.
        number += 1
        extension = href.rsplit(".", 1)[-1] if "." in href.rsplit("/", 1)[-1] else ""
        storage = extension.lower() == "ole"
        # Hancom names an OLE storage's stream with the extension in capitals.
        item = di.BinDataItem(
            di.BIN_STORAGE if storage else di.BIN_EMBEDDING, bin_id=number, extension="OLE" if storage else extension
        )
        items.append(item)
        streams.append((f"BinData/{item.stream_name}", rec.deflate(storages.get(item_id) or files[href])))
    set_bin_count(docinfo, items)
    # A document that tracks changes keeps its body in ViewText, and in
    # BodyText a stand-in holding only each section's definitions.
    changing = bool(tracked and tracked[0])
    header = _file_header(head, tracked=changing)
    out: list[tuple[str, bytes]] = [
        ("FileHeader", header.to_bytes()),
        ("DocInfo", rec.deflate(rec.serialize_records(docinfo.records))),
    ]
    for index, records in enumerate(sections):
        out.append((f"BodyText/Section{index}", rec.deflate(rec.serialize_records(stand_in(records) if changing else records))))
        if changing:
            out.append((f"ViewText/Section{index}", rec.deflate(rec.serialize_records(records))))
    out.extend(streams)
    out.append(("DocOptions/_LinkDoc", _link_doc(head)))
    out.append(("\x05HwpSummaryInformation", _summary(files)))
    preview = files.get("Preview/PrvText.txt")
    if preview:
        text = preview.decode("utf-8", errors="replace")
        out.append(("PrvText", text.encode("utf-16-le", errors="surrogatepass")))
    image = files.get("Preview/PrvImage.png")
    if image:
        out.append(("PrvImage", image))
    return build_compound_file(out)
