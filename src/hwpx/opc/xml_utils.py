# SPDX-License-Identifier: Apache-2.0
"""XML 파싱/직렬화를 위한 OPC 공통 유틸리티."""

from __future__ import annotations

from io import BytesIO
import re
from typing import Mapping

import lxml.etree as etree

from .security import HwpxSecurityError, guard_xml_bytes, guard_xml_depth

# Mapping of 2016 HWPML namespace URIs to their 2011 equivalents.
# Documents created with Hancom Office 2016+ may use these newer URIs.
# Normalising to 2011 at parse time lets the rest of the codebase use a
# single set of namespace constants without any lookup changes.
_HWPML_2016_TO_2011: tuple[tuple[bytes, bytes], ...] = (
    (b"http://www.hancom.co.kr/hwpml/2016/paragraph", b"http://www.hancom.co.kr/hwpml/2011/paragraph"),
    (b"http://www.hancom.co.kr/hwpml/2016/head", b"http://www.hancom.co.kr/hwpml/2011/head"),
    (b"http://www.hancom.co.kr/hwpml/2016/section", b"http://www.hancom.co.kr/hwpml/2011/section"),
    (b"http://www.hancom.co.kr/hwpml/2016/core", b"http://www.hancom.co.kr/hwpml/2011/core"),
    (b"http://www.hancom.co.kr/hwpml/2016/master-page", b"http://www.hancom.co.kr/hwpml/2011/master-page"),
    (b"http://www.hancom.co.kr/hwpml/2016/history", b"http://www.hancom.co.kr/hwpml/2011/history"),
    (b"http://www.hancom.co.kr/hwpml/2016/app", b"http://www.hancom.co.kr/hwpml/2011/app"),
)


_XML_MARKUP = re.compile(
    rb"<!--.*?-->|<!\[CDATA\[.*?\]\]>|<\?.*?\?>|<[^!?](?:[^>\"']|\"[^\"]*\"|'[^']*')*>",
    re.S,
)
# The name starts where a name can start (not in the middle of one): without the lookbehind a long run of
# name characters with no "=" after it is tried again from each of its characters.
_XML_ATTRIBUTE = re.compile(rb"(?<![\w:.-])([\w:.-]+)(\s*=\s*)([\"'])(.*?)\3", re.S)
_HWPML_2016_MAPPING: dict[bytes, bytes] = dict(_HWPML_2016_TO_2011)
# Every 2016 URI above contains this; a tag without it has nothing to rewrite.
_HWPML_2016_MARKER = b"hwpml/2016/"


_ROOT_START = re.compile(rb"<[A-Za-z_][\w.:-]*(?:[^>\"']|\"[^\"]*\"|'[^']*')*>")
_XMLNS_DECLARATION = re.compile(rb"""\sxmlns:([\w.-]+)\s*=\s*(["'])(.*?)\2""", re.S)
_HWPML_2011_TO_2016: dict[bytes, tuple[bytes, ...]] = {}
for _new, _old in _HWPML_2016_TO_2011:
    _HWPML_2011_TO_2016.setdefault(_old, ())
    _HWPML_2011_TO_2016[_old] += (_new,)


def _root_start(data: bytes) -> re.Match[bytes] | None:
    """The root element's start tag: the first tag after the XML declaration, comments and PIs."""

    for match in _XML_MARKUP.finditer(data):
        tag = match.group()
        if tag.startswith((b"<?", b"<!")):
            continue
        return _ROOT_START.match(data, match.start())
    return None


#: The XML declaration Hangul writes on every XML part it saves (counted on 1,265 Hancom-saved files: all
#: nine part kinds, no line break after it).
HANCOM_XML_DECLARATION = b'<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
_DECLARATION = re.compile(rb"<\?xml\b[^>]*\?>[ \t\r\n]*")
_ENCODING = re.compile(rb"""\bencoding\s*=\s*["']([^"']+)["']""")
_ATTRIBUTE = re.compile(rb"""\s+([\w:.-]+)\s*=\s*("[^"]*"|'[^']*')""", re.S)
_ANY_XMLNS = re.compile(rb"""\s+xmlns(?::([\w.-]+))?\s*=\s*("[^"]*"|'[^']*')""", re.S)


