# SPDX-License-Identifier: Apache-2.0
"""An HWP 5.0 document as the parts of an HWPX package.

:func:`convert` reads the compound file, turns DocInfo into
``Contents/header.xml``, every BodyText section into
``Contents/section<N>.xml`` and its master pages into
``Contents/masterpage<N>.xml``, copies embedded binary data to ``BinData/``
(and the chart part a Hancom chart keeps in its storage to ``Chart/``),
and writes the package files (``mimetype``, ``version.xml``, the
``META-INF`` container, ``Contents/content.hpf``, ``settings.xml`` and the
text preview) around them. :func:`to_hwpx_bytes` zips the parts so the
ordinary HWPX reader can open them.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

from lxml import etree  # type: ignore[reportAttributeAccessIssue]

from . import controls as ct
from . import docinfo as di
from . import records as rec
from . import shapes as sh
from .header_xml import build_header, track_changes
from .owpml import NS, XML_DECLARATION, root, serialize, sub, xml_text
from .reader import Hwp5File, read_hwp5
from .section_xml import ConversionReport, build_section, memo_bodies
from .summary import (
    AUTHOR,
    COMMENTS,
    CREATED,
    DATE_TEXT,
    KEYWORDS,
    LAST_AUTHOR,
    LAST_SAVED,
    SUBJECT,
    TITLE,
    filetime_text,
    read_summary,
)

MIMETYPE = b"application/hwp+zip"

VERSION_XML = (
    XML_DECLARATION
    + b'<hv:HCFVersion xmlns:hv="http://www.hancom.co.kr/hwpml/2011/version" '
    b'tagetApplication="WORDPROCESSOR" major="5" minor="1" micro="1" buildNumber="0" '
    b'os="1" xmlVersion="1.5" application="Hancom Office Hangul" appVersion="13, 0, 0, 1408 WIN32LEWindows_10"/>'
)

CONTAINER_XML = (
    XML_DECLARATION
    + b'<ocf:container xmlns:ocf="urn:oasis:names:tc:opendocument:xmlns:container" '
    b'xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf"><ocf:rootfiles>'
    b'<ocf:rootfile full-path="Contents/content.hpf" media-type="application/hwpml-package+xml"/>'
    b'<ocf:rootfile full-path="Preview/PrvText.txt" media-type="text/plain"/>'
    b'<ocf:rootfile full-path="META-INF/container.rdf" media-type="application/rdf+xml"/>'
    b"</ocf:rootfiles></ocf:container>"
)

MANIFEST_XML = XML_DECLARATION + b'<odf:manifest xmlns:odf="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"/>'

_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_PKG = "http://www.hancom.co.kr/hwpml/2016/meta/pkg#"


@dataclass
class Converted:
    """The parts of the converted package and what could not be converted."""

    files: dict[str, bytes]
    report: ConversionReport
    source: Hwp5File


def _container_rdf(sections: int) -> bytes:
    rdf = etree.Element(f"{{{_RDF}}}RDF", nsmap={"rdf": _RDF})
    for part, kind in [("Contents/header.xml", "HeaderFile")] + [
        (f"Contents/section{index}.xml", "SectionFile") for index in range(sections)
    ]:
        has = etree.SubElement(rdf, f"{{{_RDF}}}Description")
        has.set(f"{{{_RDF}}}about", "")
        part_ref = etree.SubElement(has, f"{{{_PKG}}}hasPart", nsmap={"ns0": _PKG})
        part_ref.set(f"{{{_RDF}}}resource", part)
        describe = etree.SubElement(rdf, f"{{{_RDF}}}Description")
        describe.set(f"{{{_RDF}}}about", part)
        kind_ref = etree.SubElement(describe, f"{{{_RDF}}}type")
        kind_ref.set(f"{{{_RDF}}}resource", _PKG + kind)
    document = etree.SubElement(rdf, f"{{{_RDF}}}Description")
    document.set(f"{{{_RDF}}}about", "")
    kind_ref = etree.SubElement(document, f"{{{_RDF}}}type")
    kind_ref.set(f"{{{_RDF}}}resource", _PKG + "Document")
    return XML_DECLARATION + etree.tostring(rdf, encoding="UTF-8")


def _bin_items(doc: Hwp5File, info: di.DocInfo) -> list[tuple[str, str, bytes, str, bool]]:
    """``(item id, href, payload, media type, embedded)`` for every BinData record.

    A picture, fill, bullet or video refers to its item by the place of the
    BinData record (1 first), not by the id the record keeps (which names its
    stream), so the items are named by place: ``video`` for a file a video
    plays, else ``image`` (or ``ole`` for a storage). A linked file keeps its
    path as its href and has no part.
    """

    videos = {place for section in doc.sections for place in sh.video_files(section.records)}
    items = []
    for place, item in enumerate(info.bin_data, 1):
        kind = "video" if place in videos else "image"
        if item.kind == di.BIN_LINK:
            href = item.abs_path or item.rel_path
            ext = href.rsplit(".", 1)[-1].lower() if "." in href.replace("/", chr(92)).rsplit(chr(92), 1)[-1] else ""
            items.append((f"{kind}{place}", href, b"", f"{kind}/{ext}", False))
            continue
        path = f"BinData/{item.stream_name}"
        if not doc.compound.has_stream(path):
            continue
        raw = doc.compound.read(path)
        compressed = doc.header.compressed if item.compression == 0 else item.compression == 1
        payload = rec.inflate(raw, path) if compressed else raw
        if item.kind == di.BIN_STORAGE:
            items.append((f"ole{place}", f"BinData/ole{place}.ole", payload, "application/ole", False))
        else:
            ext = item.extension
            items.append((f"{kind}{place}", f"BinData/{kind}{place}.{ext}", payload, f"{kind}/{ext.lower()}", True))
    return items


def _content_hpf(
    summary: dict[int, object], master_pages: list[int], bins: list[tuple[str, str, bytes, str, bool]]
) -> bytes:
    """The package manifest and spine; *master_pages* holds the number of
    master pages of each section, whose items go just before the section's."""

    sections = len(master_pages)
    package = root("opf:package")
    package.set("version", "")
    package.set("unique-identifier", "")
    package.set("id", "")
    metadata = sub(package, "opf:metadata")
    title = sub(metadata, "opf:title")
    if summary.get(TITLE):
        title.text = xml_text(summary[TITLE])
    sub(metadata, "opf:language").text = "ko"

    def meta(name: str, value: object) -> None:
        element = sub(metadata, "opf:meta", (("name", name), ("content", "text")))
        if value:
            element.text = xml_text(value)

    meta("creator", summary.get(AUTHOR, ""))
    meta("subject", summary.get(SUBJECT, ""))
    meta("description", summary.get(COMMENTS, ""))
    meta("lastsaveby", summary.get(LAST_AUTHOR, ""))
    created = summary.get(CREATED)
    saved = summary.get(LAST_SAVED)
    meta("CreatedDate", filetime_text(created) if isinstance(created, int) else "")
    meta("ModifiedDate", filetime_text(saved) if isinstance(saved, int) else "")
    meta("date", summary.get(DATE_TEXT, ""))
    meta("keyword", summary.get(KEYWORDS, ""))
    manifest = sub(package, "opf:manifest")
    for item_id, href, _payload, media, embedded in bins:
        attrs: list[tuple[str, object]] = [("id", item_id), ("href", href), ("media-type", media)]
        attrs.append(("isEmbeded", 1 if embedded else 0))
        sub(manifest, "opf:item", attrs)
    sub(manifest, "opf:item", (("id", "header"), ("href", "Contents/header.xml"), ("media-type", "application/xml")))
    first = 0
    for index, count in enumerate(master_pages):
        for number in range(first, first + count):
            sub(
                manifest,
                "opf:item",
                (("id", f"masterpage{number}"), ("href", f"Contents/masterpage{number}.xml"), ("media-type", "application/xml")),
            )
        first += count
        sub(
            manifest,
            "opf:item",
            (("id", f"section{index}"), ("href", f"Contents/section{index}.xml"), ("media-type", "application/xml")),
        )
    sub(manifest, "opf:item", (("id", "settings"), ("href", "settings.xml"), ("media-type", "application/xml")))
    spine = sub(package, "opf:spine")
    sub(spine, "opf:itemref", (("idref", "header"), ("linear", "yes")))
    for index in range(sections):
        sub(spine, "opf:itemref", (("idref", f"section{index}"), ("linear", "yes")))
    return serialize(package)


