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
class BulletParaHead:
    text: str
    level: Optional[int]
    start: Optional[int]
    align: Optional[str]
    use_inst_width: Optional[bool]
    auto_indent: Optional[bool]
    width_adjust: Optional[int]
    text_offset_type: Optional[str]
    text_offset: Optional[int]
    attributes: Dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Bullet:
    id: Optional[int]
    raw_id: Optional[str]
    char: str
    checked_char: Optional[str]
    use_image: bool
    para_head: BulletParaHead
    image: Optional[GenericElement] = None
    attributes: Dict[str, str] = field(default_factory=dict)
    other_children: Dict[str, List[GenericElement]] = field(default_factory=dict)

    def matches_id(self, bullet_id_ref: int | str | None) -> bool:
        if bullet_id_ref is None:
            return False

        if isinstance(bullet_id_ref, str):
            candidate = bullet_id_ref.strip()
        else:
            candidate = str(bullet_id_ref)

        if not candidate:
            return False

        if self.raw_id and candidate == self.raw_id:
            return True

        if self.id is None:
            return False

        try:
            return int(candidate) == self.id
        except (TypeError, ValueError):  # pragma: no cover - defensive branch
            return False


@dataclass(slots=True)
class BulletList:
    item_cnt: Optional[int]
    bullets: List[Bullet]

    def as_dict(self) -> Dict[str, Bullet]:
        mapping: Dict[str, Bullet] = {}
        for bullet in self.bullets:
            keys: List[str] = []
            if bullet.raw_id:
                keys.append(bullet.raw_id)
                try:
                    normalized = str(int(bullet.raw_id))
                except ValueError:
                    normalized = None
                if normalized and normalized not in keys:
                    keys.append(normalized)
            elif bullet.id is not None:
                keys.append(str(bullet.id))

            for key in keys:
                if key not in mapping:
                    mapping[key] = bullet
        return mapping

    def bullet_by_id(self, bullet_id_ref: int | str | None) -> Optional[Bullet]:
        for bullet in self.bullets:
            if bullet.matches_id(bullet_id_ref):
                return bullet
        return None


@dataclass(slots=True)
class ParagraphAlignment:
    horizontal: Optional[str]
    vertical: Optional[str]
    attributes: Dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ParagraphHeading:
    type: Optional[str]
    id_ref: Optional[int]
    level: Optional[int]
    attributes: Dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ParagraphBreakSetting:
    break_latin_word: Optional[str]
    break_non_latin_word: Optional[str]
    widow_orphan: Optional[bool]
    keep_with_next: Optional[bool]
    keep_lines: Optional[bool]
    page_break_before: Optional[bool]
    line_wrap: Optional[str]
    attributes: Dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ParagraphMargin:
    intent: Optional[str]
    left: Optional[str]
    right: Optional[str]
    prev: Optional[str]
    next: Optional[str]
    other_children: Dict[str, List[GenericElement]] = field(default_factory=dict)


@dataclass(slots=True)
class ParagraphLineSpacing:
    spacing_type: Optional[str]
    value: Optional[int]
    unit: Optional[str]
    attributes: Dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ParagraphBorder:
    border_fill_id_ref: Optional[int]
    offset_left: Optional[int]
    offset_right: Optional[int]
    offset_top: Optional[int]
    offset_bottom: Optional[int]
    connect: Optional[bool]
    ignore_margin: Optional[bool]
    attributes: Dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ParagraphAutoSpacing:
    e_asian_eng: Optional[bool]
    e_asian_num: Optional[bool]
    attributes: Dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ParagraphProperty:
    id: Optional[int]
    raw_id: Optional[str]
    tab_pr_id_ref: Optional[int]
    condense: Optional[int]
    font_line_height: Optional[bool]
    snap_to_grid: Optional[bool]
    suppress_line_numbers: Optional[bool]
    checked: Optional[bool]
    align: Optional[ParagraphAlignment] = None
    heading: Optional[ParagraphHeading] = None
    break_setting: Optional[ParagraphBreakSetting] = None
    margin: Optional[ParagraphMargin] = None
    line_spacing: Optional[ParagraphLineSpacing] = None
    border: Optional[ParagraphBorder] = None
    auto_spacing: Optional[ParagraphAutoSpacing] = None
    attributes: Dict[str, str] = field(default_factory=dict)
    other_children: Dict[str, List[GenericElement]] = field(default_factory=dict)

    def matches_id(self, para_pr_id_ref: int | str | None) -> bool:
        if para_pr_id_ref is None:
            return False

        if isinstance(para_pr_id_ref, str):
            candidate = para_pr_id_ref.strip()
        else:
            candidate = str(para_pr_id_ref)

        if not candidate:
            return False

        if self.raw_id and candidate == self.raw_id:
            return True

        if self.id is None:
            return False

        try:
            return int(candidate) == self.id
        except (TypeError, ValueError):  # pragma: no cover - defensive branch
            return False


