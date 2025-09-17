from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional

from lxml import etree

from .common import GenericElement, parse_generic_element
from .utils import local_name, parse_bool, parse_int, text_or_none


@dataclass(slots=True)
class BeginNum:
    page: int
    footnote: int
    endnote: int
    pic: int
    tbl: int
    equation: int


@dataclass(slots=True)
class LinkInfo:
    path: str
    page_inherit: bool
    footnote_inherit: bool


@dataclass(slots=True)
class LicenseMark:
    type: int
    flag: int
    lang: Optional[int]


@dataclass(slots=True)
class DocOption:
    link_info: LinkInfo
    license_mark: Optional[LicenseMark] = None


@dataclass(slots=True)
class KeyDerivation:
    algorithm: Optional[str]
    size: Optional[int]
    count: Optional[int]
    salt: Optional[bytes]


@dataclass(slots=True)
class KeyEncryption:
    derivation_key: KeyDerivation
    hash_value: bytes


@dataclass(slots=True)
class TrackChangeConfig:
    flags: Optional[int]
    encryption: Optional[KeyEncryption] = None


@dataclass(slots=True)
class FontSubstitution:
    face: str
    type: str
    is_embedded: bool
    binary_item_id_ref: Optional[str]


@dataclass(slots=True)
class FontTypeInfo:
    attributes: Dict[str, str]


@dataclass(slots=True)
class Font:
    id: Optional[int]
    face: str
    type: Optional[str]
    is_embedded: bool
    binary_item_id_ref: Optional[str]
    substitution: Optional[FontSubstitution] = None
    type_info: Optional[FontTypeInfo] = None
    other_children: Dict[str, List[GenericElement]] = field(default_factory=dict)


@dataclass(slots=True)
class FontFace:
    lang: Optional[str]
    font_cnt: Optional[int]
    fonts: List[Font]
    attributes: Dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class FontFaceList:
    item_cnt: Optional[int]
    fontfaces: List[FontFace]


@dataclass(slots=True)
class BorderFillList:
    item_cnt: Optional[int]
    fills: List[GenericElement]


@dataclass(slots=True)
class TabProperties:
    item_cnt: Optional[int]
    tabs: List[GenericElement]


@dataclass(slots=True)
class NumberingList:
    item_cnt: Optional[int]
    numberings: List[GenericElement]


@dataclass(slots=True)
class CharProperty:
    id: Optional[int]
    attributes: Dict[str, str]
    child_attributes: Dict[str, Dict[str, str]] = field(default_factory=dict)
    child_elements: Dict[str, List[GenericElement]] = field(default_factory=dict)


@dataclass(slots=True)
class CharPropertyList:
    item_cnt: Optional[int]
    properties: List[CharProperty]


@dataclass(slots=True)
class ForbiddenWordList:
    item_cnt: Optional[int]
    words: List[str]


@dataclass(slots=True)
class MemoShape:
    id: Optional[int]
    width: Optional[int]
    line_width: Optional[str]
    line_type: Optional[str]
    line_color: Optional[str]
    fill_color: Optional[str]
    active_color: Optional[str]
    memo_type: Optional[str]
    attributes: Dict[str, str] = field(default_factory=dict)

    def matches_id(self, memo_shape_id_ref: int | str | None) -> bool:
        if memo_shape_id_ref is None:
            return False

        if isinstance(memo_shape_id_ref, str):
            candidate = memo_shape_id_ref.strip()
        else:
            candidate = str(memo_shape_id_ref)

        if not candidate:
            return False

        raw_id = self.attributes.get("id")
        if raw_id is not None and candidate == raw_id:
            return True

        if self.id is None:
            return False

        try:
            return int(candidate) == self.id
        except (TypeError, ValueError):  # pragma: no cover - defensive branch
            return False


