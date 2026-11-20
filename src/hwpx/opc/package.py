# SPDX-License-Identifier: Apache-2.0
"""Utilities for reading and writing HWPX OPC packages."""

from __future__ import annotations

import hashlib
import logging
import io
from collections import Counter
import warnings
import os
import re
import tempfile
import zlib
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import (
    TYPE_CHECKING,
    Any,
    BinaryIO,
    Iterable,
    Iterator,
    Mapping,
    MutableMapping,
    Sequence,
    TypeVar,
)
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from lxml import etree  # type: ignore[reportAttributeAccessIssue]

from ..errors import HwpxError
from ..oxml.namespaces import serialize_compat_root
from ..oxml.utils import hancom_text_length

if TYPE_CHECKING:
    from .zip_records import ZipRecords, ZipRecordsUnsupported
    from ..oxml.document_metadata import DocumentMetadata
    from ..tools.package_validator import EditorOpenSafetyReport
from .relationships import (
    MAIN_ROOTFILE_MEDIA_TYPE,
    OPF_NS,
    is_header_part_name,
    is_section_part_name,
    normalize_part_name,
    parse_container_rootfiles,
    parse_manifest_relationships,
)
from .security import (
    _duplicate_entry_notice,
    guard_zip_file,
    open_archive,
    read_member,
    read_zip_members,
    register_written_archive,
    sharing_archive_reads,
)
from .xml_utils import (
    extract_xml_declaration,
    keep_source_form,
    iter_declared_namespaces,
    parse_xml,
    serialize_xml,
)

__all__ = [
    "HwpxArchiveError",
    "HwpxCompressedDataError",
    "HwpxPackage",
    "HwpxPackageError",
    "HwpxStructureError",
    "HwpxXmlSyntaxError",
    "RootFile",
    "VersionInfo",
]

logger = logging.getLogger(__name__)
_UNCHECKED_SAVE_TOKEN = object()
_LAYOUT_CACHE_ELEMENT_NAMES = {"linesegarray"}


class _UncheckedSaveBuffer(io.BytesIO):
    """Internal buffer marker for diagnostic snapshots that skip open-safety."""


def _is_integer_literal(value: str | None) -> bool:
    if value is None:
        return False
    try:
        int(value.strip())
    except (TypeError, ValueError):
        return False
    return True


_STYLE_ID_REF = b"styleIDRef"
_NUMERIC_STYLE_ID_REF = re.compile(rb'styleIDRef="[0-9]+"')
_XML_DECLARED_ENCODING = re.compile(rb"""\sencoding\s*=\s*["']([^"']*)["']""")
_UTF8_BOM = b"\xef\xbb\xbf"


def _reads_as_utf8(payload: bytes) -> bool:
    """True when it is certain an XML parser reads *payload* as UTF-8.

    Either it opens with an XML declaration that names UTF-8 or no encoding, or
    it opens with ``<`` and no declaration (and is not UTF-16/32 without a byte
    order mark). Leading whitespace, another encoding or anything unusual
    answers False.
    """

    head = payload[:256]
    if head.startswith(_UTF8_BOM):
        head = head[len(_UTF8_BOM):]
    if not head.startswith(b"<?xml"):
        return head[:1] == b"<" and head[1:2] not in (b"", b"\x00")
    end = head.find(b"?>")
    if end < 0:
        return False
    declared = _XML_DECLARED_ENCODING.search(head[:end])
    return declared is None or declared.group(1).lower() == b"utf-8"


def _names_no_style(payload: bytes) -> bool:
    """True when it is certain that no ``styleIDRef`` in *payload* is a style name.

    That is so when the part is read as UTF-8 and every place the bytes
    ``styleIDRef`` appear is an attribute written ``styleIDRef="<digits>"``.
    Anything else (another encoding, other quoting, a value that is not plain
    digits) answers False, and the caller parses the part to find out.
    """

    if not _reads_as_utf8(payload):
        return False
    return payload.count(_STYLE_ID_REF) == len(_NUMERIC_STYLE_ID_REF.findall(payload))


def _declared_encrypted_parts(data: bytes | None) -> frozenset[str]:
    """Part names that ``META-INF/manifest.xml`` declares encrypted.

    Hancom saves a password-protected HWPX with ODF package encryption: each
    encrypted part gets an ``odf:file-entry`` carrying an ``odf:encryption-data``
    child (AES-256-CBC, PBKDF2), and its bytes in the archive are ciphertext.
    A plain document's ``META-INF/manifest.xml`` is an empty ``odf:manifest``.

    Detection only -- it never raises. A missing or unreadable manifest means
    "nothing declared", so the ordinary parse path keeps reporting whatever is
    actually wrong with the package.
    """

    if not data:
        return frozenset()
    try:
        root = parse_xml(data)
    except (etree.LxmlError, ValueError):  # unreadable, or over a security guard: nothing declared
        return frozenset()
    declared: set[str] = set()
    for entry in root.iter():
        if not isinstance(entry.tag, str) or etree.QName(entry).localname != "file-entry":
            continue
        if not any(
            isinstance(child.tag, str) and etree.QName(child).localname == "encryption-data"
            for child in entry
        ):
            continue
        for key, value in entry.attrib.items():
            if etree.QName(key).localname == "full-path" and value.strip():
                declared.add(normalize_part_name(value))
    return frozenset(declared)


class HwpxPackageError(HwpxError):
    """Base error raised for issues related to :class:`HwpxPackage`.

    It is a :class:`hwpx.errors.HwpxError`: ``code`` is always a kebab-case value
    from ``docs/error-codes.md`` — the reason when the raising code knows it
    (``open-encrypted``, ``open-safety-failed`` …), else the class's
    :attr:`default_code` — with ``suggestion`` and ``context`` as on any
    ``HwpxError``. It is still constructed like a plain exception (positional
    arguments), so the subclasses that are also the exception Python or lxml
    raised (:class:`zipfile.BadZipFile`, ``zlib.error``,
    ``lxml.etree.XMLSyntaxError``) keep their own constructor and attributes.
    lxml's integer error number is kept in ``lxml_code``.
    """

    default_code = "package-invalid"

    def __init__(
        self,
        *args: Any,
        code: str | None = None,
        context: Mapping[str, Any] | None = None,
        suggestion: str | None = None,
    ) -> None:
        # Skip HwpxError.__init__ (one keyword-only message) and run the next
        # constructor in the MRO: Exception, BadZipFile, zlib.error or lxml's
        # XMLSyntaxError(message, code, line, column, filename).
        super(HwpxError, self).__init__(*args)
        lxml_code = getattr(self, "code", None)
        if isinstance(lxml_code, int):
            self.lxml_code = lxml_code
        self.message = str(args[0]) if args else ""
        self.code = code if code is not None else self.default_code
        self.context = dict(context) if context else {}
        self.suggestion = suggestion


class _OpenFolderError(HwpxPackageError, IsADirectoryError):
    """A folder was given where a document file belongs (``code="open-is-folder"``)."""


def _looks_like_text(head: bytes) -> bool:
    """True when *head* decodes as text with almost no control characters."""

    import codecs

    for encoding in ("utf-8", "cp949", "utf-16"):
        try:
            # final=False: the head may end in the middle of a character.
            text = codecs.getincrementaldecoder(encoding)().decode(head, final=False)
        except UnicodeError:  # not UnicodeDecodeError alone: UTF-16 without a byte order mark raises the base class
            continue
        controls = sum(1 for char in text if ord(char) < 32 and char not in "\t\r\n\f")
        return controls <= len(text) // 50
    return False


_PackageErrorT = TypeVar("_PackageErrorT", bound=BaseException)


def _with_reason(
    error: _PackageErrorT,
    code: str,
    suggestion: str,
    context: dict[str, Any] | None = None,
) -> _PackageErrorT:
    """Attach the structured reason to a package error the opening code raises."""

    error.code = code  # type: ignore[attr-defined]
    error.suggestion = suggestion  # type: ignore[attr-defined]
    error.context = dict(context or {})  # type: ignore[attr-defined]
    return error


class HwpxStructureError(HwpxPackageError):
    """Raised when the underlying HWPX package violates the required structure."""

    default_code = "package-structure-invalid"


class HwpxArchiveError(HwpxStructureError, BadZipFile):
    """The input is not a readable ZIP archive (empty, truncated, or not a ZIP).

    It is still a :class:`zipfile.BadZipFile`, so callers that catch that keep
    working; the ``zipfile`` error is the ``__cause__``.
    """

    default_code = "open-archive-damaged"


class HwpxCompressedDataError(HwpxStructureError, zlib.error):
    """A ZIP member's compressed data is damaged.

    It is still a :class:`zlib.error`; the original is the ``__cause__``.
    """

    default_code = "open-archive-damaged"


class HwpxXmlSyntaxError(HwpxStructureError, etree.XMLSyntaxError):
    """An XML part of the package is not well-formed.

    It is still an :class:`lxml.etree.XMLSyntaxError` (``position`` and
    ``lineno`` are kept; lxml's integer error number is ``lxml_code``, since
    ``code`` is the python-hwpx code); the original is the ``__cause__``.
    ``part_name`` is the part that failed when the caller knew it, else ``None``.
    """

    default_code = "package-xml-invalid"
    part_name: str | None = None

    @classmethod
    def wrap(
        cls,
        exc: etree.XMLSyntaxError,
        *,
        part_name: str | None = None,
        message: str | None = None,
    ) -> "HwpxXmlSyntaxError":
        line, column = exc.position or (1, 1)
        if message is None:
            where = f"'{part_name}' 파트" if part_name else "패키지"
            message = f"{where}의 XML이 올바르지 않습니다: {exc.msg}"
        wrapped = cls(message, exc.code, line, column, exc.filename)
        wrapped.part_name = part_name
        return wrapped


@contextmanager
def structure_errors() -> Iterator[None]:
    """Turn the raw exceptions a damaged package raises into structure errors.

    ``zlib.error`` and ``lxml.etree.XMLSyntaxError`` leave as
    :class:`HwpxCompressedDataError` and :class:`HwpxXmlSyntaxError`, with the
    original as ``__cause__``. Errors that are already package errors pass
    through untouched.
    """

    try:
        yield
    except HwpxPackageError:
        raise
    except zlib.error as exc:
        raise HwpxCompressedDataError(f"압축 데이터가 손상됐습니다: {exc}") from exc
    except etree.XMLSyntaxError as exc:
        raise HwpxXmlSyntaxError.wrap(exc) from exc