@dataclass(slots=True)
class ParagraphPropertyList:
    item_cnt: Optional[int]
    properties: List[ParagraphProperty]

    def as_dict(self) -> Dict[str, ParagraphProperty]:
        mapping: Dict[str, ParagraphProperty] = {}
        for prop in self.properties:
            keys: List[str] = []
            if prop.raw_id:
                keys.append(prop.raw_id)
                try:
                    normalized = str(int(prop.raw_id))
                except ValueError:
                    normalized = None
                if normalized and normalized not in keys:
                    keys.append(normalized)
            elif prop.id is not None:
                keys.append(str(prop.id))

            for key in keys:
                if key not in mapping:
                    mapping[key] = prop
        return mapping

    def property_by_id(
        self, para_pr_id_ref: int | str | None
    ) -> Optional[ParagraphProperty]:
        for prop in self.properties:
            if prop.matches_id(para_pr_id_ref):
                return prop
        return None


@dataclass(slots=True)
class Style:
    id: Optional[int]
    raw_id: Optional[str]
    type: Optional[str]
    name: Optional[str]
    eng_name: Optional[str]
    para_pr_id_ref: Optional[int]
    char_pr_id_ref: Optional[int]
    next_style_id_ref: Optional[int]
    lang_id: Optional[int]
    lock_form: Optional[bool]
    attributes: Dict[str, str] = field(default_factory=dict)

    def matches_id(self, style_id_ref: int | str | None) -> bool:
        if style_id_ref is None:
            return False

        if isinstance(style_id_ref, str):
            candidate = style_id_ref.strip()
        else:
            candidate = str(style_id_ref)

        if not candidate:
            return False

        if self.raw_id and candidate == self.raw_id:
            return True

        if self.id is None:
            return False

        try:
            return int(candidate) == self.id
        except (TypeError, ValueError):  # pragma: no cover - defensive branch
            return False


@dataclass(slots=True)
class StyleList:
    item_cnt: Optional[int]
    styles: List[Style]

    def as_dict(self) -> Dict[str, Style]:
        mapping: Dict[str, Style] = {}
        for style in self.styles:
            keys: List[str] = []
            if style.raw_id:
                keys.append(style.raw_id)
                try:
                    normalized = str(int(style.raw_id))
                except ValueError:
                    normalized = None
                if normalized and normalized not in keys:
                    keys.append(normalized)
            elif style.id is not None:
                keys.append(str(style.id))

            for key in keys:
                if key not in mapping:
                    mapping[key] = style
        return mapping

    def style_by_id(self, style_id_ref: int | str | None) -> Optional[Style]:
        for style in self.styles:
            if style.matches_id(style_id_ref):
                return style
        return None


@dataclass(slots=True)
class TrackChange:
    id: Optional[int]
    raw_id: Optional[str]
    change_type: Optional[str]
    date: Optional[str]
    author_id: Optional[int]
    char_shape_id: Optional[int]
    para_shape_id: Optional[int]
    hide: Optional[bool]
    attributes: Dict[str, str] = field(default_factory=dict)

    def matches_id(self, change_id_ref: int | str | None) -> bool:
        if change_id_ref is None:
            return False

        if isinstance(change_id_ref, str):
            candidate = change_id_ref.strip()
        else:
            candidate = str(change_id_ref)

        if not candidate:
            return False

        if self.raw_id and candidate == self.raw_id:
            return True

        if self.id is None:
            return False

        try:
            return int(candidate) == self.id
        except (TypeError, ValueError):  # pragma: no cover - defensive branch
            return False