@dataclass(slots=True)
class MemoProperties:
    item_cnt: Optional[int]
    memo_shapes: List[MemoShape]
    attributes: Dict[str, str] = field(default_factory=dict)

    def shape_by_id(self, memo_shape_id_ref: int | str | None) -> Optional[MemoShape]:
        for shape in self.memo_shapes:
            if shape.matches_id(memo_shape_id_ref):
                return shape
        return None

    def as_dict(self) -> Dict[str, MemoShape]:
        mapping: Dict[str, MemoShape] = {}
        for shape in self.memo_shapes:
            raw_id = shape.attributes.get("id")
            keys: List[str] = []
            if raw_id:
                keys.append(raw_id)
                try:
                    normalized = str(int(raw_id))
                except ValueError:
                    normalized = None
                if normalized and normalized not in keys:
                    keys.append(normalized)
            elif shape.id is not None:
                keys.append(str(shape.id))

            for key in keys:
                if key not in mapping:
                    mapping[key] = shape
        return mapping


@dataclass(slots=True)
class RefList:
    fontfaces: Optional[FontFaceList] = None
    border_fills: Optional[BorderFillList] = None
    char_properties: Optional[CharPropertyList] = None
    tab_properties: Optional[TabProperties] = None
    numberings: Optional[NumberingList] = None
    memo_properties: Optional[MemoProperties] = None
    other_collections: Dict[str, List[GenericElement]] = field(default_factory=dict)


@dataclass(slots=True)
class Header:
    version: str
    sec_cnt: int
    begin_num: Optional[BeginNum] = None
    ref_list: Optional[RefList] = None
    forbidden_word_list: Optional[ForbiddenWordList] = None
    compatible_document: Optional[GenericElement] = None
    doc_option: Optional[DocOption] = None
    meta_tag: Optional[str] = None
    track_change_config: Optional[TrackChangeConfig] = None
    other_elements: Dict[str, List[GenericElement]] = field(default_factory=dict)

    def memo_shape(self, memo_shape_id_ref: int | str | None) -> Optional[MemoShape]:
        if self.ref_list is None or self.ref_list.memo_properties is None:
            return None
        return self.ref_list.memo_properties.shape_by_id(memo_shape_id_ref)


def parse_begin_num(node: etree._Element) -> BeginNum:
    return BeginNum(
        page=parse_int(node.get("page"), allow_none=False),
        footnote=parse_int(node.get("footnote"), allow_none=False),
        endnote=parse_int(node.get("endnote"), allow_none=False),
        pic=parse_int(node.get("pic"), allow_none=False),
        tbl=parse_int(node.get("tbl"), allow_none=False),
        equation=parse_int(node.get("equation"), allow_none=False),
    )


def parse_link_info(node: etree._Element) -> LinkInfo:
    return LinkInfo(
        path=node.get("path", ""),
        page_inherit=parse_bool(node.get("pageInherit"), default=False) or False,
        footnote_inherit=parse_bool(node.get("footnoteInherit"), default=False) or False,
    )


def parse_license_mark(node: etree._Element) -> LicenseMark:
    return LicenseMark(
        type=parse_int(node.get("type"), allow_none=False),
        flag=parse_int(node.get("flag"), allow_none=False),
        lang=parse_int(node.get("lang")),
    )


def parse_doc_option(node: etree._Element) -> DocOption:
    link_info: Optional[LinkInfo] = None
    license_mark: Optional[LicenseMark] = None

    for child in node:
        name = local_name(child)
        if name == "linkinfo":
            link_info = parse_link_info(child)
        elif name == "licensemark":
            license_mark = parse_license_mark(child)

    if link_info is None:
        raise ValueError("docOption element is missing required linkinfo child")

    return DocOption(link_info=link_info, license_mark=license_mark)


def _decode_base64(value: Optional[str]) -> Optional[bytes]:
    if not value:
        return None
    try:
        return base64.b64decode(value)
    except (ValueError, binascii.Error) as exc:  # pragma: no cover - defensive branch
        raise ValueError("Invalid base64 value") from exc


def parse_key_encryption(node: etree._Element) -> Optional[KeyEncryption]:
    derivation_node: Optional[etree._Element] = None
    hash_node: Optional[etree._Element] = None
    for child in node:
        name = local_name(child)
        if name == "derivationKey":
            derivation_node = child
        elif name == "hash":
            hash_node = child

    if derivation_node is None or hash_node is None:
        return None

    derivation = KeyDerivation(
        algorithm=derivation_node.get("algorithm"),
        size=parse_int(derivation_node.get("size")),
        count=parse_int(derivation_node.get("count")),
        salt=_decode_base64(derivation_node.get("salt")),
    )

    hash_text = text_or_none(hash_node) or ""
    hash_bytes = _decode_base64(hash_text) or b""
    return KeyEncryption(derivation_key=derivation, hash_value=hash_bytes)