_STANDALONE_YES = re.compile(rb"""\bstandalone\s*=\s*["']yes["']""")


def _declaration_for(source: bytes | None, *, standalone: bool = False) -> bytes:
    """The declaration (with what follows it up to the root) a part written in place of *source* carries:
    *source*'s own, as it was read; Hangul's for a part the engine makes (no *source*). A *source* without a
    declaration gets none; one that declares another encoding than UTF-8 (the bytes are written in UTF-8)
    gets Hangul's. With *standalone* (a section or header, which Hangul and the package checks want declared
    ``standalone="yes"``), a declaration without it is replaced by Hangul's."""

    if source is None:
        return HANCOM_XML_DECLARATION
    match = _DECLARATION.match(source)
    if match is None:
        return b""
    encoding = _ENCODING.search(match.group())
    if encoding is not None and encoding.group(1).lower().replace(b"_", b"-") not in (b"utf-8", b"utf8"):
        return HANCOM_XML_DECLARATION
    if standalone and not _STANDALONE_YES.search(match.group()):
        return HANCOM_XML_DECLARATION
    return match.group()


def _namespaces(tag: bytes) -> list[tuple[bytes | None, bytes]]:
    return [(m.group(1), m.group(2)[1:-1]) for m in _ANY_XMLNS.finditer(tag)]


def _plain_attributes(tag: bytes) -> list[tuple[bytes, bytes]]:
    return [
        (m.group(1), m.group(2)) for m in _ATTRIBUTE.finditer(tag)
        if m.group(1) != b"xmlns" and not m.group(1).startswith(b"xmlns:")
    ]


def _tag_name(tag: bytes) -> bytes:
    return re.match(rb"<([^\s/>]+)", tag).group(1)  # type: ignore[union-attr]


def keep_source_form(source: bytes | None, written: bytes, *, standalone: bool = False) -> bytes:
    """*written* -- a part the engine serialized, from the tree it parsed from *source* or anew -- in the
    form *source* had: its XML declaration as read (Hangul's for a part the engine makes) and its root's
    namespace declarations as read, in their order.

    Reading moves a 2016 HWPML namespace URI to its 2011 one and a writer may keep only the declarations it
    uses (Hangul's ``content.hpf`` declares 15, ElementTree wrote 1), so the root's declarations come back
    from *source*: every one *source* made, then any the written root makes that *source* did not. A
    declaration is kept as written only where *source* bound its prefix otherwise and the body uses that
    prefix. When the written root's other attributes are *source*'s, its start tag is *source*'s, byte for
    byte. Nothing after the root's start tag changes. *standalone*: see :func:`_declaration_for`."""

    declaration = _declaration_for(source, standalone=standalone)
    head = _DECLARATION.match(written)
    rest = written[head.end():] if head else written.lstrip()
    start = _root_start(rest)
    if start is None or source is None:
        return declaration + rest
    old_start = _root_start(source)
    if old_start is None or _tag_name(old_start.group()) != _tag_name(start.group()):
        return declaration + rest
    tag, body = start.group(), rest[start.end():]
    old_tag = old_start.group()
    written_ns, old_ns = _namespaces(tag), dict(_namespaces(old_tag))
    merged: list[tuple[bytes | None, bytes]] = []
    for prefix, uri in _namespaces(old_tag):
        mine = dict(written_ns).get(prefix)
        used = prefix is not None and (prefix + b":" in body or prefix + b":" in tag[1:].split(b" ")[0])
        if mine is not None and mine != uri and used and uri not in _HWPML_2011_TO_2016.get(mine, ()):
            merged.append((prefix, mine))  # the body means another namespace by this prefix: keep it
        elif mine is not None and mine != uri and used:
            merged.append((prefix, mine))  # 2016 read as 2011, and the body uses it: as written
        else:
            merged.append((prefix, uri))
    for prefix, uri in written_ns:
        if prefix not in old_ns:
            merged.append((prefix, uri))
    if merged == _namespaces(old_tag) and _plain_attributes(tag) == _plain_attributes(old_tag) and (
        tag.endswith(b"/>") == old_tag.endswith(b"/>")
    ):
        return declaration + rest[: start.start()] + old_tag + body
    declarations = b"".join(
        (b" xmlns" if prefix is None else b" xmlns:" + prefix) + b'="' + uri + b'"' for prefix, uri in merged
    )
    attributes = b"".join(b" " + name + b"=" + value for name, value in _plain_attributes(tag))
    close = b"/>" if tag.endswith(b"/>") else b">"
    return declaration + rest[: start.start()] + b"<" + _tag_name(tag) + declarations + attributes + close + body