def _summarize_validation_issues(issues: Sequence[object], *, limit: int = 5) -> str:
    selected = [str(issue) for issue in issues[:limit]]
    remaining = len(issues) - len(selected)
    summary = "; ".join(selected)
    if remaining > 0:
        summary += f" ... and {remaining} more"
    return summary


def _require_unchecked_save_token(token: object | None) -> None:
    if token is not _UNCHECKED_SAVE_TOKEN:
        raise HwpxPackageError(
            "unchecked HWPX save is an internal diagnostic path and requires "
            "the package-private unchecked save token"
        )


def _require_unchecked_save_buffer(destination: object) -> None:
    if not isinstance(destination, _UncheckedSaveBuffer):
        raise HwpxPackageError(
            "unchecked HWPX save is diagnostic-only and cannot write to "
            "caller-provided file paths or streams"
        )


def _capture_stream_checkpoint(stream: BinaryIO) -> "tuple[int, bytes, int | None] | None":
    """:func:`hwpx.quality.save_pipeline._capture_stream_checkpoint` (one rule for both savers)."""

    from ..quality.save_pipeline import _capture_stream_checkpoint as capture

    return capture(stream)


def _rollback_stream(stream: BinaryIO, checkpoint: "tuple[int, bytes, int | None] | None") -> bool:
    """:func:`hwpx.quality.save_pipeline._rollback_stream` (one rule for both savers)."""

    from ..quality.save_pipeline import _rollback_stream as rollback

    return rollback(stream, checkpoint)


def refuse_duplicate_entry_names(names: Iterable[str]) -> None:
    """Refuse to write back an archive that holds one name more than once (*names* are the repeated
    names; nothing happens when there are none).

    A writer that reads parts by name keeps one payload per name (the last, as ``zipfile`` reads it), so
    writing such an archive back would drop or overwrite the other contents without a word. The document
    save and every byte patch (:mod:`hwpx.patch` and the patches built on it) refuse it with this one
    error, before anything is written. Opening and reading such a file stay allowed, and Hangul never
    writes one."""

    repeated = sorted(set(names))
    if not repeated:
        return
    raise HwpxPackageError(
        "the archive holds more than one entry named "
        + ", ".join(repeated[:5])
        + "; writing it back would keep only one of their contents",
        code="save-duplicate-entry-names",
        context={"names": repeated[:20]},
        suggestion=(
            "nothing was written; read what you need from the document, or rebuild the archive with "
            "one entry per name (Hangul's own save does) before editing it"
        ),
    )


def duplicate_entry_names(infos: Iterable[ZipInfo]) -> list[str]:
    """The file names (directory entries aside) that *infos* list more than once, sorted."""

    counts = Counter(info.filename for info in infos if not info.is_dir())
    return sorted(name for name, count in counts.items() if count > 1)


#: The ZipInfo fields a save carries from the source entry (see ``HwpxPackage._zip_info_for_write``); an
#: entry is copied from the source only when every one of them is what the source had.
_RECORD_FIELDS = (
    "date_time",
    "compress_type",
    "comment",
    "extra",
    "create_system",
    "create_version",
    "extract_version",
    "flag_bits",
    "volume",
    "internal_attr",
    "external_attr",
)


def _archive_bytes(stream: str | Path | BinaryIO) -> bytes:
    """All of *stream*'s bytes: the file at a path, or a seekable stream read from its start."""

    if isinstance(stream, (str, os.PathLike)):
        return Path(stream).read_bytes()
    if isinstance(stream, io.BytesIO):
        return stream.getvalue()
    stream.seek(0)
    data = stream.read()
    if not isinstance(data, (bytes, bytearray)):
        raise BadZipFile("the stream did not give bytes")
    return bytes(data)


@dataclass(frozen=True)
class ZipRecordsOutcome:
    """What one archive build did with the source archive's records.

    ``copied`` are the entries written with the source's local record, byte for byte. ``rewritten_reason``
    is set when the source's records could not be used at all (``"zip64"``, ``"duplicate-entry-names"``,
    ...; see :mod:`hwpx.opc.zip_records`) and every entry was compressed again; ``"no-source"`` for a
    package that was not opened from an archive (``new()``, a converted ``.hwp``)."""

    copied: frozenset[str]
    rewritten_reason: str | None

    @classmethod
    def no_source(cls) -> "ZipRecordsOutcome":
        return cls(copied=frozenset(), rewritten_reason="no-source")


class _SourceArchive:
    """The archive a package was opened from: its bytes, the content and ZipInfo of each entry as read,
    and (on first use) where each record lies."""

    def __init__(self, data: bytes, contents: dict[str, bytes], infos: dict[str, ZipInfo]) -> None:
        self.data = data
        self.contents = contents
        self.infos = infos
        self._records: "ZipRecords | None" = None
        self._unsupported: "ZipRecordsUnsupported | None" = None

    def comment(self) -> bytes:
        """The archive comment of the source (``b""`` when it has none or cannot be read so)."""

        try:
            with ZipFile(io.BytesIO(self.data)) as archive:
                return archive.comment
        except (BadZipFile, OSError, ValueError):
            return b""

    def records(self) -> "ZipRecords":
        from .zip_records import ZipRecordsUnsupported, read_records

        if self._unsupported is not None:
            raise self._unsupported
        if self._records is None:
            try:
                self._records = read_records(self.data)
            except ZipRecordsUnsupported as exc:
                self._unsupported = exc
                raise
        return self._records


#: Hangul's order of the ``opf:metadata`` children (every Hancom-saved file writes all ten).
_METADATA_ORDER = (
    "title", "language", "creator", "subject", "description", "lastsaveby",
    "CreatedDate", "ModifiedDate", "date", "keyword",
)
_OPF_URI = b"http://www.idpf.org/2007/opf/"


def _metadata_key(element: etree._Element) -> str:
    local = _local_name(element)
    return (element.get("name") or local) if local == "meta" else local


def _insert_in_hangul_order(metadata_el: etree._Element, element: etree._Element, key: str) -> None:
    """Put *element* (field *key*) before the first child Hangul writes after that field, else last."""

    if key in _METADATA_ORDER:
        later = set(_METADATA_ORDER[_METADATA_ORDER.index(key) + 1:])
        for index, child in enumerate(metadata_el):
            if isinstance(child.tag, str) and _metadata_key(child) in later:
                metadata_el.insert(index, element)
                return
    metadata_el.append(element)


def _splice_metadata(data: bytes, metadata_el: etree._Element) -> bytes | None:
    """*data* (a ``content.hpf``) with the text of each ``opf:metadata`` child that *metadata_el* holds
    differently put in place, and nothing else changed -- the XML declaration, namespace declarations,
    attribute order and spacing stay the bytes that were read. A child *data* lacks is added where Hangul
    writes it, in Hangul's form. ``None`` when the block cannot be edited this way (no ``opf`` prefix, a
    child it cannot find or holding markup, a child gone); the caller then writes the part from the tree."""

    declared = re.search(rb'xmlns:([A-Za-z_][\w.-]*)="' + re.escape(_OPF_URI) + rb'"', data)
    if declared is None:
        return None
    prefix = declared.group(1)
    block = re.search(rb"<" + prefix + rb":metadata\b[^>]*>(.*?)</" + prefix + rb":metadata>", data, re.S)
    if block is None:
        return None
    child = re.compile(
        rb"<" + prefix + rb":(\w+)((?:\s+[\w:.-]+\s*=\s*(?:\"[^\"]*\"|'[^']*'))*)\s*(?:/>|>([^<]*)</"
        + prefix + rb":\1>)"
    )
    found: dict[str, tuple[int, int, bytes, bytes]] = {}
    position = block.start(1)
    end = block.end(1)
    while position < end:
        match = child.match(data, position)
        if match is None:
            if data[position:position + 1].isspace():
                position += 1
                continue
            return None
        local, attributes, text = match.group(1).decode(), match.group(2), match.group(3)
        key = local
        if local == "meta":
            name = re.search(rb'\bname\s*=\s*["\']([^"\']*)["\']', attributes)
            if name is None:
                return None
            key = name.group(1).decode("utf-8")
        if key in found:
            return None
        found[key] = (match.start(), match.end(), attributes, text if text is not None else b"")
        position = match.end()

    wanted: dict[str, str] = {}
    for element in metadata_el:
        if not isinstance(element.tag, str):
            continue
        if len(element):
            return None
        wanted[_metadata_key(element)] = element.text or ""
    if set(found) - set(wanted):
        return None

    def render(local: bytes, attributes: bytes, text: str) -> bytes:
        name = prefix + b":" + local
        if not text:
            return b"<" + name + attributes + b"/>"
        # A carriage return written as itself would read back as a line feed (XML end-of-line handling),
        # so it is written as a character reference, as lxml writes it.
        escaped = (
            text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\r", "&#13;")
        ).encode("utf-8")
        return b"<" + name + attributes + b">" + escaped + b"</" + name + b">"

    edits: list[tuple[int, int, bytes]] = []

    def hangul_place(key: str) -> int:
        return _METADATA_ORDER.index(key) if key in _METADATA_ORDER else len(_METADATA_ORDER)

    for key, text in sorted(wanted.items(), key=lambda item: hangul_place(item[0])):
        if key in found:
            start, stop, attributes, raw = found[key]
            old = etree.fromstring(b"<x>" + raw + b"</x>").text or "" if raw else ""
            if old != text:
                local = b"meta" if key not in ("title", "language") else key.encode()
                edits.append((start, stop, render(local, attributes, text)))
            continue
        if not text:
            continue
        local = key.encode() if key in ("title", "language") else b"meta"
        attributes = b"" if local != b"meta" else b' name="' + key.encode("utf-8") + b'" content="text"'
        order = _METADATA_ORDER.index(key) if key in _METADATA_ORDER else len(_METADATA_ORDER)
        later = [found[k][0] for k in found if k in _METADATA_ORDER and _METADATA_ORDER.index(k) > order]
        at = min(later) if later else end
        edits.append((at, at, render(local, attributes, text)))
    if not edits:
        return data
    # Fields added at the same place (several missing ones before the same field, or at the end) go in
    # Hangul's order: edits were made in that order, so join them in it.
    merged: dict[tuple[int, int], bytes] = {}
    for start, stop, replacement in edits:
        merged[(start, stop)] = merged.get((start, stop), b"") + replacement
    out = data
    # From the end; at one offset a replaced field (start, stop) goes before an insertion (start, start).
    for (start, stop), replacement in sorted(merged.items(), key=lambda item: item[0], reverse=True):
        out = out[:start] + replacement + out[stop:]
    return out