@dataclass(slots=True)
class TrackChangeList:
    item_cnt: Optional[int]
    changes: List[TrackChange]

    def as_dict(self) -> Dict[str, TrackChange]:
        mapping: Dict[str, TrackChange] = {}
        for change in self.changes:
            keys: List[str] = []
            if change.raw_id:
                keys.append(change.raw_id)
                try:
                    normalized = str(int(change.raw_id))
                except ValueError:
                    normalized = None
                if normalized and normalized not in keys:
                    keys.append(normalized)
            elif change.id is not None:
                keys.append(str(change.id))

            for key in keys:
                if key not in mapping:
                    mapping[key] = change
        return mapping

    def change_by_id(self, change_id_ref: int | str | None) -> Optional[TrackChange]:
        for change in self.changes:
            if change.matches_id(change_id_ref):
                return change
        return None


@dataclass(slots=True)
class TrackChangeAuthor:
    id: Optional[int]
    raw_id: Optional[str]
    name: Optional[str]
    mark: Optional[bool]
    color: Optional[str]
    attributes: Dict[str, str] = field(default_factory=dict)

    def matches_id(self, author_id_ref: int | str | None) -> bool:
        if author_id_ref is None:
            return False

        if isinstance(author_id_ref, str):
            candidate = author_id_ref.strip()
        else:
            candidate = str(author_id_ref)

        if not candidate:
            return False

        if self.raw_id and candidate == self.raw_id:
            return True

        if self.id is None:
            return False

        try:
            return int(candidate) == self.id
        except (TypeError, ValueError):  # pragma: no cover - defensive branch
            return False


@dataclass(slots=True)
class TrackChangeAuthorList:
    item_cnt: Optional[int]
    authors: List[TrackChangeAuthor]

    def as_dict(self) -> Dict[str, TrackChangeAuthor]:
        mapping: Dict[str, TrackChangeAuthor] = {}
        for author in self.authors:
            keys: List[str] = []
            if author.raw_id:
                keys.append(author.raw_id)
                try:
                    normalized = str(int(author.raw_id))
                except ValueError:
                    normalized = None
                if normalized and normalized not in keys:
                    keys.append(normalized)
            elif author.id is not None:
                keys.append(str(author.id))

            for key in keys:
                if key not in mapping:
                    mapping[key] = author
        return mapping

    def author_by_id(self, author_id_ref: int | str | None) -> Optional[TrackChangeAuthor]:
        for author in self.authors:
            if author.matches_id(author_id_ref):
                return author
        return None


@dataclass(slots=True)
class RefList:
    fontfaces: Optional[FontFaceList] = None
    border_fills: Optional[BorderFillList] = None
    char_properties: Optional[CharPropertyList] = None
    tab_properties: Optional[TabProperties] = None
    numberings: Optional[NumberingList] = None
    bullets: Optional[BulletList] = None
    para_properties: Optional[ParagraphPropertyList] = None
    styles: Optional[StyleList] = None
    memo_properties: Optional[MemoProperties] = None
    track_changes: Optional[TrackChangeList] = None
    track_change_authors: Optional[TrackChangeAuthorList] = None
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

    def bullet(self, bullet_id_ref: int | str | None) -> Optional[Bullet]:
        if self.ref_list is None or self.ref_list.bullets is None:
            return None
        return self.ref_list.bullets.bullet_by_id(bullet_id_ref)

    def paragraph_property(
        self, para_pr_id_ref: int | str | None
    ) -> Optional[ParagraphProperty]:
        if self.ref_list is None or self.ref_list.para_properties is None:
            return None
        return self.ref_list.para_properties.property_by_id(para_pr_id_ref)

    def style(self, style_id_ref: int | str | None) -> Optional[Style]:
        if self.ref_list is None or self.ref_list.styles is None:
            return None
        return self.ref_list.styles.style_by_id(style_id_ref)

    def track_change(self, change_id_ref: int | str | None) -> Optional[TrackChange]:
        if self.ref_list is None or self.ref_list.track_changes is None:
            return None
        return self.ref_list.track_changes.change_by_id(change_id_ref)

    def track_change_author(
        self, author_id_ref: int | str | None
    ) -> Optional[TrackChangeAuthor]:
        if self.ref_list is None or self.ref_list.track_change_authors is None:
            return None
        return self.ref_list.track_change_authors.author_by_id(author_id_ref)


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