def _settings(info: di.DocInfo, report: ConversionReport) -> bytes:
    settings = etree.Element(f"{{{NS['ha']}}}HWPApplicationSetting", nsmap={"ha": NS["ha"], "config": NS["config"]})
    caret = etree.SubElement(settings, f"{{{NS['ha']}}}CaretPosition")
    caret.set("listIDRef", str(info.properties.caret_list_id))
    caret.set("paraIDRef", str(info.properties.caret_para_id))
    caret.set("pos", str(info.properties.caret_pos))
    # The print settings DOC_DATA keeps; other document data has no place.
    for record in info.other:
        if record.tag != rec.DOC_DATA:
            continue
        found = ct.print_info(record.payload)
        if found is None:
            report.drop("doc-data")
            continue
        values, unnamed = found
        for _ in range(unnamed):
            report.drop("print-setting")
        if not values:
            continue
        group = etree.SubElement(settings, f"{{{NS['config']}}}config-item-set", name="PrintInfo")
        for name, (_, kind, _) in ct.PRINT_INFO_ITEMS.items():
            if name in values:
                item = etree.SubElement(group, f"{{{NS['config']}}}config-item", name=name, type=kind)
                item.text = ("true" if values[name] else "false") if kind == "boolean" else str(values[name])
    return serialize(settings)