def _write_stream_or_rollback(stream: BinaryIO, data: bytes) -> None:
    checkpoint = _capture_stream_checkpoint(stream)
    if checkpoint is None:
        raise HwpxPackageError(
            "HWPX package stream save requires a checkpointable stream; "
            "use save(path) with a filesystem path for non-seekable outputs"
        )
    try:
        written = stream.write(data)
        if written is not None and written != len(data):
            raise HwpxPackageError(
                "short write while saving HWPX package stream: "
                f"wrote {written} of {len(data)} bytes"
            )
        from ..quality.save_pipeline import settle_written_stream

        settle_written_stream(stream, checkpoint[0], data, checkpoint[1])
    except BaseException as error:
        from ..quality.save_pipeline import _rollback_or_say_so

        _rollback_or_say_so(stream, checkpoint, error)
        raise


def _local_name(element: etree._Element) -> str:
    tag = element.tag
    if not isinstance(tag, str):
        return ""
    try:
        return etree.QName(element).localname
    except ValueError:
        if "}" in tag:
            return tag.rsplit("}", 1)[1]
        return tag


def _paragraph_plain_text_length(paragraph: etree._Element) -> int | None:
    """Length of a simple paragraph in Hancom's text positions, or ``None``.

    Mirrors the oxml-side stale detector: only paragraphs made purely of runs
    with text/tab-like children can be judged at the byte boundary; anything
    else (controls, tables, fields) returns ``None`` so its cache is kept.
    An ``hp:t`` counts its inline elements (line breaks, fixed spaces, tabs)
    at their Hancom widths, as ``hp:lineseg@textpos`` does.
    """
    total = 0
    for child in paragraph:
        child_name = _local_name(child).lower()
        if child_name in _LAYOUT_CACHE_ELEMENT_NAMES:
            continue
        if child_name != "run":
            return None
        for run_child in child:
            run_child_name = _local_name(run_child).lower()
            if run_child_name == "t":
                total += hancom_text_length(run_child)
            elif run_child_name in {"tab", "linebreak", "hyphen", "nbspace"}:
                total += 1
            else:
                return None
    return total


def _paragraph_layout_cache_is_stale(paragraph: etree._Element) -> bool:
    text_length = _paragraph_plain_text_length(paragraph)
    if text_length is None:
        return False
    for child in paragraph:
        if _local_name(child).lower() not in _LAYOUT_CACHE_ELEMENT_NAMES:
            continue
        for line_seg in child:
            if _local_name(line_seg).lower() != "lineseg":
                continue
            textpos = line_seg.get("textpos")
            if textpos is None:
                continue
            try:
                if int(textpos) > text_length:
                    return True
            except ValueError:
                return True
    return False


def _strip_section_layout_caches(payload: bytes) -> bytes:
    """Drop only *stale* paragraph layout caches from a section payload.

    Valid caches are the authored layout of untouched paragraphs; removing
    them forces the editor to re-lay-out entire multi-page documents, which
    shifted page counts and stacked glyphs in the wild form-fill differential
    (specs/031 P0 receipt). The mutating APIs upstream clear the caches of
    exactly the paragraphs they touch, so this byte-boundary sweep only
    guards against writers that left a provably stale cache behind.
    """
    root = parse_xml(payload)
    removed = False
    for parent in root.iter():
        if _local_name(parent).lower() != "p":
            continue
        if not _paragraph_layout_cache_is_stale(parent):
            continue
        for child in list(parent):
            if _local_name(child).lower() in _LAYOUT_CACHE_ELEMENT_NAMES:
                parent.remove(child)
                removed = True
    return _serialize_hwpml_root(root) if removed else payload


def _serialize_hwpml_root(root: etree._Element) -> bytes:
    local_name = _local_name(root)
    if local_name not in {"sec", "head"}:
        return serialize_xml(root, xml_declaration=True)
    return serialize_compat_root(root)


def _normalize_hwpml_root_payload(path: str, payload: bytes) -> bytes:
    if not (is_section_part_name(path) or is_header_part_name(path) or path == HwpxPackage.HEADER_PATH):
        return payload
    root = parse_xml(payload)
    if _local_name(root) not in {"sec", "head"}:
        return payload
    return _serialize_hwpml_root(root)


def _sanitize_part_for_write(path: str, payload: bytes) -> bytes:
    if is_section_part_name(path):
        payload = _strip_section_layout_caches(payload)
    return _normalize_hwpml_root_payload(path, payload)


@dataclass(frozen=True)
class RootFile:
    """Represents a ``rootfile`` entry from ``META-INF/container.xml``."""

    full_path: str
    media_type: str | None = None

    def ensure_exists(self, files: Mapping[str, bytes]) -> None:
        """Ensure that the referenced root file actually exists in ``files``."""

        if self.full_path not in files:
            raise HwpxStructureError(
                f"Root content '{self.full_path}' declared in container.xml is missing."
            )


class VersionInfo:
    """Model for the ``version.xml`` document."""

    def __init__(
        self,
        element: etree._Element,
        namespaces: Mapping[str, str],
        xml_declaration: bytes | None,
    ) -> None:
        self._element = element
        self._namespaces = dict(namespaces)
        self._xml_declaration = xml_declaration
        self._dirty = False

    @classmethod
    def from_bytes(cls, data: bytes) -> VersionInfo:
        element = parse_xml(data)
        namespaces = cls._collect_namespaces(data)
        declaration = cls._extract_declaration(data)
        return cls(element, namespaces, declaration)

    @classmethod
    def default(cls) -> VersionInfo:
        return cls.from_bytes(
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<hv:HCFVersion xmlns:hv="http://www.hancom.co.kr/hwpml/2011/version" '
            b'tagetApplication="WORDPROCESSOR" major="5" minor="1" micro="1" buildNumber="0"/>'
        )

    @staticmethod
    def _collect_namespaces(data: bytes) -> Mapping[str, str]:
        return iter_declared_namespaces(data)

    @staticmethod
    def _extract_declaration(data: bytes) -> bytes | None:
        return extract_xml_declaration(data)

    @property
    def attributes(self) -> Mapping[str, str]:
        return dict(self._element.attrib)

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._element.attrib.get(key, default)

    def set(self, key: str, value: str) -> None:
        self._element.attrib[key] = value
        self._dirty = True

    @property
    def tag(self) -> str:
        return self._element.tag

    def to_bytes(self) -> bytes:
        xml_body = serialize_xml(self._element, xml_declaration=False)
        if self._xml_declaration:
            return self._xml_declaration + xml_body
        return xml_body

    @property
    def dirty(self) -> bool:
        return self._dirty

    def mark_clean(self) -> None:
        self._dirty = False