def _normalize_attribute(match: re.Match[bytes]) -> bytes:
    name, equals, quote, value = match.groups()
    if name == b"xmlns" or name.startswith(b"xmlns:"):
        value = _HWPML_2016_MAPPING.get(value, value)
    return name + equals + quote + value + quote


def _normalize_markup(match: re.Match[bytes]) -> bytes:
    tag = match.group()
    if _HWPML_2016_MARKER not in tag or tag.startswith((b"<!", b"<?")):
        return tag
    return _XML_ATTRIBUTE.sub(_normalize_attribute, tag)


_TAG_STOP = re.compile(rb"[>\"']")


def _markup_end(data: bytes, start: int) -> int:
    """Where the markup opening at ``data[start] == b"<"`` ends (the index after it), or ``-1`` when it
    does not end. A comment, a CDATA section and a processing instruction end at their own closers; a
    tag ends at the first ``>`` outside a quoted value. One forward pass: no position is read twice."""

    if data.startswith(b"<!--", start):
        close = data.find(b"-->", start + 4)
        return -1 if close == -1 else close + 3
    if data.startswith(b"<![CDATA[", start):
        close = data.find(b"]]>", start + 9)
        return -1 if close == -1 else close + 3
    if data.startswith(b"<?", start):
        close = data.find(b"?>", start + 2)
        return -1 if close == -1 else close + 2
    pos = start + 2  # a tag has a character after its "<"
    if pos > len(data):
        return -1
    while True:
        stop = _TAG_STOP.search(data, pos)
        if stop is None:
            return -1
        if stop.group() == b">":
            return stop.end()
        close = data.find(stop.group(), stop.end())
        if close == -1:
            return -1
        pos = close + 1


def _normalize_every_markup(data: bytes) -> bytes:
    """The rewrite for a part with ``<!`` in it, where a ``<`` may stand inside a comment or CDATA:
    every piece of markup in order. Markup that does not end stops the rewrite there (the part is
    not well-formed, and the parser says so); nothing after it is read again, so the time is linear
    in the part's size whatever it holds."""

    out: list[bytes] = []
    pos = 0  # copied up to here
    at = data.find(b"<")
    while at != -1:
        if data.startswith(b"<!", at) and not data.startswith((b"<!--", b"<![CDATA["), at):
            at = data.find(b"<", at + 2)  # a DOCTYPE or a declaration inside one: not rewritten
            continue
        end = _markup_end(data, at)
        if end == -1:
            break
        if not data.startswith((b"<!", b"<?"), at) and data.find(_HWPML_2016_MARKER, at, end) != -1:
            out.append(data[pos:at])
            out.append(_XML_ATTRIBUTE.sub(_normalize_attribute, data[at:end]))
            pos = end
        at = data.find(b"<", end)
    out.append(data[pos:])
    return b"".join(out)