def parse_bullet_para_head(node: etree._Element) -> BulletParaHead:
    return BulletParaHead(
        text=text_or_none(node) or "",
        level=parse_int(node.get("level")),
        start=parse_int(node.get("start")),
        align=node.get("align"),
        use_inst_width=parse_bool(node.get("useInstWidth")),
        auto_indent=parse_bool(node.get("autoIndent")),
        width_adjust=parse_int(node.get("widthAdjust")),
        text_offset_type=node.get("textOffsetType"),
        text_offset=parse_int(node.get("textOffset")),
        attributes={key: value for key, value in node.attrib.items()},
    )


def parse_bullet(node: etree._Element) -> Bullet:
    image: Optional[GenericElement] = None
    para_head: Optional[BulletParaHead] = None
    other_children: Dict[str, List[GenericElement]] = {}

    for child in node:
        name = local_name(child)
        if name == "img":
            image = parse_generic_element(child)
        elif name == "paraHead":
            para_head = parse_bullet_para_head(child)
        else:
            other_children.setdefault(name, []).append(parse_generic_element(child))

    if para_head is None:
        raise ValueError("bullet element missing required paraHead child")

    return Bullet(
        id=parse_int(node.get("id")),
        raw_id=node.get("id"),
        char=node.get("char", ""),
        checked_char=node.get("checkedChar"),
        use_image=parse_bool(node.get("useImage"), default=False) or False,
        para_head=para_head,
        image=image,
        attributes={key: value for key, value in node.attrib.items()},
        other_children=other_children,
    )


def parse_bullets(node: etree._Element) -> BulletList:
    bullets = [parse_bullet(child) for child in node if local_name(child) == "bullet"]
    return BulletList(item_cnt=parse_int(node.get("itemCnt")), bullets=bullets)


def parse_paragraph_alignment(node: etree._Element) -> ParagraphAlignment:
    return ParagraphAlignment(
        horizontal=node.get("horizontal"),
        vertical=node.get("vertical"),
        attributes={key: value for key, value in node.attrib.items()},
    )


def parse_paragraph_heading(node: etree._Element) -> ParagraphHeading:
    return ParagraphHeading(
        type=node.get("type"),
        id_ref=parse_int(node.get("idRef")),
        level=parse_int(node.get("level")),
        attributes={key: value for key, value in node.attrib.items()},
    )


def parse_paragraph_break_setting(node: etree._Element) -> ParagraphBreakSetting:
    return ParagraphBreakSetting(
        break_latin_word=node.get("breakLatinWord"),
        break_non_latin_word=node.get("breakNonLatinWord"),
        widow_orphan=parse_bool(node.get("widowOrphan")),
        keep_with_next=parse_bool(node.get("keepWithNext")),
        keep_lines=parse_bool(node.get("keepLines")),
        page_break_before=parse_bool(node.get("pageBreakBefore")),
        line_wrap=node.get("lineWrap"),
        attributes={key: value for key, value in node.attrib.items()},
    )


def _margin_value(child: etree._Element) -> Optional[str]:
    value = text_or_none(child)
    return value if value is not None else child.text.strip() if child.text else None


def parse_paragraph_margin(node: etree._Element) -> ParagraphMargin:
    values: Dict[str, Optional[str]] = {
        "intent": None,
        "left": None,
        "right": None,
        "prev": None,
        "next": None,
    }
    other_children: Dict[str, List[GenericElement]] = {}

    for child in node:
        name = local_name(child)
        if name in values:
            values[name] = _margin_value(child)
        else:
            other_children.setdefault(name, []).append(parse_generic_element(child))

    return ParagraphMargin(
        intent=values["intent"],
        left=values["left"],
        right=values["right"],
        prev=values["prev"],
        next=values["next"],
        other_children=other_children,
    )


def parse_paragraph_line_spacing(node: etree._Element) -> ParagraphLineSpacing:
    return ParagraphLineSpacing(
        spacing_type=node.get("type"),
        value=parse_int(node.get("value")),
        unit=node.get("unit"),
        attributes={key: value for key, value in node.attrib.items()},
    )