def parse_track_change_config(node: etree._Element) -> TrackChangeConfig:
    encryption: Optional[KeyEncryption] = None
    for child in node:
        if local_name(child) == "trackChangeEncrpytion":
            encryption = parse_key_encryption(child)
            break
    return TrackChangeConfig(flags=parse_int(node.get("flags")), encryption=encryption)


def parse_font_substitution(node: etree._Element) -> FontSubstitution:
    return FontSubstitution(
        face=node.get("face", ""),
        type=node.get("type", ""),
        is_embedded=parse_bool(node.get("isEmbedded"), default=False) or False,
        binary_item_id_ref=node.get("binaryItemIDRef"),
    )


def parse_font_type_info(node: etree._Element) -> FontTypeInfo:
    return FontTypeInfo(attributes={key: value for key, value in node.attrib.items()})


def parse_font(node: etree._Element) -> Font:
    substitution: Optional[FontSubstitution] = None
    type_info: Optional[FontTypeInfo] = None
    other_children: Dict[str, List[GenericElement]] = {}

    for child in node:
        name = local_name(child)
        if name == "substFont":
            substitution = parse_font_substitution(child)
        elif name == "typeInfo":
            type_info = parse_font_type_info(child)
        else:
            other_children.setdefault(name, []).append(parse_generic_element(child))

    return Font(
        id=parse_int(node.get("id")),
        face=node.get("face", ""),
        type=node.get("type"),
        is_embedded=parse_bool(node.get("isEmbedded"), default=False) or False,
        binary_item_id_ref=node.get("binaryItemIDRef"),
        substitution=substitution,
        type_info=type_info,
        other_children=other_children,
    )


def parse_font_face(node: etree._Element) -> FontFace:
    fonts = [parse_font(child) for child in node if local_name(child) == "font"]
    attributes = {key: value for key, value in node.attrib.items()}
    return FontFace(
        lang=node.get("lang"),
        font_cnt=parse_int(node.get("fontCnt")),
        fonts=fonts,
        attributes=attributes,
    )


def parse_font_faces(node: etree._Element) -> FontFaceList:
    fontfaces = [parse_font_face(child) for child in node if local_name(child) == "fontface"]
    return FontFaceList(item_cnt=parse_int(node.get("itemCnt")), fontfaces=fontfaces)


def parse_border_fills(node: etree._Element) -> BorderFillList:
    fills = [parse_generic_element(child) for child in node if local_name(child) == "borderFill"]
    return BorderFillList(item_cnt=parse_int(node.get("itemCnt")), fills=fills)


def parse_char_property(node: etree._Element) -> CharProperty:
    child_attributes: Dict[str, Dict[str, str]] = {}
    child_elements: Dict[str, List[GenericElement]] = {}
    for child in node:
        if len(child) == 0 and (child.text is None or not child.text.strip()):
            child_attributes[local_name(child)] = {
                key: value for key, value in child.attrib.items()
            }
        else:
            child_elements.setdefault(local_name(child), []).append(parse_generic_element(child))

    return CharProperty(
        id=parse_int(node.get("id")),
        attributes={key: value for key, value in node.attrib.items() if key != "id"},
        child_attributes=child_attributes,
        child_elements=child_elements,
    )


def parse_char_properties(node: etree._Element) -> CharPropertyList:
    properties = [
        parse_char_property(child) for child in node if local_name(child) == "charPr"
    ]
    return CharPropertyList(item_cnt=parse_int(node.get("itemCnt")), properties=properties)


def parse_tab_properties(node: etree._Element) -> TabProperties:
    tabs = [parse_generic_element(child) for child in node if local_name(child) == "tabPr"]
    return TabProperties(item_cnt=parse_int(node.get("itemCnt")), tabs=tabs)


