# SPDX-License-Identifier: Apache-2.0
"""``ensure_numbering``'s full body (6.13 트레인㊻).

``header_part.py``의 owner-file 1600줄 캡에 헤드룸이 없어(㊻ 착지 시
1617줄) 이 메서드 전체를 새 모듈로 뺀다(`section_layout.py`의 "그대로
옮김" 전례와 같은 패턴) — `header_part.py`의 자리는 1줄 위임만 남는다.

세 kind(``"bullet"``/``"number"``/``"outline"``) 중 뒤 둘은 완전히 같은
메커니즘(``hh:numbering``/``hh:paraHead`` 정의를 만들고 각 레벨의 paraPr
id를 돌려준다)을 서로 다른 ``heading_type``(``"NUMBER"``/``"OUTLINE"``)
으로만 참조한다 — ``_numbering_refs_for_kind``가 그 공통 로직 하나로 둘
다 담당한다(중복 제거, 신규 계산 로직 없음).

``"outline"``은 6.13 트레인㊻이 새로 연 kind다: `hh:heading
type="OUTLINE"`이 목록 서식과 **같은** id-space를 쓴다는 사실은 이미
알려져 있었으나(`bind_outline_level`, `_document/headings.py`),
`ensure_numbering` 자신은 `"bullet"`/`"number"`만 받았다 — 개요 번호
*모양*(numFormat/start)을 커스터마이즈할 길이 없었다(`add_heading`/
`apply_paragraph_format(outline_level=)`는 항상 고정 `idRef="0"`만
참조). 실코퍼스 67파일 전수: `hh:heading type="OUTLINE"` 451건 전부
`idRef="0"`뿐이라 커스텀 idRef 조합은 미실측(Create(experimental), v17
배치 대기) — 재사용하는 `hh:numbering`/`hh:paraHead` 구조 자체는 v14의
`authored-listformat`에서 이미 render-verified라 구조적 추측 위험은
없다.

7.0 adds the definition verbs the engine lacked (``doc.styles.add_numbering``,
``ensure_bullet``, ``set_numbering_level``), ``Paragraph.set_numbering``/``set_bullet``
that put one paragraph in a list keeping the rest of its shape, and the defaults
they write, taken from what Hancom saves (:data:`HANCOM_NUMBERING_LEVELS`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping, Sequence

from .namespaces import HH, HP

if TYPE_CHECKING:
    from .document_parts import HwpxOxmlDocument
    from .header_part import HwpxOxmlHeader
    from .paragraph import HwpxOxmlParagraph

__all__ = [
    "HANCOM_NUMBERING_LEVELS",
    "NOTE_NUMBER_FORMATS",
    "NUMBER_FORMATS",
    "NUMBER_FORMAT_ALIASES",
    "add_numbering_definition",
    "check_list_level",
    "ensure_bullet_definition",
    "ensure_numbering_levels",
    "ensure_numbering_refs",
    "number_format",
    "set_numbering_level",
    "set_paragraph_list",
]

_DEFAULT_BULLET_CHARS = ("-", "○", "□", "•")

#: The number formats of list and outline heads and of page numbers (``hc:NumberType1``).
#: Hancom numbers in plain digits when the format is anything else.
NUMBER_FORMATS = frozenset({
    "DIGIT", "CIRCLED_DIGIT", "ROMAN_CAPITAL", "ROMAN_SMALL", "LATIN_CAPITAL", "LATIN_SMALL",
    "CIRCLED_LATIN_CAPITAL", "CIRCLED_LATIN_SMALL", "HANGUL_SYLLABLE", "CIRCLED_HANGUL_SYLLABLE",
    "HANGUL_JAMO", "CIRCLED_HANGUL_JAMO", "HANGUL_PHONETIC", "IDEOGRAPH", "CIRCLED_IDEOGRAPH",
})

#: The number formats of footnote and endnote numbers (``hc:NumberType2``): :data:`NUMBER_FORMATS`
#: and four more, which Hancom's own documents use only there.
NOTE_NUMBER_FORMATS = NUMBER_FORMATS | {"DECAGON_CIRCLE", "DECAGON_CIRCLE_HANJA", "SYMBOL", "USER_CHAR"}

#: Short names for some of :data:`NUMBER_FORMATS` (``page.set_page_number`` took them first).
NUMBER_FORMAT_ALIASES = {
    "NUMBER": "DIGIT", "ROMAN": "ROMAN_CAPITAL", "ROMAN_UPPER": "ROMAN_CAPITAL", "ROMAN_LOWER": "ROMAN_SMALL",
    "ALPHA": "LATIN_CAPITAL", "ALPHA_UPPER": "LATIN_CAPITAL", "ALPHA_LOWER": "LATIN_SMALL",
    "HANGUL": "HANGUL_SYLLABLE",
}


def number_format(value: object, *, note: bool = False) -> str:
    """*value* as one of :data:`NUMBER_FORMATS`, or of :data:`NOTE_NUMBER_FORMATS` for a footnote
    or endnote number (*note*), in either case or as one of the short names.

    Anything else is refused.
    """
    allowed = NOTE_NUMBER_FORMATS if note else NUMBER_FORMATS
    normalized = str(value).strip().upper()
    normalized = NUMBER_FORMAT_ALIASES.get(normalized, normalized)
    if normalized not in allowed:
        from ..errors import HwpxValueError

        raise HwpxValueError(
            f"number format {value!r} is for footnote and endnote numbers only"
            if normalized in NOTE_NUMBER_FORMATS
            else f"unsupported number format {value!r}",
            code="style-number-format-invalid",
            context={"format": str(value), "allowed": sorted(allowed)},
            suggestion="Use one of: " + ", ".join([*sorted(allowed), *sorted(NUMBER_FORMAT_ALIASES)]),
        )
    return normalized


def _numbering_refs_for_kind(
    header: "HwpxOxmlHeader",
    heading_type: str,
    resolved_levels: Sequence[Mapping[str, str]],
) -> list[str]:
    """``hh:numbering`` 정의를 만들고 각 레벨의 paraPr id를 돌려준다.

    *heading_type*은 ``"NUMBER"``(번호매기기) 또는 ``"OUTLINE"``(개요
    번호 모양) — 만드는 ``hh:numbering``/``hh:paraHead`` 구조 자체는
    완전히 동일, 참조하는 `hh:heading`의 `type`만 다르다.
    """
    checked_levels = [
        {**level, "numFormat": number_format(value)} if (value := level.get("numFormat") or level.get("format")) else level
        for level in resolved_levels
    ]
    numbering_id = header._create_numbering_definition(checked_levels)
    return [
        header._ensure_para_property_heading(
            heading_type=heading_type,
            id_ref=numbering_id,
            level=index,
        )
        for index in range(len(resolved_levels))
    ]


def ensure_numbering_refs(
    header: "HwpxOxmlHeader",
    *,
    kind: str,
    levels: Sequence[Mapping[str, str]] | None = None,
) -> list[str]:
    """``header_part.py``의 ``HwpxOxmlHeader.ensure_numbering``이 그대로
    위임하는 전체 구현 — 원래 위치에서 옮긴 것뿐, 동작 변경 없음(``bullet``/
    ``number`` 두 branch)에 ``outline``이 새로 붙었다."""

    resolved_levels = list(levels or [{}])
    if not resolved_levels:
        resolved_levels = [{}]
    normalized_kind = kind.lower()

    if normalized_kind == "bullet":
        refs: list[str] = []
        for index, level in enumerate(resolved_levels):
            bullet_char = str(
                level.get("char") or _DEFAULT_BULLET_CHARS[index % len(_DEFAULT_BULLET_CHARS)]
            )
            bullet_id = header._ensure_bullet_definition(bullet_char)
            refs.append(
                header._ensure_para_property_heading(
                    heading_type="BULLET",
                    id_ref=bullet_id,
                    level=index,
                )
            )
        return refs

    if normalized_kind in {"number", "numbered", "numbering"}:
        return _numbering_refs_for_kind(header, "NUMBER", resolved_levels)

    if normalized_kind == "outline":
        return _numbering_refs_for_kind(header, "OUTLINE", resolved_levels)

    from ..errors import HwpxValueError

    raise HwpxValueError(
        "kind must be 'bullet', 'number', or 'outline'",
        code="style-list-kind-invalid",
        context={"kind": kind},
        suggestion='kind="bullet"(글머리표), "number"(번호), "outline"(개요) 중 하나를 주세요.',
    )


def ensure_numbering_levels(header: "HwpxOxmlHeader", numbering_id: str, levels: int) -> None:
    """Give numbering *numbering_id* a head for every level up to *levels*, in the form a new
    definition's heads take (``^1.^2.`` …): Hancom draws no number for a level its numbering
    lacks. A numbering the header does not hold (an outline's ``idRef="0"``) is left alone."""

    numbering = next(
        (item for item in header.element.iter(f"{HH}numbering") if item.get("id") == str(numbering_id)),
        None,
    )
    if numbering is None:
        return
    present = {head.get("level") for head in numbering.findall(f"{HH}paraHead")}
    missing = [level for level in range(1, levels + 1) if str(level) not in present]
    if not missing:
        return
    for level in missing:
        head = numbering.makeelement(f"{HH}paraHead", header._default_para_head_attributes(level))
        head.text = ".".join(f"^{part}" for part in range(1, level + 1)) + "."
        numbering.append(head)
    for head in sorted(numbering.findall(f"{HH}paraHead"), key=lambda head: int(head.get("level") or 0)):
        numbering.remove(head)
        numbering.append(head)
    header.mark_dirty()


# --------------------------------------------------------------------------
# 7.0: numbering and bullet definitions, and a paragraph's place in a list

#: Hancom's own numbering, level by level: the number pattern (``^n`` stands for the number
#: of level *n*; an empty pattern draws no number), the digit style, and whether the level
#: is checkable. It is the definition a new Hancom document carries as id 1, numbers its
#: outline with and gives a new numbered list (``list_number_level1.hwpx``), the one in the
#: new-document skeleton Hancom 2024 (13.0) saved: 1,071 of the 1,157 ``hh:numbering`` in the
#: files of ``tests/fixtures`` are it (Hancom 13.0 on Windows, 12.30 on macOS), each level
#: with ``start="1"``, ``align="LEFT"``, ``useInstWidth="1"``, ``autoIndent="1"``,
#: ``widthAdjust="0"``, ``textOffset="50"`` (percent) and the text's own character shape,
#: and the definition itself with ``start="0"`` (drawn as 1). Seven files, without a
#: version, write the empty levels 9 and 10 as ``DIGIT``.
HANCOM_NUMBERING_LEVELS: tuple[tuple[str, str, bool], ...] = (
    ("^1.", "DIGIT", False),
    ("^2.", "HANGUL_SYLLABLE", False),
    ("^3)", "DIGIT", False),
    ("^4)", "HANGUL_SYLLABLE", False),
    ("(^5)", "DIGIT", False),
    ("(^6)", "HANGUL_SYLLABLE", False),
    ("^7", "CIRCLED_DIGIT", True),
    ("^8", "CIRCLED_HANGUL_SYLLABLE", True),
    ("", "HANGUL_JAMO", False),
    ("", "ROMAN_SMALL", True),
)

#: What one level of ``add_numbering(levels=...)`` or ``set_numbering_level`` may give.
_LEVEL_KEYS = ("text", "number_format", "start")

#: ``charPrIDRef`` of a head drawn in the character shape of its paragraph's text.
_TEXT_CHAR_SHAPE = "4294967295"


def _local(element: Any) -> str:
    tag = element.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _normalized_id(raw: object) -> str:
    text = str(raw).strip()
    return str(int(text)) if text.isdecimal() else text


def check_list_level(level: object) -> int:
    """*level* as a list level 1 to 10, else ``style-list-level-invalid``."""

    if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= 10:
        from ..errors import HwpxValueError

        raise HwpxValueError(
            f"level must be an int from 1 to 10; got {level!r}",
            code="style-list-level-invalid",
            context={"requested": repr(level)},
            suggestion="Hancom lists have ten levels, 1 to 10; it cannot save a document using a deeper one.",
        )
    return level


def _check_start(start: object) -> int:
    if isinstance(start, bool) or not isinstance(start, int) or not 0 <= start <= 0xFFFF:
        from ..errors import HwpxValueError

        raise HwpxValueError(  # Hancom keeps a list's start as 16 bits unsigned (0 drawn as 1)
            f"start must be an int from 0 to 65535; got {start!r}",
            code="style-list-start-value",
            context={"requested": repr(start)},
            suggestion="Pass the number the level starts at, from 0 to 65535.",
        )
    return start


def _level_changes(spec: object, *, where: str) -> dict[str, str]:
    """One level's ``text``/``number_format``/``start`` as the ``hh:paraHead`` values they write
    (``text``, ``numFormat``, ``start``), checked before anything changes."""

    from ..errors import HwpxValueError

    if not isinstance(spec, Mapping):
        raise HwpxValueError(
            f"{where} must be a mapping of text, number_format and start; got {spec!r}",
            code="style-numbering-level-invalid",
            context={"where": where, "requested": repr(spec), "allowed": list(_LEVEL_KEYS)},
            suggestion='Describe a level as {"text": "^1.", "number_format": "DIGIT", "start": 1}.',
        )
    unknown = sorted(str(key) for key in spec if key not in _LEVEL_KEYS)
    if unknown:
        raise HwpxValueError(
            f"{where} has keys a numbering level does not take: {', '.join(unknown)}",
            code="style-numbering-level-invalid",
            context={"where": where, "unknown": unknown, "allowed": list(_LEVEL_KEYS)},
            suggestion="A level takes text (the number pattern, ^n for level n's number), "
            "number_format and start.",
        )
    changes: dict[str, str] = {}
    text = spec.get("text")
    if text is not None:
        if not isinstance(text, str):
            raise HwpxValueError(
                f"{where}: text must be a string; got {text!r}",
                code="style-numbering-level-invalid",
                context={"where": where, "requested": repr(text)},
                suggestion='Pass the number pattern as a string: "^1." draws 1., "(^2)" draws (가); "" draws no number.',
            )
        changes["text"] = text
    if spec.get("number_format") is not None:
        changes["numFormat"] = number_format(spec["number_format"])
    if spec.get("start") is not None:
        changes["start"] = str(_check_start(spec["start"]))
    return changes


def _definition_id(definition: object) -> str:
    """The id of *definition*: a :class:`~hwpx.objects.NumberingInfo` or ``Bullet`` read from
    the document, or the id itself (an int or a string)."""

    if isinstance(definition, (int, str)) and not isinstance(definition, bool):
        return str(definition).strip()
    for name in ("raw_id", "id"):
        value = getattr(definition, name, None)
        if value is not None and not isinstance(value, bool):
            return str(value).strip()
    return repr(definition)


def _find_head_definition(header: "HwpxOxmlHeader", tag: str, wanted: str) -> Any | None:
    container = header._numberings_element() if tag == "numbering" else header._bullets_element()
    if container is None:
        return None
    normalized = _normalized_id(wanted)
    return next(
        (child for child in container if _local(child) == tag and _normalized_id(child.get("id") or "") == normalized),
        None,
    )


def _definition_not_found(tag: str, wanted: str) -> Exception:
    from ..errors import HwpxLookupError

    maker = "doc.styles.add_numbering()" if tag == "numbering" else "doc.styles.ensure_bullet()"
    return HwpxLookupError(
        f"the header has no {tag} with id {wanted!r}",
        code="style-definition-not-found",
        context={"kind": tag, "id": wanted},
        suggestion=f"Make one with {maker}, or read the ids the document has from "
        f"doc.styles.{'numberings' if tag == 'numbering' else 'bullets'}.",
    )


def add_numbering_definition(header: "HwpxOxmlHeader", levels: object) -> str:
    """``doc.styles.add_numbering``: a new ``hh:numbering`` of ten levels, Hancom's own
    (:data:`HANCOM_NUMBERING_LEVELS`) with each of *levels* changing the level of its place.
    Returns its id. Everything is checked before the header changes."""

    from ..errors import HwpxValueError

    if levels is None:
        specs: Sequence[object] = ()
    elif isinstance(levels, (str, bytes, Mapping)) or not isinstance(levels, Sequence):
        raise HwpxValueError(
            f"levels must be a sequence of level mappings; got {levels!r}",
            code="style-numbering-level-invalid",
            context={"requested": repr(levels)},
            suggestion='Pass levels=[{"text": "^1)"}, {"number_format": "LATIN_SMALL"}], one mapping per level from 1.',
        )
    else:
        specs = levels
    if len(specs) > len(HANCOM_NUMBERING_LEVELS):
        raise HwpxValueError(
            f"a numbering has at most {len(HANCOM_NUMBERING_LEVELS)} levels; got {len(specs)}",
            code="style-list-level-invalid",
            context={"requested": len(specs)},
            suggestion="Hancom lists have ten levels, 1 to 10.",
        )
    changes = [_level_changes(spec, where=f"levels[{index}]") for index, spec in enumerate(specs)]

    numberings = header._numberings_element(create=True)
    if numberings is None:  # pragma: no cover - the header always takes a refList
        from ..errors import HwpxStateError

        raise HwpxStateError("failed to create the numberings list", code="document-header-missing")
    numbering_id = header._allocate_ref_id(numberings, f"{HH}numbering")
    first_start = changes[0].get("start", "0") if changes else "0"
    numbering = numberings.makeelement(f"{HH}numbering", {"id": numbering_id, "start": first_start})
    for level, (text, digits, checkable) in enumerate(HANCOM_NUMBERING_LEVELS, start=1):
        given = changes[level - 1] if level <= len(changes) else {}
        attributes = header._default_para_head_attributes(level)
        attributes["numFormat"] = digits
        attributes["checkable"] = "1" if checkable else "0"
        attributes.update((key, value) for key, value in given.items() if key != "text")
        head = numbering.makeelement(f"{HH}paraHead", attributes)
        head.text = given.get("text", text) or None
        numbering.append(head)
    numberings.append(numbering)
    header._update_item_count(numberings, f"{HH}numbering")
    header.mark_dirty()
    return numbering_id


def ensure_bullet_definition(header: "HwpxOxmlHeader", char: object, char_pr_id_ref: object = None) -> str:
    """``doc.styles.ensure_bullet``: the id of the ``hh:bullet`` drawing *char*, made as Hancom
    writes one (31 of the 50 ``hh:bullet`` in the Hancom-saved files of ``tests/fixtures`` have
    this head) unless a bullet saying exactly the same is there already."""

    from ..errors import HwpxValueError

    if not isinstance(char, str) or len(char) != 1:
        raise HwpxValueError(
            f"a bullet is one character; got {char!r}",
            code="style-bullet-char-invalid",
            context={"requested": repr(char)},
            suggestion='Pass one character, such as "●" (the bullet Hancom gives a new list), "○", "■" or "-".',
        )
    shape = _TEXT_CHAR_SHAPE
    if char_pr_id_ref is not None:
        from .formatting import find_definition

        found = find_definition(header, "charPr", char_pr_id_ref)  # type: ignore[arg-type]
        if found is None:
            from ..errors import HwpxLookupError

            raise HwpxLookupError(
                f"the header has no charPr with id {char_pr_id_ref!r}",
                code="style-definition-not-found",
                context={"kind": "charPr", "id": str(char_pr_id_ref)},
                suggestion="Make the bullet's character shape with doc.styles.ensure_run(...) and pass its id.",
            )
        shape = str(found.get("id"))
    head = header._default_para_head_attributes(0)
    head.pop("start", None)
    head["useInstWidth"] = "0"
    head["charPrIDRef"] = shape
    bullets = header._bullets_element(create=True)
    if bullets is None:  # pragma: no cover - the header always takes a refList
        from ..errors import HwpxStateError

        raise HwpxStateError("failed to create the bullets list", code="document-header-missing")
    for bullet in bullets:
        if _local(bullet) != "bullet" or not bullet.get("id"):
            continue
        own = {key: value for key, value in bullet.attrib.items() if key != "id"}
        children = list(bullet)
        if (
            own == {"char": char, "useImage": "0"}
            and len(children) == 1
            and _local(children[0]) == "paraHead"
            and dict(children[0].attrib) == head
            and not (children[0].text or "").strip()
        ):
            return str(bullet.get("id"))
    bullet_id = header._allocate_ref_id(bullets, f"{HH}bullet")
    bullet = bullets.makeelement(f"{HH}bullet", {"id": bullet_id, "char": char, "useImage": "0"})
    bullet.append(bullet.makeelement(f"{HH}paraHead", head))
    bullets.append(bullet)
    header._update_item_count(bullets, f"{HH}bullet")
    header.mark_dirty()
    return bullet_id


def set_paragraph_list(paragraph: "HwpxOxmlParagraph", kind: str, definition: object, level: object) -> None:
    """``Paragraph.set_numbering``/``set_bullet``: give *paragraph* the head (``hh:heading``) of
    numbering or bullet *definition* at *level*, ``None`` no head. The rest of its paragraph
    shape stays; a shape saying the same is reused (``_derive_paragraph``)."""

    from .formatting import _derive_paragraph, _header_of
    from .paragraph_heading import set_paragraph_heading

    checked = check_list_level(level)
    if definition is None:
        attributes = {"type": "NONE", "idRef": "0", "level": "0"}
    else:
        tag = "numbering" if kind == "NUMBER" else "bullet"
        wanted = _definition_id(definition)
        found = _find_head_definition(_header_of(paragraph.section.document), tag, wanted)
        if found is None:
            raise _definition_not_found(tag, wanted)
        attributes = {"type": kind, "idRef": str(found.get("id")), "level": str(checked - 1)}
    _derive_paragraph(paragraph, lambda _header, element: set_paragraph_heading(element, attributes))


def set_numbering_level(
    document: "HwpxOxmlDocument", numbering: object, level: object, changes: Mapping[str, object]
) -> None:
    """``doc.styles.set_numbering_level``: change level *level* of numbering *numbering* (every
    ``hh:paraHead`` of that level, those in an ``hp:switch`` too) and lay out again the
    paragraphs that draw a number from it."""

    from ..errors import HwpxLookupError, HwpxValueError
    from .formatting import _header_of

    header = _header_of(document)
    checked = check_list_level(level)
    values = _level_changes(changes, where="set_numbering_level")
    if not values:
        raise HwpxValueError(
            "set_numbering_level got nothing to change",
            code="style-numbering-level-invalid",
            context={"allowed": list(_LEVEL_KEYS)},
            suggestion="Pass text=, number_format= or start=.",
        )
    wanted = _definition_id(numbering)
    element = _find_head_definition(header, "numbering", wanted)
    if element is None:
        raise _definition_not_found("numbering", wanted)
    heads = [head for head in element.iter(f"{HH}paraHead") if _normalized_id(head.get("level") or "") == str(checked)]
    if not heads:
        present = sorted({int(head.get("level") or 0) for head in element.iter(f"{HH}paraHead")})
        raise HwpxLookupError(
            f"numbering {wanted} has no level {checked}",
            code="style-numbering-level-missing",
            context={"id": wanted, "level": checked, "levels": present},
            suggestion="Change one of its levels, or make a numbering of ten levels with doc.styles.add_numbering().",
        )
    changed = False
    for head in heads:
        for key, value in values.items():
            if key == "text":
                if (head.text or "") != value or len(head):
                    for child in list(head):
                        head.remove(child)
                    head.text = value or None
                    changed = True
            elif head.get(key) != value:
                head.set(key, value)
                changed = True
    if checked == 1 and "start" in values and element.get("start") != values["start"]:
        element.set("start", values["start"])  # the definition's start is the list's (16 bits)
        changed = True
    if changed:
        header.mark_dirty()
        _clear_numbered_paragraphs(document, header, str(element.get("id")))


def _clear_numbered_paragraphs(document: "HwpxOxmlDocument", header: "HwpxOxmlHeader", numbering_id: str) -> None:
    """Drop the line layout cache of every paragraph that draws a number from *numbering_id*:
    its numbered paragraphs, and the outline paragraphs when a section numbers its outline
    with it. A changed pattern changes the room the number takes on the first line."""

    from ._document_primitives import _clear_paragraph_layout_cache
    from .formatting import _story_parts
    from .paragraph_heading import paragraph_heading

    wanted = _normalized_id(numbering_id)
    numbered: set[str] = set()
    outlined: set[str] = set()
    container = header._para_properties_element()
    for para_pr in [] if container is None else list(container):
        heading = paragraph_heading(para_pr)
        if heading is None:
            continue
        identifier = _normalized_id(para_pr.get("id") or "")
        if heading.get("type") == "NUMBER" and _normalized_id(heading.get("idRef") or "") == wanted:
            numbered.add(identifier)
        elif heading.get("type") == "OUTLINE":
            outlined.add(identifier)
    outlines = any(
        _normalized_id(sec_pr.get("outlineShapeIDRef") or "") == wanted
        for section in document.sections
        for sec_pr in section.element.iter(f"{HP}secPr")
    )
    affected = numbered | (outlined if outlines else set())
    if not affected:
        return
    for part in _story_parts(document):
        removed = 0
        for paragraph in part.element.iter(f"{HP}p"):
            if _normalized_id(paragraph.get("paraPrIDRef") or "") in affected:
                removed += _clear_paragraph_layout_cache(paragraph)
        if removed:
            part.mark_dirty()