def parse_paragraph_border(node: etree._Element) -> ParagraphBorder:
    return ParagraphBorder(
        border_fill_id_ref=parse_int(node.get("borderFillIDRef")),
        offset_left=parse_int(node.get("offsetLeft")),
        offset_right=parse_int(node.get("offsetRight")),
        offset_top=parse_int(node.get("offsetTop")),
        offset_bottom=parse_int(node.get("offsetBottom")),
        connect=parse_bool(node.get("connect")),
        ignore_margin=parse_bool(node.get("ignoreMargin")),
        attributes={key: value for key, value in node.attrib.items()},
    )


def parse_paragraph_auto_spacing(node: etree._Element) -> ParagraphAutoSpacing:
    return ParagraphAutoSpacing(
        e_asian_eng=parse_bool(node.get("eAsianEng")),
        e_asian_num=parse_bool(node.get("eAsianNum")),
        attributes={key: value for key, value in node.attrib.items()},
    )


def parse_paragraph_property(node: etree._Element) -> ParagraphProperty:
    align: Optional[ParagraphAlignment] = None
    heading: Optional[ParagraphHeading] = None
    break_setting: Optional[ParagraphBreakSetting] = None
    margin: Optional[ParagraphMargin] = None
    line_spacing: Optional[ParagraphLineSpacing] = None
    border: Optional[ParagraphBorder] = None
    auto_spacing: Optional[ParagraphAutoSpacing] = None
    other_children: Dict[str, List[GenericElement]] = {}

    for child in node:
        name = local_name(child)
        if name == "align":
            align = parse_paragraph_alignment(child)
        elif name == "heading":
            heading = parse_paragraph_heading(child)
        elif name == "breakSetting":
            break_setting = parse_paragraph_break_setting(child)
        elif name == "margin":
            margin = parse_paragraph_margin(child)
        elif name == "lineSpacing":
            line_spacing = parse_paragraph_line_spacing(child)
        elif name == "border":
            border = parse_paragraph_border(child)
        elif name == "autoSpacing":
            auto_spacing = parse_paragraph_auto_spacing(child)
        else:
            other_children.setdefault(name, []).append(parse_generic_element(child))

    known_attrs = {
        "id",
        "tabPrIDRef",
        "condense",
        "fontLineHeight",
        "snapToGrid",
        "suppressLineNumbers",
        "checked",
    }

    attributes = {
        key: value for key, value in node.attrib.items() if key not in known_attrs
    }

    return ParagraphProperty(
        id=parse_int(node.get("id")),
        raw_id=node.get("id"),
        tab_pr_id_ref=parse_int(node.get("tabPrIDRef")),
        condense=parse_int(node.get("condense")),
        font_line_height=parse_bool(node.get("fontLineHeight")),
        snap_to_grid=parse_bool(node.get("snapToGrid")),
        suppress_line_numbers=parse_bool(node.get("suppressLineNumbers")),
        checked=parse_bool(node.get("checked")),
        align=align,
        heading=heading,
        break_setting=break_setting,
        margin=margin,
        line_spacing=line_spacing,
        border=border,
        auto_spacing=auto_spacing,
        attributes=attributes,
        other_children=other_children,
    )


def parse_paragraph_properties(node: etree._Element) -> ParagraphPropertyList:
    properties = [
        parse_paragraph_property(child) for child in node if local_name(child) == "paraPr"
    ]
    return ParagraphPropertyList(item_cnt=parse_int(node.get("itemCnt")), properties=properties)


def parse_style(node: etree._Element) -> Style:
    known_attrs = {
        "id",
        "type",
        "name",
        "engName",
        "paraPrIDRef",
        "charPrIDRef",
        "nextStyleIDRef",
        "langID",
        "lockForm",
    }

    attributes = {
        key: value for key, value in node.attrib.items() if key not in known_attrs
    }

    return Style(
        id=parse_int(node.get("id")),
        raw_id=node.get("id"),
        type=node.get("type"),
        name=node.get("name"),
        eng_name=node.get("engName"),
        para_pr_id_ref=parse_int(node.get("paraPrIDRef")),
        char_pr_id_ref=parse_int(node.get("charPrIDRef")),
        next_style_id_ref=parse_int(node.get("nextStyleIDRef")),
        lang_id=parse_int(node.get("langID")),
        lock_form=parse_bool(node.get("lockForm")),
        attributes=attributes,
    )