class HwpxPackage:
    """Represents an HWPX package backed by an Open Packaging Convention container."""

    CONTAINER_PATH = "META-INF/container.xml"
    VERSION_PATH = "version.xml"
    SETTINGS_PATH = "settings.xml"
    MIMETYPE_PATH = "mimetype"
    DEFAULT_MIMETYPE = "application/hwp+zip"
    MANIFEST_PATH = "Contents/content.hpf"
    HEADER_PATH = "Contents/header.xml"
    #: OLE2/CFBF container signature — the HWP v5 (``.hwp``) binary format.
    OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    PREVIEW_PREFIX = "Preview/"
    # An HWP 3.x file is not a compound file: it starts with this text, then the version.
    HWP3_MAGIC = b"HWP Document File V"
    #: ODF package manifest; a password-protected HWPX declares its encrypted
    #: parts here (``odf:encryption-data``).
    ODF_MANIFEST_PATH = "META-INF/manifest.xml"

    def __init__(
        self,
        files: MutableMapping[str, bytes],
        rootfiles: Iterable[RootFile],
        version_info: VersionInfo,
        mimetype: str,
        *,
        zip_infos: Mapping[str, ZipInfo] | None = None,
        zip_order: Sequence[str] | None = None,
    ) -> None:
        self._files = files
        # Open-time baseline for the Safe Write Contract: preservation must be
        # measured against what was actually opened, or a low-level set_part
        # applied before save() would count as "already there" and slip past a
        # mode="patch" grade unnoticed. Values are immutable bytes, so this
        # holds references, not copies.
        self._opened_members: dict[str, bytes] = dict(files)
        self._rootfiles = list(rootfiles)
        self._version = version_info
        self._mimetype = mimetype
        self._zip_infos = dict(zip_infos or {})
        self._opened_zip_infos: dict[str, ZipInfo] = dict(zip_infos or {})
        self._zip_order = list(zip_order or files.keys())
        self._encrypted_parts = _declared_encrypted_parts(files.get(self.ODF_MANIFEST_PATH))
        self._manifest_tree: etree._Element | None = None
        self._spine_cache: list[str] | None = None
        self._section_paths_cache: list[str] | None = None
        self._header_paths_cache: list[str] | None = None
        self._master_page_paths_cache: list[str] | None = None
        self._history_paths_cache: list[str] | None = None
        self._version_path_cache: str | None = None
        self._version_path_cache_resolved = False
        self._settings_path_cache: str | None = None
        self._settings_path_cache_resolved = False
        self._archive_write_depth = 0
        # The archive this package was opened from, to copy the local record of every entry a save leaves
        # unchanged (see _assemble_archive). None for a package built from parts (new(), a converted .hwp).
        self._source_archive: _SourceArchive | None = None
        #: Names the archive it was opened from holds more than once (a save would keep only one payload).
        self._duplicate_entry_names: tuple[str, ...] = ()
        #: The archive's directory entries (``BinData/``), written back by a save as they were.
        self._zip_directories: dict[str, ZipInfo] = {}
        # What the last archive build did with the source's records (MutationReport.preservation).
        self._zip_records_outcome: ZipRecordsOutcome = ZipRecordsOutcome.no_source()
        # The last archive this package built, kept until a clean save makes it the new source.
        self._last_built_archive: _SourceArchive | None = None
        # SHA-256 of the last archive bytes this package's save verified as
        # editor-open safe (see _save_to_zip); None until such a save.
        self._verified_archive_digest: bytes | None = None
        # The report of that validation, for a caller that needs its evidence for the same bytes.
        self._verified_archive_report: "EditorOpenSafetyReport | None" = None
        self._validate_structure()

    @staticmethod
    def _leading_bytes(source: str | Path | BinaryIO, count: int) -> bytes:
        """Peek at the head of *source*, leaving a stream's position where it was."""

        try:
            if isinstance(source, (str, Path)):
                with open(source, "rb") as fh:
                    return fh.read(count)
            position = source.tell()
            try:
                source.seek(0)
                return source.read(count)
            finally:
                source.seek(position)
        except (OSError, AttributeError):
            return b""

    @classmethod
    def _check_open_source(cls, pkg_file: object) -> None:
        """Refuse what cannot be a package before ``zipfile`` turns it into an unrelated error."""

        if isinstance(pkg_file, (str, os.PathLike)):
            path = os.fspath(pkg_file)
            if isinstance(path, str) and os.path.isdir(path):
                raise _with_reason(
                    _OpenFolderError(f"폴더는 문서로 열 수 없습니다: {path}"),
                    "open-is-folder",
                    "그 폴더 안의 .hwpx나 .hwp 파일 경로를 주세요.",
                    {"path": path},
                )
            return
        if isinstance(pkg_file, (bytes, bytearray)):
            return
        if callable(getattr(pkg_file, "read", None)) and callable(getattr(pkg_file, "seek", None)):
            return
        from ..errors import HwpxTypeError

        raise HwpxTypeError(
            f"문서로 열 수 없는 값입니다: {type(pkg_file).__name__}. 경로(str·Path), bytes, "
            "읽고 되감을 수 있는 이진 스트림 중 하나를 주세요.",
            code="open-invalid-type",
            context={"type": type(pkg_file).__name__},
            suggestion="HwpxDocument.open('문서.hwpx')처럼 파일 경로를 넘기세요.",
        )

    @classmethod
    def _not_an_archive(
        cls, stream: str | Path | BinaryIO, exc: BadZipFile
    ) -> "HwpxArchiveError":
        """The error for input ``zipfile`` refused, worded by what the input really is."""

        head = cls._leading_bytes(stream, 512)
        name = os.fspath(stream) if isinstance(stream, (str, os.PathLike)) else getattr(stream, "name", "")
        suffix = os.path.splitext(name)[1].lower() if isinstance(name, str) else ""
        context: dict[str, Any] = {"suffix": suffix, "bytes": len(head)}
        if head.startswith(cls.OLE2_MAGIC):
            return _with_reason(
                HwpxArchiveError(
                    "HwpxPackage는 HWPX 패키지만 엽니다. HWP 5.0(.hwp) 문서는 "
                    "HwpxDocument.open으로 열거나, 한컴오피스에서 HWPX로 변환한 뒤 사용하세요."
                ),
                "open-hwp5-not-package",
                "HwpxDocument.open(...)으로 여세요.",
                context,
            )
        if head.startswith(cls.HWP3_MAGIC):
            return _with_reason(
                HwpxArchiveError(
                    "HWP 3.x 이하 형식의 .hwp 문서는 열 수 없습니다. "
                    "한컴오피스에서 열어 HWPX로 저장한 뒤 사용하세요."
                ),
                "open-hwp3-unsupported",
                "한컴오피스에서 열어 HWPX(.hwpx)로 저장한 뒤 그 파일을 여세요.",
                context,
            )
        if not head:
            return _with_reason(
                HwpxArchiveError("빈 파일입니다(0바이트). 문서 내용이 없습니다."),
                "open-empty-file",
                "저장이 끝난 원본 파일을 다시 받거나 한컴오피스에서 다시 저장하세요.",
                context,
            )
        if suffix == ".hwp":
            return _with_reason(
                HwpxArchiveError(
                    "HWP 문서가 아닙니다: 파일 앞부분이 HWP 5.0 문서 머리(복합 파일)가 아닙니다. "
                    "다른 형식의 파일이거나 손상된 파일입니다."
                ),
                "open-not-hwp",
                "한컴오피스에서 열리는지 확인하고, 열리면 HWPX(.hwpx)로 다시 저장해 여세요.",
                context,
            )
        if head.startswith(b"PK"):
            return _with_reason(
                HwpxArchiveError(
                    f"HWPX 파일이 잘렸거나 손상됐습니다: ZIP 목록을 읽지 못했습니다({exc})."
                ),
                "open-archive-damaged",
                "내려받기·복사가 끝까지 됐는지 확인하고 원본을 다시 받으세요.",
                context,
            )
        textual = _looks_like_text(head)
        what = "텍스트 파일" if textual else "다른 형식의 파일"
        return _with_reason(
            HwpxArchiveError(
                f"HWPX 문서가 아닙니다: {what}입니다(HWPX는 ZIP으로 묶인 파일입니다)."
            ),
            "open-not-hwpx",
            "한/글 문서(.hwpx 또는 .hwp)인지 확인하세요. 다른 형식이면 한컴오피스에서 열어 HWPX로 저장하세요.",
            {**context, "text": textual},
        )

    @classmethod
    def open(cls, pkg_file: str | Path | bytes | bytearray | BinaryIO) -> HwpxPackage:
        cls._check_open_source(pkg_file)
        if isinstance(pkg_file, (bytes, bytearray)):
            stream: str | Path | BinaryIO = io.BytesIO(pkg_file)
        else:
            stream = pkg_file
        # The archive's own bytes, read once: a save copies the records of unchanged entries from them.
        source_bytes = _archive_bytes(stream)

        try:
            # In-memory input goes through ``open_archive`` so the reopen a save
            # does of its own output shares that save's member reads.
            with open_archive(source_bytes) as zf:
                guard_zip_file(zf)
                infos = [info for info in zf.infolist() if not info.is_dir()]
                duplicates = duplicate_entry_names(infos)
                files = read_zip_members(zf)
                zip_infos = {info.filename: info for info in infos}
                # Directory entries hold no part; they are kept (in the central directory's order, with
                # the files) so a save writes them back where they were.
                directories = {info.filename: info for info in zf.infolist() if info.is_dir()}
                zip_order = [info.filename for info in zf.infolist()]
        except BadZipFile as exc:
            # Still a BadZipFile (HwpxArchiveError derives from it); the message says what the
            # input is instead of zipfile's "File is not a zip file".
            raise cls._not_an_archive(stream, exc) from exc
        except zlib.error as exc:
            raise _with_reason(
                HwpxCompressedDataError(f"압축 데이터가 손상됐습니다: {exc}"),
                "open-archive-damaged",
                "내려받기·복사가 끝까지 됐는지 확인하고 원본을 다시 받으세요.",
            ) from exc
        logger.debug("HWPX 패키지 파일 목록 %d개를 로드했습니다.", len(files))
        if cls.MIMETYPE_PATH not in files:
            if "[Content_Types].xml" in files:
                raise _with_reason(
                    HwpxStructureError(
                        "HWPX package is missing the mandatory 'mimetype' file: this is an Office "
                        "Open XML file (.docx/.xlsx/.pptx), not HWPX."
                    ),
                    "open-not-hwpx",
                    "Open it in its own program, or in Hancom Office and save it as .hwpx.",
                    {"format": "ooxml"},
                )
            raise _with_reason(
                HwpxStructureError("HWPX package is missing the mandatory 'mimetype' file."),
                "open-not-hwpx",
                "This ZIP is not an HWPX document; save the document from Hancom Office as .hwpx.",
            )
        try:
            mimetype = files[cls.MIMETYPE_PATH].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise _with_reason(
                HwpxStructureError("HWPX package's 'mimetype' file is not text."),
                "open-not-hwpx",
                "This ZIP is not an HWPX document; save the document from Hancom Office as .hwpx.",
            ) from exc
        with structure_errors():
            rootfiles = cls._parse_container(files.get(cls.CONTAINER_PATH))
            version_info = cls._parse_version(files.get(cls.VERSION_PATH))
            package = cls(
                files,
                rootfiles,
                version_info,
                mimetype,
                zip_infos=zip_infos,
                zip_order=zip_order,
            )
        package._source_archive = _SourceArchive(source_bytes, dict(files), dict(zip_infos))
        package._duplicate_entry_names = tuple(duplicates)
        if duplicates:
            notice = _duplicate_entry_notice(info.filename for info in infos)
            warnings.warn(f"HWPX package: {notice}", UserWarning, stacklevel=3)
        package._zip_directories = {
            name: info for name, info in directories.items() if name not in files
        }
        return package

    @staticmethod
    def _parse_container(data: bytes | None) -> list[RootFile]:
        if data is None:
            raise HwpxStructureError(
                "HWPX package is missing 'META-INF/container.xml'."
            )
        try:
            root = parse_xml(data)
        except Exception:
            # The error is raised to the caller, which reports it; a traceback here would be printed twice.
            logger.debug("container.xml 파싱에 실패했습니다.", exc_info=True)
            raise
        rootfiles = [
            RootFile(ref.full_path, ref.media_type)
            for ref in parse_container_rootfiles(root)
        ]
        if not rootfiles:
            raise HwpxStructureError("container.xml does not declare any rootfiles.")
        return rootfiles

    @staticmethod
    def _parse_version(data: bytes | None) -> VersionInfo:
        if data is None:
            logger.info("HWPX package is missing optional 'version.xml'; using defaults.")
            return VersionInfo.default()
        return VersionInfo.from_bytes(data)

    def _validate_structure(self) -> None:
        for rootfile in self._rootfiles:
            if rootfile.full_path.startswith(self.PREVIEW_PREFIX) and rootfile.full_path not in self._files:
                # A preview holds no content of its own and Hancom opens the document without it,
                # so this is information, not something the caller must act on.
                logger.info(
                    "container.xml이 가리키는 미리보기 '%s'가 패키지에 없습니다. 본문이 아니어서 그대로 엽니다.",
                    rootfile.full_path,
                )
                continue
            rootfile.ensure_exists(self._files)

    @property
    def mimetype(self) -> str:
        return self._mimetype

    @property
    def rootfiles(self) -> tuple[RootFile, ...]:
        return tuple(self._rootfiles)

    def iter_rootfiles(self) -> Iterator[RootFile]:
        yield from self._rootfiles

    @property
    def main_content(self) -> RootFile:
        for rootfile in self._rootfiles:
            if rootfile.media_type == MAIN_ROOTFILE_MEDIA_TYPE:
                return rootfile
        selected = self._rootfiles[0]
        logger.warning(
            "표준 media_type 메인 rootfile이 없어 첫 항목으로 대체합니다: path=%s",
            selected.full_path,
        )
        return selected

    @property
    def version_info(self) -> VersionInfo:
        return self._version

    def read(self, path: str) -> bytes:
        norm_path = self._normalize_path(path)
        try:
            return self._files[norm_path]
        except KeyError as exc:
            logger.debug("파트 누락: path=%s", norm_path)
            raise HwpxPackageError(f"File '{norm_path}' is not present in the package.") from exc

    def write(self, path: str, data: bytes | str) -> None:
        norm_path = self._normalize_path(path)
        if isinstance(data, str):
            data = data.encode("utf-8")
        sanitized = _sanitize_part_for_write(norm_path, data)
        if sanitized is not data:
            # A section or header written anew (stale line caches dropped, the root re-serialized): it keeps
            # the declaration and root namespace declarations the part had (Hangul's for a new part).
            sanitized = keep_source_form(self._files.get(norm_path), sanitized, standalone=True)
        data = sanitized
        pending_rootfiles: list[RootFile] | None = None
        pending_version: VersionInfo | None = None
        if norm_path == self.MIMETYPE_PATH:
            mimetype = data.decode("utf-8")
        elif norm_path == self.CONTAINER_PATH:
            pending_rootfiles = self._parse_container(data)
        elif norm_path == self.VERSION_PATH:
            pending_version = self._parse_version(data)
        self._files[norm_path] = data
        if norm_path not in self._zip_order:
            self._zip_order.append(norm_path)
        if norm_path == self.MIMETYPE_PATH:
            self._mimetype = mimetype
        elif norm_path == self.CONTAINER_PATH:
            assert pending_rootfiles is not None
            self._rootfiles = pending_rootfiles
        elif norm_path == self.VERSION_PATH:
            assert pending_version is not None
            self._version = pending_version
        self._invalidate_caches(norm_path)
        self._validate_structure()

    def delete(self, path: str) -> None:
        norm_path = self._normalize_path(path)
        if norm_path not in self._files:
            raise HwpxPackageError(f"File '{norm_path}' is not present in the package.")
        if norm_path in {self.MIMETYPE_PATH, self.CONTAINER_PATH, self.VERSION_PATH}:
            raise HwpxStructureError(
                "Cannot remove mandatory files ('mimetype', 'container.xml', 'version.xml')."
            )
        del self._files[norm_path]
        self._zip_infos.pop(norm_path, None)
        self._zip_order = [name for name in self._zip_order if name != norm_path]
        self._invalidate_caches(norm_path)
        self._validate_structure()

    @staticmethod
    def _normalize_path(path: str) -> str:
        return normalize_part_name(path)

    def files(self) -> list[str]:
        return sorted(self._files)

    def part_names(self) -> list[str]:
        return self.files()

    def has_part(self, part_name: str) -> bool:
        return self._normalize_path(part_name) in self._files

    def get_part(self, part_name: str) -> bytes:
        return self.read(part_name)

    def set_part(self, part_name: str, payload: bytes | str | etree._Element) -> None:
        if isinstance(payload, etree._Element):
            # A tree is one this package parsed (2016 HWPML URIs read as 2011): keep the part's own
            # namespace declarations.
            self._set_serialized_part(part_name, serialize_xml(payload, xml_declaration=True))
            return
        elif isinstance(payload, str):
            data = payload.encode("utf-8")
        elif isinstance(payload, bytes):
            data = payload
        else:
            raise TypeError(f"unsupported part payload type: {type(payload)!r}")
        self.write(part_name, data)

    def _set_serialized_part(self, part_name: str, data: bytes) -> None:
        """Write *data*, a part the engine serialized from the tree it parsed from this part, putting back
        its XML declaration and root namespace declarations as read (:func:`keep_source_form`)."""

        previous = self._files.get(self._normalize_path(part_name))
        self.write(part_name, keep_source_form(previous, data))

    def get_xml(self, part_name: str) -> etree._Element:
        data = self.read(part_name)
        try:
            return parse_xml(data)
        except etree.XMLSyntaxError as exc:
            # The exception type callers already catch (XMLSyntaxError) stays;
            # it also becomes a structure error, names the part, and carries
            # the original lxml error as __cause__.
            normalized = self._normalize_path(part_name)
            if normalized not in self._encrypted_parts:
                raise HwpxXmlSyntaxError.wrap(exc, part_name=normalized) from exc
            encrypted = HwpxXmlSyntaxError.wrap(
                exc,
                part_name=normalized,
                message=(
                    "암호가 걸린 HWPX 문서는 지원하지 않습니다"
                    f"('{normalized}' 파트가 암호화돼 있습니다). "
                    "한컴오피스에서 문서 암호를 해제한 뒤 다시 저장해 사용하세요."
                ),
            )
            # The reason is known, so ``code`` is the stable string, not lxml's number for
            # "start tag expected"; that number stays in ``lxml_code``.
            encrypted.lxml_code = exc.code  # type: ignore[attr-defined]
            raise _with_reason(
                encrypted,
                "open-encrypted",
                "한컴오피스에서 문서 암호를 해제하고 다시 저장한 뒤 여세요.",
                {"part": normalized},
            ) from exc

    def set_xml(self, part_name: str, element: etree._Element) -> None:
        self.set_part(part_name, element)

    def get_text(self, part_name: str, encoding: str = "utf-8") -> str:
        return self.read(part_name).decode(encoding)

    def manifest_tree(self) -> etree._Element:
        if self._manifest_tree is None:
            self._manifest_tree = self.get_xml(self.main_content.full_path)
        return self._manifest_tree

    def _manifest_items(self) -> list[etree._Element]:
        manifest = self.manifest_tree()
        return list(manifest.findall("./opf:manifest/opf:item", OPF_NS))

    @staticmethod
    def _normalized_manifest_value(element: etree._Element) -> str:
        values = [
            element.attrib.get("id", ""),
            element.attrib.get("href", ""),
            element.attrib.get("media-type", ""),
            element.attrib.get("properties", ""),
        ]
        return " ".join(part.lower() for part in values if part)

    @classmethod
    def _manifest_matches(cls, element: etree._Element, *candidates: str) -> bool:
        normalized = cls._normalized_manifest_value(element)
        return any(candidate in normalized for candidate in candidates if candidate)

    def _resolve_spine_paths(self) -> list[str]:
        if self._spine_cache is None:
            relationships = parse_manifest_relationships(
                self.manifest_tree(),
                self.main_content.full_path,
                known_parts=self._files.keys(),
            )
            self._spine_cache = list(relationships.spine_paths)
        return self._spine_cache

    def section_paths(self) -> list[str]:
        if self._section_paths_cache is None:
            paths = [
                path
                for path in self._resolve_spine_paths()
                if path and is_section_part_name(path)
            ]
            if not paths:
                logger.warning("manifest spine에서 section 경로를 찾지 못해 파일명 기반 fallback을 사용합니다.")
                paths = [
                    name
                    for name in self._files.keys()
                    if is_section_part_name(name)
                ]
            self._section_paths_cache = paths
        return list(self._section_paths_cache)

    def header_paths(self) -> list[str]:
        if self._header_paths_cache is None:
            paths = [
                path
                for path in self._resolve_spine_paths()
                if path and is_header_part_name(path)
            ]
            if not paths and self.has_part(self.HEADER_PATH):
                logger.warning(
                    "manifest spine에서 header 경로를 찾지 못해 기본 header 경로 fallback을 사용합니다: %s",
                    self.HEADER_PATH,
                )
                paths = [self.HEADER_PATH]
            self._header_paths_cache = paths
        return list(self._header_paths_cache)

    def master_page_paths(self) -> list[str]:
        if self._master_page_paths_cache is None:
            paths = list(
                parse_manifest_relationships(
                    self.manifest_tree(),
                    self.main_content.full_path,
                    known_parts=self._files.keys(),
                ).master_page_paths
            )
            if not paths:
                paths = [
                    name
                    for name in self._files.keys()
                    if "master" in PurePosixPath(name).name.lower()
                    and "page" in PurePosixPath(name).name.lower()
                ]
                # masterPage가 아예 없는 문서가 정상이므로, manifest가 실재
                # 파일을 놓친 경우에만 경고한다.
                if paths:
                    logger.warning(
                        "manifest에서 masterPage를 찾지 못해 파일명 탐색 fallback을 사용합니다."
                    )
            self._master_page_paths_cache = paths
        return list(self._master_page_paths_cache)

    def history_paths(self) -> list[str]:
        if self._history_paths_cache is None:
            paths = list(
                parse_manifest_relationships(
                    self.manifest_tree(),
                    self.main_content.full_path,
                    known_parts=self._files.keys(),
                ).history_paths
            )
            if not paths:
                paths = [
                    name
                    for name in self._files.keys()
                    if "history" in PurePosixPath(name).name.lower()
                ]
                # history가 없는 문서가 정상이므로, manifest가 실재 파일을
                # 놓친 경우에만 경고한다.
                if paths:
                    logger.warning(
                        "manifest에서 history를 찾지 못해 파일명 탐색 fallback을 사용합니다."
                    )
            self._history_paths_cache = paths
        return list(self._history_paths_cache)

    def version_path(self) -> str | None:
        if not self._version_path_cache_resolved:
            path = parse_manifest_relationships(
                self.manifest_tree(),
                self.main_content.full_path,
                known_parts=self._files.keys(),
            ).version_path
            if path is None and self.has_part(self.VERSION_PATH):
                # 실제 한컴 산출물은 version.xml을 manifest에 선언하지 않고
                # 고정 경로로 둔다(gold fixtures 실측). 정상 경로이므로 경고
                # 대신 debug로 남긴다.
                logger.debug(
                    "manifest에 version 항목이 없어 고정 경로를 사용합니다: %s",
                    self.VERSION_PATH,
                )
                path = self.VERSION_PATH
            self._version_path_cache = path
            self._version_path_cache_resolved = True
        return self._version_path_cache

    def settings_path(self) -> str | None:
        if not self._settings_path_cache_resolved:
            path = parse_manifest_relationships(
                self.manifest_tree(),
                self.main_content.full_path,
                known_parts=self._files.keys(),
            ).settings_path
            if path is None and self.has_part(self.SETTINGS_PATH):
                # 실코퍼스 177파일 전수: settings.xml은 manifest item(id=
                # "settings")으로 정상 선언되지만, version.xml과 같은 이유로
                # 고정 경로 fallback도 둔다.
                logger.debug(
                    "manifest에 settings 항목이 없어 고정 경로를 사용합니다: %s",
                    self.SETTINGS_PATH,
                )
                path = self.SETTINGS_PATH
            self._settings_path_cache = path
            self._settings_path_cache_resolved = True
        return self._settings_path_cache

    # ------------------------------------------------------------------
    # Manifest item helpers (for BinData / images)
    # ------------------------------------------------------------------

    def _manifest_element(self) -> etree._Element | None:
        """Return the ``<opf:manifest>`` element."""
        manifest = self.manifest_tree()
        return manifest.find("opf:manifest", OPF_NS)

    # ------------------------------------------------------------------
    # Document metadata (opf:metadata) -- cycle 6.12 트레인㊸.
    # Deliberately built on the SAME manifest_tree()/_persist_manifest()
    # machinery add_manifest_item/remove_manifest_item already use, not a
    # second independent representation of content.hpf -- HwpxOxmlDocument
    # holds the exact same tree object (assigned from this same
    # manifest_tree() call in HwpxOxmlDocument.from_package), so writing
    # here is visible there too and there's no risk of one path's edit
    # silently clobbering the other's at save time.
    # ------------------------------------------------------------------

    def _metadata_element(self, *, create: bool = False) -> etree._Element | None:
        """Return the ``<opf:metadata>`` element (sibling of ``opf:manifest``)."""
        manifest = self.manifest_tree()
        metadata_el = manifest.find("opf:metadata", OPF_NS)
        if metadata_el is None and create:
            metadata_el = manifest.makeelement(f"{{{OPF_NS['opf']}}}metadata", {})
            manifest.insert(0, metadata_el)
        return metadata_el

    def document_metadata(self) -> "DocumentMetadata | None":
        """Parse ``opf:metadata`` into a :class:`~hwpx.oxml.document_metadata.
        DocumentMetadata` snapshot. ``None`` if the part has no metadata
        block at all (real corpus: 65/67 fixtures have one)."""
        from ..oxml.document_metadata import parse_document_metadata

        metadata_el = self._metadata_element(create=False)
        if metadata_el is None:
            return None
        return parse_document_metadata(metadata_el)

    def set_document_metadata(
        self,
        *,
        title: str | None = None,
        creator: str | None = None,
        subject: str | None = None,
        keyword: str | None = None,
        created_date: str | None = None,
        modified_date: str | None = None,
        description: str | None = None,
        lastsaveby: str | None = None,
        date: str | None = None,
    ) -> None:
        """Set the given ``opf:metadata`` fields; omitted (``None``) fields
        are left untouched and ``""`` empties one. ``description``,
        ``lastsaveby`` and the free-form ``date`` are written as given (raw
        strings, as ``created_date`` is); ``doc.parts.set_document_metadata``
        writes ``date`` in Hangul's form from a ``datetime``. Scoped to exactly the 6 fields with real
        corpus evidence worth authoring (title/creator/subject/keyword/
        CreatedDate/ModifiedDate) -- ``date``/``description``/
        ``lastsaveby``/``language`` stay read-only (``date`` especially:
        see ``oxml.document_metadata``'s own docstring for why its
        multi-format reality rules out safe authoring).

        ``created_date``/``modified_date`` are raw strings here, not
        ``datetime`` objects -- pass an already-formatted ISO 8601 string
        (``"%Y-%m-%dT%H:%M:%SZ"``, matching the real corpus's own 100%
        -consistent format) if setting these; this function does not
        format or validate the value, matching this module's own
        preserve-what-you-give-it convention for every other field.
        """

        metadata_el = self._metadata_element(create=True)
        # create=True always returns an element -- an internal invariant, not
        # a user-facing error condition, so this narrows the type for mypy
        # without adding to the untyped-error census (error_code_census.py
        # only walks ast.Raise, not ast.Assert).
        assert metadata_el is not None

        # A key written twice in the block (not Hangul's form, but readable) gets the value in every copy:
        # a copy left with the old value would still say it.
        if title is not None:
            titles = metadata_el.findall(f"{{{OPF_NS['opf']}}}title")
            if not titles:
                titles = [metadata_el.makeelement(f"{{{OPF_NS['opf']}}}title", {})]
                metadata_el.insert(0, titles[0])
            for title_el in titles:
                title_el.text = title or None

        for field_name, value in (
            ("creator", creator),
            ("subject", subject),
            ("keyword", keyword),
            ("CreatedDate", created_date),
            ("ModifiedDate", modified_date),
            ("description", description),
            ("lastsaveby", lastsaveby),
            ("date", date),
        ):
            if value is None:
                continue
            metas = [
                candidate
                for candidate in metadata_el.findall(f"{{{OPF_NS['opf']}}}meta")
                if candidate.get("name") == field_name
            ]
            if not metas:
                metas = [metadata_el.makeelement(
                    f"{{{OPF_NS['opf']}}}meta", {"name": field_name, "content": "text"}
                )]
                _insert_in_hangul_order(metadata_el, metas[0], field_name)
            for meta_el in metas:
                meta_el.text = value or None

        self._persist_metadata(metadata_el)

    def _clear_named_meta(self, names: Iterable[str]) -> list[str]:
        """Empty every ``opf:meta`` whose ``name`` is one of *names* -- each copy of a key -- and return the
        name of each one that held a value, in document order. Missing fields are not created."""

        metadata_el = self._metadata_element(create=False)
        if metadata_el is None:
            return []
        wanted = set(names)
        meta_tag = f"{{{OPF_NS['opf']}}}meta"
        cleared: list[str] = []
        for child in metadata_el:
            if child.tag != meta_tag or child.get("name") not in wanted:
                continue
            if (child.text or "").strip() or len(child):
                cleared.append(str(child.get("name")))
            for grandchild in list(child):
                child.remove(grandchild)
            child.text = None
        if cleared:
            self._persist_metadata(metadata_el)
        return cleared

    def clear_document_metadata(
        self,
        *,
        keep: Iterable[str] = ("title", "language"),
        timestamp: str = "1970-01-01T00:00:00Z",
    ) -> list[str]:
        """Empty every ``opf:metadata`` field whose key is not in *keep*.

        A child's key is its ``name`` attribute for ``opf:meta`` and its
        local name otherwise (``title``, ``language``). Names this library
        does not model are cleared too, so metadata a caller does not know
        about does not survive. An ``opf:meta`` whose name contains
        ``"Date"`` (``CreatedDate``/``ModifiedDate``) gets *timestamp*;
        every other cleared element keeps its attributes and loses its
        content -- the free-form ``date`` field is emptied, never
        timestamped. Missing elements are not created. A bare string
        *keep* counts as one key.

        Returns the cleared keys in document order; ``[]`` when the part has
        no metadata block.
        """

        metadata_el = self._metadata_element(create=False)
        if metadata_el is None:
            return []
        kept = {keep} if isinstance(keep, str) else set(keep)
        meta_tag = f"{{{OPF_NS['opf']}}}meta"

        cleared: list[str] = []
        for child in metadata_el:
            if not isinstance(child.tag, str):
                continue  # comments and processing instructions carry no field
            is_meta = child.tag == meta_tag
            key = (child.get("name") if is_meta else None) or _local_name(child)
            if key in kept:
                continue
            for grandchild in list(child):
                child.remove(grandchild)
            child.text = timestamp if is_meta and "Date" in key else None
            cleared.append(key)

        if cleared:
            self._persist_metadata(metadata_el)
        return cleared

    def add_manifest_item(
        self,
        item_id: str,
        href: str,
        media_type: str,
        *,
        extra_attrs: dict[str, str] | None = None,
    ) -> None:
        """Add an ``<opf:item>`` to the manifest if *item_id* is not present.

        ``extra_attrs`` carries item-specific manifest attributes — notably
        ``isEmbeded="1"`` for embedded BinData images (OWPML's single-d spelling),
        which real Hancom requires to render an embedded picture.
        """
        manifest_el = self._manifest_element()
        if manifest_el is None:
            raise HwpxStructureError("Manifest does not contain an <opf:manifest> element.")

        for existing in manifest_el.findall("opf:item", OPF_NS):
            if existing.get("id") == item_id:
                return  # already present

        attrs = {"id": item_id, "href": href, "media-type": media_type}
        if extra_attrs:
            attrs.update(extra_attrs)
        new_item = manifest_el.makeelement(f"{{{OPF_NS['opf']}}}item", attrs)
        manifest_el.append(new_item)
        self._persist_manifest()

    def remove_manifest_item(self, item_id: str) -> bool:
        """Remove an ``<opf:item>`` by its manifest ``id``.  Returns ``True`` on success.

        *item_id* is the manifest id (``"image1"``), not a part path --
        :meth:`part_names` returns paths (``"BinData/image1.png"``). When no
        item has that id and the value contains ``/``, an item whose
        ``href`` names the same part (normalized like part names) is
        removed instead.
        """
        manifest_el = self._manifest_element()
        if manifest_el is None:
            return False

        items = manifest_el.findall("opf:item", OPF_NS)
        match = next((item for item in items if item.get("id") == item_id), None)
        if match is None and "/" in item_id:
            part_name = normalize_part_name(item_id)
            match = next(
                (item for item in items if normalize_part_name(item.get("href", "")) == part_name),
                None,
            )
        if match is None:
            return False
        manifest_el.remove(match)
        self._persist_manifest()
        return True

    def _persist_metadata(self, metadata_el: etree._Element) -> None:
        """Write a change of ``opf:metadata`` alone: only the text of the fields that changed moves
        (:func:`_splice_metadata`); a part that cannot be edited so is written from the tree."""

        path = self.main_content.full_path
        current = self._files.get(self._normalize_path(path))
        spliced = None if current is None else _splice_metadata(current, metadata_el)
        if spliced is None:
            self._persist_manifest()
        elif spliced != current:
            # The tree holds this change and any manifest change not written yet (a section the document
            # added, written when it saves): writing the part must not drop the tree for one re-read from
            # bytes that lack them.
            tree = self._manifest_tree
            self.write(path, spliced)
            self._manifest_tree = tree

    def _persist_manifest(self) -> None:
        """Write the in-memory manifest tree back to the package."""
        tree = self._manifest_tree
        if tree is not None:
            self.set_part(self.main_content.full_path, tree)

    def _invalidate_caches(self, changed_path: str) -> None:
        if changed_path in {self.CONTAINER_PATH, self.main_content.full_path}:
            self._manifest_tree = None
        self._spine_cache = None
        self._section_paths_cache = None
        self._header_paths_cache = None
        self._master_page_paths_cache = None
        self._history_paths_cache = None
        self._version_path_cache = None
        self._version_path_cache_resolved = False
        self._settings_path_cache = None
        self._settings_path_cache_resolved = False

    def _iter_header_part_paths_for_safety_normalization(self) -> list[str]:
        paths: list[str] = []
        try:
            paths.extend(self.header_paths())
        except Exception:
            logger.debug("failed to resolve header paths for safety normalization", exc_info=True)
        paths.extend(
            path
            for path in self._files
            if is_header_part_name(path) or path == self.HEADER_PATH
        )
        return list(dict.fromkeys(path for path in paths if path in self._files))

    def _iter_section_part_paths_for_safety_normalization(self) -> list[str]:
        paths: list[str] = []
        try:
            paths.extend(self.section_paths())
        except Exception:
            logger.debug("failed to resolve section paths for safety normalization", exc_info=True)
        paths.extend(path for path in self._files if is_section_part_name(path))
        return list(dict.fromkeys(path for path in paths if path in self._files))

    def _style_name_id_map_for_safety_normalization(self) -> dict[str, str]:
        aliases: dict[str, str] = {}
        conflicts: set[str] = set()
        for path in self._iter_header_part_paths_for_safety_normalization():
            try:
                root = parse_xml(self._files[path])
            except Exception:
                continue
            for style in root.iter():
                if _local_name(style) != "style":
                    continue
                style_id = style.get("id")
                if not _is_integer_literal(style_id):
                    continue
                resolved_id = style_id.strip()
                for attr_name in ("name", "engName"):
                    alias = (style.get(attr_name) or "").strip()
                    if not alias:
                        continue
                    existing = aliases.get(alias)
                    if existing is not None and existing != resolved_id:
                        conflicts.add(alias)
                        continue
                    aliases[alias] = resolved_id

        for alias in conflicts:
            aliases.pop(alias, None)
        return aliases

    def _normalize_named_style_references_for_safety(self) -> None:
        style_ids_by_name = self._style_name_id_map_for_safety_normalization()
        if not style_ids_by_name:
            return

        for path in self._iter_section_part_paths_for_safety_normalization():
            if _names_no_style(self._files[path]):
                continue  # nothing to convert; parsing the part would find the same
            try:
                root = parse_xml(self._files[path])
            except Exception:
                continue
            changed = False
            for paragraph in root.iter():
                if _local_name(paragraph) != "p":
                    continue
                style_id_ref = paragraph.get("styleIDRef")
                if style_id_ref is None or _is_integer_literal(style_id_ref):
                    continue
                replacement = style_ids_by_name.get(style_id_ref.strip())
                if replacement is None or replacement == style_id_ref:
                    continue
                paragraph.set("styleIDRef", replacement)
                changed = True
            if changed:
                self._files[path] = keep_source_form(self._files[path], _serialize_hwpml_root(root), standalone=True)

    def save(
        self,
        pkg_file: str | Path | BinaryIO | None = None,
        updates: Mapping[str, bytes | str | etree._Element] | None = None,
    ) -> str | Path | BinaryIO | bytes | None:
        if updates:
            for part_name, payload in updates.items():
                self.set_part(part_name, payload)

        destination = pkg_file
        if destination is None:
            return self._save_to_bytes(verify_open_safety=True, mark_clean=True)

        self._save_to_zip(destination, verify_open_safety=True)
        return destination

    def _save_bytes_unchecked(
        self,
        updates: Mapping[str, bytes | str | etree._Element] | None = None,
        *,
        _unchecked_token: object | None = None,
    ) -> bytes:
        """Return archive bytes without editor-open validation for internal diagnostics."""

        _require_unchecked_save_token(_unchecked_token)
        if updates:
            for part_name, payload in updates.items():
                self.set_part(part_name, payload)
        return self._save_to_bytes(
            verify_open_safety=False,
            mark_clean=False,
            _unchecked_token=_UNCHECKED_SAVE_TOKEN,
        )

    def _save_to_bytes(
        self,
        *,
        verify_open_safety: bool,
        mark_clean: bool,
        _unchecked_token: object | None = None,
    ) -> bytes:
        if not verify_open_safety:
            _require_unchecked_save_token(_unchecked_token)
        buffer: io.BytesIO = (
            _UncheckedSaveBuffer() if not verify_open_safety else io.BytesIO()
        )
        self._save_to_zip(
            buffer,
            verify_open_safety=verify_open_safety,
            mark_clean=mark_clean,
            _unchecked_token=_unchecked_token,
        )
        return buffer.getvalue()

    def _save_to_zip(
        self,
        pkg_file: str | Path | BinaryIO,
        *,
        verify_open_safety: bool,
        mark_clean: bool = True,
        _unchecked_token: object | None = None,
    ) -> None:
        if not verify_open_safety:
            _require_unchecked_save_token(_unchecked_token)
            _require_unchecked_save_buffer(pkg_file)
        self._refuse_duplicate_entry_names()
        self._files[self.MIMETYPE_PATH] = self._mimetype.encode("utf-8")
        version_was_dirty = self._version.dirty
        if self._version.dirty:
            self._files[self.VERSION_PATH] = self._version.to_bytes()
        self._normalize_named_style_references_for_safety()
        self._validate_structure()

        payload = self._assemble_archive()
        # The integrity test inflates every member; the checks that follow
        # read those same members instead of inflating them again.
        with sharing_archive_reads():
            register_written_archive(payload)
            with open_archive(payload) as zf_check:
                bad = zf_check.testzip()
                if bad is not None:
                    raise HwpxPackageError(
                        f"ZIP integrity check failed for entry '{bad}'"
                    )
                self._check_written_entries(zf_check)
            if verify_open_safety:
                report = self._verify_editor_open_safe_archive(payload)
                # Remember which exact bytes passed, so the document-level
                # check of the same save need not run the validation again.
                verified = report is not None and report.ok
                self._verified_archive_digest = hashlib.sha256(payload).digest() if verified else None
                self._verified_archive_report = report if verified else None

        if isinstance(pkg_file, (str, Path)):
            # Atomic write: write to a temp file first, then rename.
            target = Path(pkg_file)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(target.parent), suffix=".hwpx.tmp"
            )
            try:
                with os.fdopen(fd, "wb") as tmp_fh:
                    tmp_fh.write(payload)
                os.replace(tmp_path, str(target))
            except BaseException:
                # Clean up the temp file on any error.
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        else:
            _write_stream_or_rollback(pkg_file, payload)
        if mark_clean and version_was_dirty:
            self._version.mark_clean()

    def _refuse_duplicate_entry_names(self) -> None:
        """A package opened from an archive holding one name twice is refused at save, before anything is
        written (:func:`refuse_duplicate_entry_names`): the package keeps one payload per name, so a save
        would drop the other one without a word. Opening it stays allowed -- reading, extracting and
        converting such a file lose nothing."""

        refuse_duplicate_entry_names(self._duplicate_entry_names)

    def _assemble_archive(self) -> bytes:
        """The archive this save writes.

        Every entry is first written with ``zipfile`` from its content. Then, for a package opened from an
        archive, each entry whose content and ZIP metadata are what the source had takes the source's local
        record instead -- the compressed bytes, flags, extra field and data descriptor as they were -- so an
        untouched part keeps its bytes whatever deflate this Python has, and a save that changed nothing
        writes the source file again. A changed or new entry keeps the freshly compressed record. An
        archive whose records cannot be moved one by one (:class:`ZipRecordsUnsupported`) is written as
        ``zipfile`` wrote it, and :attr:`_zip_records_outcome` says why."""

        source = self._source_archive
        self._expected_entry_order: list[str] | None = None
        buffer = io.BytesIO()
        with ZipFile(buffer, "w") as zf:
            self._write_archive_from_save(zf)
            if source is not None:
                # The archive comment is the source's, also when its records cannot be kept one by one.
                zf.comment = source.comment()
        built = buffer.getvalue()
        self._last_built_archive = None
        from .zip_records import ZipRecordsUnsupported, assemble, read_records

        if source is None:
            self._zip_records_outcome = ZipRecordsOutcome.no_source()
            return built
        try:
            source_records = source.records()
            built_records = read_records(built)
        except ZipRecordsUnsupported as exc:
            self._zip_records_outcome = ZipRecordsOutcome(copied=frozenset(), rewritten_reason=exc.reason)
            return self._keep_source_layout(built, source)
        records: list[tuple[bytes, bytes]] = []
        copied: set[str] = set()
        for entry in built_records.entries:
            original = source_records.by_name.get(entry.filename)
            directory = entry.filename in self._zip_directories and entry.filename not in self._files
            # mimetype's record is kept whenever its content is: the source's place and compression for it
            # (not first, or deflated) are what the file says, and making it standard is hwpx-repair's job.
            mimetype_kept = (
                entry.filename == self.MIMETYPE_PATH
                and source.contents.get(self.MIMETYPE_PATH) == self._files.get(self.MIMETYPE_PATH)
            )
            if original is not None and (directory or mimetype_kept or self._entry_unchanged(entry.filename, source)):
                records.append((source_records.local_record(original), original.raw))
                copied.add(entry.filename)
            else:
                records.append((built_records.local_record(entry), entry.raw))
        # The records lie where the source had them (its physical order, which may differ from the order
        # its central directory lists them in), mimetype included; a new entry goes after them. The central
        # directory lists the source's entries in the source's order, then the new ones.
        names = [entry.filename for entry in built_records.entries]
        central_rank = {entry.filename: rank for rank, entry in enumerate(source_records.entries)}

        def place(index: int) -> tuple[int, int]:
            original = source_records.by_name.get(names[index])
            return (0, original.header_offset) if original is not None else (1, index)

        def listed(index: int) -> tuple[int, int]:
            rank = central_rank.get(names[index])
            return (0, rank) if rank is not None else (1, index)

        local_order = sorted(range(len(records)), key=place)
        position = {index: slot for slot, index in enumerate(local_order)}
        central = sorted(range(len(records)), key=listed)
        self._expected_entry_order = [names[index] for index in central]
        try:
            written = assemble(
                [records[index] for index in local_order],
                source_records.eocd,
                central_order=[position[index] for index in central],
            )
        except ZipRecordsUnsupported as exc:
            self._zip_records_outcome = ZipRecordsOutcome(copied=frozenset(), rewritten_reason=exc.reason)
            return self._keep_source_layout(built, source)
        self._zip_records_outcome = ZipRecordsOutcome(copied=frozenset(copied), rewritten_reason=None)
        self._last_built_archive = _SourceArchive(
            written,
            dict(self._files),
            {
                name: self._zip_info_for_write(
                    name, ZIP_STORED if name == self.MIMETYPE_PATH else ZIP_DEFLATED
                )
                for name in self._files
            },
        )
        return written

    @staticmethod
    def _keep_source_layout(built: bytes, source: "_SourceArchive") -> bytes:
        """*built* (every entry written again, in the source's central order) with its records lying where
        the source had them, for a source whose records could not be kept (ZIP64, a prefix, ...): a save
        that cannot keep the bytes still keeps what the file says -- both entry orders, ``mimetype``'s place
        and compression, the archive comment. *built* as it is when its records cannot be moved."""

        from .zip_records import ZipRecordsUnsupported, lay_out_records

        try:
            with ZipFile(io.BytesIO(source.data)) as archive:
                infos = sorted(archive.infolist(), key=lambda info: info.header_offset)
        except (BadZipFile, OSError, ValueError):
            return built
        try:
            return lay_out_records(built, [info.filename for info in infos])
        except ZipRecordsUnsupported:
            return built

    def _adopt_last_archive(self) -> None:
        """After a clean save, the archive it wrote is what the next save keeps records from (the document
        now stands for that file). A package with no source stays without one."""

        if self._source_archive is not None and self._last_built_archive is not None:
            self._source_archive = self._last_built_archive
        self._last_built_archive = None

    def _entry_unchanged(self, name: str, source: "_SourceArchive") -> bool:
        """True only when *name*'s content is byte for byte what the source held and the ZIP metadata this
        save asks for is the source's own -- then the source's record is that entry. Anything else, or
        anything uncertain, is written anew."""

        if name not in source.contents or name not in source.infos:
            return False
        if self._files.get(name) != source.contents[name]:
            return False
        compress_type = ZIP_STORED if name == self.MIMETYPE_PATH else ZIP_DEFLATED
        wanted = self._zip_info_for_write(name, compress_type)
        original = source.infos[name]
        return all(
            getattr(wanted, field_name) == getattr(original, field_name)
            for field_name in _RECORD_FIELDS
        )

    def _check_written_entries(self, archive: ZipFile) -> None:
        """Refuse the save unless the written archive holds exactly the entries meant, in order, each with
        the content meant -- a copied source record must never stand for content it does not hold."""

        names = [info.filename for info in archive.infolist()]
        expected = self._write_order()
        kept_order = getattr(self, "_expected_entry_order", None)
        if kept_order is not None:  # records kept from the source, in its order
            expected = kept_order
        mismatched = [] if names == expected else ["(entry list)"]
        if not mismatched:
            mismatched = [
                info.filename
                for info in archive.infolist()
                if read_member(archive, info) != self._files.get(info.filename, b"")
            ]
        if mismatched:
            raise HwpxPackageError(
                "the written archive does not hold the content this save meant to write: "
                + ", ".join(mismatched[:5]),
                code="save-archive-content-mismatch",
                context={"entries": mismatched[:20]},
                suggestion=(
                    "nothing was written; report this with the source file -- the save copied a ZIP record "
                    "that does not match the part's content."
                ),
            )

    @classmethod
    def _verify_editor_open_safe_archive(
        cls, source: str | Path | bytes
    ) -> "EditorOpenSafetyReport":
        from ..tools.package_validator import validate_editor_open_safety

        report = validate_editor_open_safety(source)
        if not report.ok:
            raise HwpxPackageError(
                "Generated HWPX package failed open-safety validation: "
                + report.summary,
                code="open-safety-failed",
                context={"summary": report.summary},
                suggestion=(
                    "The serialized package would not reopen in an HWPX editor; "
                    "inspect validate_editor_open_safety(...) for the failing checks."
                ),
            )
        return report

    def _write_archive_from_save(self, zf: ZipFile) -> None:
        self._archive_write_depth += 1
        try:
            self._write_archive(zf)
        finally:
            self._archive_write_depth -= 1

    def _write_archive(self, zf: ZipFile) -> None:
        if self._archive_write_depth <= 0:
            raise HwpxPackageError(
                "raw HWPX archive writing is an internal save path; use "
                "HwpxPackage.save() so editor-open safety validation runs"
            )
        for name in self._write_order():
            if name == self.MIMETYPE_PATH:
                self._write_mimetype(zf)
            elif name not in self._files:
                zf.writestr(self._directory_info(name), b"")
            else:
                self._write_zip_entry(zf, name, self._files[name], ZIP_DEFLATED)

    def _write_order(self) -> list[str]:
        """The entries a save writes, in order: ``mimetype`` where the source archive listed it (first for a
        package not read from one), the other entries it read in its order, then new parts by name."""

        ordered_names = self._ordered_entry_names()
        new_names = sorted(
            name for name in self._files if name != self.MIMETYPE_PATH and name not in ordered_names
        )
        if self._source_archive is None:
            listed = [self.MIMETYPE_PATH, *ordered_names]
        else:
            listed = [name for name in self._zip_order if name == self.MIMETYPE_PATH or name in ordered_names]
            if self.MIMETYPE_PATH not in listed:
                listed.insert(0, self.MIMETYPE_PATH)
        # One name listed twice (refused before a save gets here) must not be written twice.
        return [*dict.fromkeys(listed), *new_names]

    def _ordered_entry_names(self) -> list[str]:
        """The entries after ``mimetype`` in the order they were read: parts the package still holds and the
        archive's directory entries."""

        return [
            name
            for name in self._zip_order
            if name != self.MIMETYPE_PATH and (name in self._files or name in self._zip_directories)
        ]

    def _directory_info(self, name: str) -> ZipInfo:
        """A fresh ZipInfo for directory entry *name* with what the source's entry said (``writestr``
        changes the info it is given, so the source's own is not passed)."""

        original = self._zip_directories[name]
        info = ZipInfo(name, original.date_time)
        for field_name in ("compress_type", "comment", "extra", "create_system", "create_version",
                           "extract_version", "flag_bits", "volume", "internal_attr", "external_attr"):
            setattr(info, field_name, getattr(original, field_name))
        return info

    def _zip_info_for_write(self, path: str, compress_type: int) -> ZipInfo:
        original = self._zip_infos.get(path)
        if original is None:
            info = ZipInfo(path)
            info.compress_type = compress_type
            return info

        info = ZipInfo(path, original.date_time)
        # mimetype keeps the compression it was read with while its content is what was read (a source
        # that deflated it says so, and making it standard is hwpx-repair's job); a new one is stored.
        info.compress_type = (
            compress_type
            if path == self.MIMETYPE_PATH and not self._mimetype_as_read()
            else original.compress_type
        )
        info.comment = original.comment
        info.extra = original.extra
        info.create_system = original.create_system
        info.create_version = original.create_version
        info.extract_version = original.extract_version
        info.flag_bits = original.flag_bits
        info.volume = original.volume
        info.internal_attr = original.internal_attr
        info.external_attr = original.external_attr
        return info

    def _mimetype_as_read(self) -> bool:
        source = self._source_archive
        return source is not None and source.contents.get(self.MIMETYPE_PATH) == self._files.get(
            self.MIMETYPE_PATH
        )

    def _write_zip_entry(
        self,
        zf: ZipFile,
        path: str,
        payload: bytes,
        compress_type: int,
    ) -> None:
        if self._archive_write_depth <= 0:
            raise HwpxPackageError(
                "raw HWPX ZIP entry writing is an internal save path; use "
                "HwpxPackage.save() so editor-open safety validation runs"
            )
        info = self._zip_info_for_write(path, compress_type)
        zf.writestr(info, payload)

    def _write_mimetype(self, zf: ZipFile) -> None:
        self._write_zip_entry(
            zf,
            self.MIMETYPE_PATH,
            self._files[self.MIMETYPE_PATH],
            ZIP_STORED,
        )