def normalize_hwpml_namespaces(data: bytes) -> bytes:
    """Normalize namespace declarations, preserving ordinary URI-valued data.

    In particular, hp:case/@hp:required-namespace is a feature-selection value,
    not a namespace declaration. Rewriting it can select the wrong switch case.
    Comments, CDATA, processing instructions and quoted non-xmlns values stay
    byte-identical. The parser still uses the canonical 2011 namespace family.

    Only a tag that contains a 2016 URI can change, so those tags are found
    directly from the URI occurrences instead of scanning every tag and
    attribute. When the part has comments, CDATA or a DOCTYPE (``<!``), where a
    ``<`` does not always open a tag, every piece of markup is scanned in order.

    The time is linear in the size of the part for any bytes: a part is read from a
    stranger's file before it is known to be XML at all.
    """
    if _HWPML_2016_MARKER not in data:
        return data
    if b"<!" in data:
        return _normalize_every_markup(data)
    out: list[bytes] = []
    pos = 0  # copied up to here
    floor = 0  # no "<" before here opens a tag that holds a later URI
    hit = data.find(_HWPML_2016_MARKER)
    while hit != -1:
        # Attribute values cannot hold "<", so the last "<" before the URI
        # opens the tag that holds it, if any does.
        start = data.rfind(b"<", floor, hit)
        floor = hit
        if start == -1 or data.startswith(b"<?", start):
            # the URI sits in text or in a processing instruction: left as is
            hit = data.find(_HWPML_2016_MARKER, hit + len(_HWPML_2016_MARKER))
            continue
        end = _markup_end(data, start)
        if end == -1:
            # The last "<" before the URI opens nothing that ends: it may stand inside a processing
            # instruction (``<?rule test="a < b" ...?>``), which only reading the markup in order
            # tells apart. That reading is linear too.
            return _normalize_every_markup(data)
        if end <= hit:
            hit = data.find(_HWPML_2016_MARKER, hit + len(_HWPML_2016_MARKER))
            continue
        out.append(data[pos:start])
        out.append(_XML_ATTRIBUTE.sub(_normalize_attribute, data[start:end]))
        pos = floor = end
        hit = data.find(_HWPML_2016_MARKER, pos)
    out.append(data[pos:])
    return b"".join(out)


def parse_xml(data: bytes) -> etree._Element:
    """바이트 XML 문서를 파싱해 루트 요소를 반환한다.

    2016 HWPML 네임스페이스는 파싱 전에 2011 버전으로 자동 정규화된다.
    """

    guard_xml_bytes(data)
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    root = etree.fromstring(normalize_hwpml_namespaces(data), parser=parser)
    if root.getroottree().docinfo.doctype:  # one the byte check could not read (UTF-16)
        raise HwpxSecurityError("XML payload contains a disallowed DTD/entity declaration")
    guard_xml_depth(root)
    return root


def parse_untrusted_xml(data: bytes, *, part_name: str = "XML payload") -> etree._Element:
    """Parse the bytes of a package part as they are, without normalising them.

    The payload is guarded, parsed without resolving entities or reaching the
    network, and refused when it carries a document type declaration anywhere.
    Raises :class:`~hwpx.opc.security.HwpxSecurityError` or
    ``lxml.etree.XMLSyntaxError``.
    """

    guard_xml_bytes(data, part_name=part_name)
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    root = etree.fromstring(data, parser=parser)
    if root.getroottree().docinfo.doctype:
        raise HwpxSecurityError(f"{part_name} contains a disallowed DTD/entity declaration")
    guard_xml_depth(root, part_name=part_name)
    return root


def parse_xml_with_namespaces(data: bytes) -> tuple[etree._Element, Mapping[str, str]]:
    """루트 요소와 네임스페이스 매핑(prefix -> uri)을 함께 반환한다."""

    root = parse_xml(data)
    namespaces = {"" if prefix is None else prefix: uri for prefix, uri in root.nsmap.items() if uri}
    return root, namespaces


def iter_declared_namespaces(data: bytes) -> Mapping[str, str]:
    """XML 선언 순서를 보존한 네임스페이스 매핑을 추출한다.

    2016 HWPML 네임스페이스는 2011 버전으로 정규화된다.
    """

    guard_xml_bytes(data)
    normalized = normalize_hwpml_namespaces(data)
    namespaces: dict[str, str] = {}
    for _, elem in etree.iterparse(
        BytesIO(normalized),
        events=("start-ns",),
        resolve_entities=False,
        no_network=True,
        huge_tree=False,
    ):
        prefix, uri = elem
        namespaces[prefix or ""] = uri
    return namespaces


def extract_xml_declaration(data: bytes) -> bytes | None:
    """문서 상단의 XML 선언(`<?xml ... ?>`)을 추출한다."""

    stripped = data.lstrip()
    if not stripped.startswith(b"<?xml"):
        return None
    end = stripped.find(b"?>")
    if end == -1:
        return None
    return stripped[: end + 2]


def serialize_xml(element: etree._Element, *, xml_declaration: bool = False) -> bytes:
    """요소를 UTF-8 XML 바이트로 직렬화한다."""

    return etree.tostring(element, encoding="utf-8", xml_declaration=xml_declaration)