def parse_styles(node: etree._Element) -> StyleList:
    styles = [parse_style(child) for child in node if local_name(child) == "style"]
    return StyleList(item_cnt=parse_int(node.get("itemCnt")), styles=styles)


def parse_track_change(node: etree._Element) -> TrackChange:
    known_attrs = {
        "id",
        "type",
        "date",
        "authorID",
        "charShapeID",
        "paraShapeID",
        "hide",
    }

    attributes = {
        key: value for key, value in node.attrib.items() if key not in known_attrs
    }

    return TrackChange(
        id=parse_int(node.get("id")),
        raw_id=node.get("id"),
        change_type=node.get("type"),
        date=node.get("date"),
        author_id=parse_int(node.get("authorID")),
        char_shape_id=parse_int(node.get("charShapeID")),
        para_shape_id=parse_int(node.get("paraShapeID")),
        hide=parse_bool(node.get("hide")),
        attributes=attributes,
    )


def parse_track_changes(node: etree._Element) -> TrackChangeList:
    changes = [
        parse_track_change(child) for child in node if local_name(child) == "trackChange"
    ]
    return TrackChangeList(item_cnt=parse_int(node.get("itemCnt")), changes=changes)


def parse_track_change_author(node: etree._Element) -> TrackChangeAuthor:
    known_attrs = {"id", "name", "mark", "color"}
    attributes = {
        key: value for key, value in node.attrib.items() if key not in known_attrs
    }
    return TrackChangeAuthor(
        id=parse_int(node.get("id")),
        raw_id=node.get("id"),
        name=node.get("name"),
        mark=parse_bool(node.get("mark")),
        color=node.get("color"),
        attributes=attributes,
    )


def parse_track_change_authors(node: etree._Element) -> TrackChangeAuthorList:
    authors = [
        parse_track_change_author(child)
        for child in node
        if local_name(child) == "trackChangeAuthor"
    ]
    return TrackChangeAuthorList(
        item_cnt=parse_int(node.get("itemCnt")),
        authors=authors,
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
        elif name == "bullets":
            ref_list.bullets = parse_bullets(child)
        elif name == "paraProperties":
            ref_list.para_properties = parse_paragraph_properties(child)
        elif name == "styles":
            ref_list.styles = parse_styles(child)
        elif name == "memoProperties":
            ref_list.memo_properties = parse_memo_properties(child)
        elif name == "trackChanges":
            ref_list.track_changes = parse_track_changes(child)
        elif name == "trackChangeAuthors":
            ref_list.track_change_authors = parse_track_change_authors(child)
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
    "Bullet",
    "BulletList",
    "BulletParaHead",
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
    "ParagraphAlignment",
    "ParagraphAutoSpacing",
    "ParagraphBreakSetting",
    "ParagraphBorder",
    "ParagraphHeading",
    "ParagraphLineSpacing",
    "ParagraphMargin",
    "ParagraphProperty",
    "ParagraphPropertyList",
    "RefList",
    "Style",
    "StyleList",
    "TabProperties",
    "TrackChange",
    "TrackChangeAuthor",
    "TrackChangeAuthorList",
    "TrackChangeConfig",
    "TrackChangeList",
    "memo_shape_from_attributes",
    "parse_begin_num",
    "parse_bullet",
    "parse_bullet_para_head",
    "parse_bullets",
    "parse_char_property",
    "parse_char_properties",
    "parse_doc_option",
    "parse_forbidden_word_list",
    "parse_header_element",
    "parse_memo_properties",
    "parse_memo_shape",
    "parse_numberings",
    "parse_paragraph_alignment",
    "parse_paragraph_auto_spacing",
    "parse_paragraph_border",
    "parse_paragraph_break_setting",
    "parse_paragraph_line_spacing",
    "parse_paragraph_margin",
    "parse_paragraph_property",
    "parse_paragraph_properties",
    "parse_ref_list",
    "parse_style",
    "parse_styles",
    "parse_tab_properties",
    "parse_track_change",
    "parse_track_change_author",
    "parse_track_change_authors",
    "parse_track_changes",
]