def _preview_text(doc: Hwp5File) -> bytes:
    if not doc.compound.has_stream("PrvText"):
        return b""
    text = doc.compound.read("PrvText").decode("utf-16-le", errors="replace").split("\0", 1)[0]
    return text.encode("utf-8")


def convert(data: bytes) -> Converted:
    """Convert the bytes of a ``.hwp`` file into HWPX package parts."""

    doc = read_hwp5(data)
    info = di.decode_docinfo(doc.docinfo)
    report = ConversionReport()
    header = doc.header
    license_mark = None
    if header.has("ccl") or header.has("kogl"):
        license_mark = ("CCL" if header.has("ccl") else "KOGL", header.flags2, header.kogl_country)
    link_doc = doc.compound.read("DocOptions/_LinkDoc") if doc.compound.has_stream("DocOptions/_LinkDoc") else None
    files: dict[str, bytes] = {"mimetype": MIMETYPE, "version.xml": VERSION_XML}
    bins = _bin_items(doc, info)
    # A Hancom chart keeps its chart part in its OLE storage; the part goes
    # just before the storage, numbered in BinData order, in no manifest.
    charts: dict[str, str] = {}
    for item_id, href, payload, _media, _embedded in bins:
        chart = sh.chart_xml(payload) if item_id.startswith("ole") else None
        if chart is not None:
            charts[item_id] = f"Chart/chart{len(charts) + 1}.xml"
            files[charts[item_id]] = chart
        if href.startswith("BinData/"):
            files[href] = payload
    files["Contents/header.xml"] = build_header(
        info, len(doc.sections), link_doc=link_doc, license_mark=license_mark
    )
    memos = memo_bodies(doc.sections)
    master_pages: list[bytes] = []
    counts: list[int] = []
    parts: list[bytes] = []
    track_ids = [0]
    for section in doc.sections:
        before = len(master_pages)
        parts.append(build_section(section, report, memos, master_pages, charts, track_ids))
        counts.append(len(master_pages) - before)
    for _ in memos:
        report.skip("memo-body")
    # Each section's master pages come just before it, as Hancom stores them.
    first = 0
    for index, (part, count) in enumerate(zip(parts, counts)):
        for number in range(first, first + count):
            files[f"Contents/masterpage{number}.xml"] = master_pages[number]
        first += count
        files[f"Contents/section{index}.xml"] = part
    files["Preview/PrvText.txt"] = _preview_text(doc)
    files["settings.xml"] = _settings(info, report)
    files["META-INF/container.rdf"] = _container_rdf(len(doc.sections))
    summary = read_summary(doc.compound.read("\x05HwpSummaryInformation")) if doc.compound.has_stream(
        "\x05HwpSummaryInformation"
    ) else {}
    files["Contents/content.hpf"] = _content_hpf(summary, counts, bins)
    files["META-INF/container.xml"] = CONTAINER_XML
    files["META-INF/manifest.xml"] = MANIFEST_XML
    # The header leaves out tracked changes it cannot express.
    if track_changes(info) is None:
        report.skip("track-changes")
    return Converted(files, report, doc)


def to_hwpx_bytes(files: dict[str, bytes]) -> bytes:
    """Zip package parts the way HWPX expects: ``mimetype`` first and stored."""

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), files["mimetype"], compress_type=zipfile.ZIP_STORED)
        for name, payload in files.items():
            if name == "mimetype":
                continue
            method = zipfile.ZIP_STORED if name.startswith("BinData/") or name == "version.xml" else zipfile.ZIP_DEFLATED
            zf.writestr(zipfile.ZipInfo(name), payload, compress_type=method)
    return out.getvalue()