def parse_numberings(node: etree._Element) -> NumberingList:
    numberings = [
        parse_generic_element(child) for child in node if local_name(child) == "numbering"
    ]
    return NumberingList(item_cnt=parse_int(node.get("itemCnt")), numberings=numberings)


def parse_forbidden_word_list(node: etree._Element) -> ForbiddenWordList:
    words = [text_or_none(child) or "" for child in node if local_name(child) == "forbiddenWord"]
    return ForbiddenWordList(item_cnt=parse_int(node.get("itemCnt")), words=words)


def memo_shape_from_attributes(attrs: Mapping[str, str]) -> MemoShape:
    return MemoShape(
        id=parse_int(attrs.get("id")),
        width=parse_int(attrs.get("width")),
        line_width=attrs.get("lineWidth"),
        line_type=attrs.get("lineType"),
        line_color=attrs.get("lineColor"),
        fill_color=attrs.get("fillColor"),
        active_color=attrs.get("activeColor"),
        memo_type=attrs.get("memoType"),
        attributes=dict(attrs),
    )


def parse_memo_shape(node: etree._Element) -> MemoShape:
    return memo_shape_from_attributes(node.attrib)


def parse_memo_properties(node: etree._Element) -> MemoProperties:
    memo_shapes = [
        parse_memo_shape(child) for child in node if local_name(child) == "memoPr"
    ]
    attributes = {key: value for key, value in node.attrib.items() if key != "itemCnt"}
    return MemoProperties(
        item_cnt=parse_int(node.get("itemCnt")),
        memo_shapes=memo_shapes,
        attributes=attributes,
    )


def parse_ref_list(node: etree._Element) -> RefList:
    ref_list = RefList()
    for child in node:
        name = local_name(child)
        if name == "fontfaces":
            ref_list.fontfaces = parse_font_faces(child)
        elif name == "borderFills":
            ref_list.border_fills = parse_border_fills(child)
        elif name == "charProperties":
            ref_list.char_properties = parse_char_properties(child)
        elif name == "tabProperties":
            ref_list.tab_properties = parse_tab_properties(child)
        elif name == "numberings":
            ref_list.numberings = parse_numberings(child)
        elif name == "memoProperties":
            ref_list.memo_properties = parse_memo_properties(child)
        else:
            ref_list.other_collections.setdefault(name, []).append(parse_generic_element(child))
    return ref_list


def parse_header_element(node: etree._Element) -> Header:
    version = node.get("version")
    if version is None:
        raise ValueError("Header element is missing required version attribute")
    sec_cnt = parse_int(node.get("secCnt"), allow_none=False)

    header = Header(version=version, sec_cnt=sec_cnt)

    for child in node:
        name = local_name(child)
        if name == "beginNum":
            header.begin_num = parse_begin_num(child)
        elif name == "refList":
            header.ref_list = parse_ref_list(child)
        elif name == "forbiddenWordList":
            header.forbidden_word_list = parse_forbidden_word_list(child)
        elif name == "compatibleDocument":
            header.compatible_document = parse_generic_element(child)
        elif name == "docOption":
            header.doc_option = parse_doc_option(child)
        elif name == "metaTag":
            header.meta_tag = text_or_none(child)
        elif name == "trackchangeConfig":
            header.track_change_config = parse_track_change_config(child)
        else:
            header.other_elements.setdefault(name, []).append(parse_generic_element(child))

    return header


__all__ = [
    "BeginNum",
    "BorderFillList",
    "CharProperty",
    "CharPropertyList",
    "DocOption",
    "Font",
    "FontFace",
    "FontFaceList",
    "FontSubstitution",
    "FontTypeInfo",
    "ForbiddenWordList",
    "Header",
    "KeyDerivation",
    "KeyEncryption",
    "LinkInfo",
    "LicenseMark",
    "MemoProperties",
    "MemoShape",
    "NumberingList",
    "RefList",
    "TabProperties",
    "TrackChangeConfig",
    "memo_shape_from_attributes",
    "parse_begin_num",
    "parse_doc_option",
    "parse_header_element",
    "parse_memo_properties",
    "parse_memo_shape",
    "parse_ref_list",
]
