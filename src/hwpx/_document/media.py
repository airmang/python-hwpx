# SPDX-License-Identifier: Apache-2.0
"""Picture/image domain owner behind the HwpxDocument facade."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Iterator, NamedTuple, cast

from ..errors import HwpxStateError, HwpxValueError
from ..objects.binary_item import BinaryItem
from ..objects.results import PictureReplacement
from ..opc.relationships import (
    BINARY_ITEM_REF_ATTRS,
    bin_ref_aliases,
    is_binary_manifest_item,
    is_linked_file,
    normalize_part_name,
    resolve_part_name,
)
from ..oxml import HwpxOxmlParagraph
from ..oxml.namespaces import HC, HP
from ..oxml.objects import HwpxOxmlPicture
from ..oxml.color import normalize_color
from ..oxml.shape_position import PictureGlow, PictureReflection, PictureShadow, validate_picture_effects
from ..oxml.shape_position import (
    line_width_units, validate_picture_align, validate_picture_crop, validate_picture_image, validate_shape_size,
)
from ._units import _mm_to_hwp_units

if TYPE_CHECKING:
    from hwpx.document import HwpxDocument
    from ..oxml import HwpxOxmlSection, Style

_HP = HP
_HC = HC


def _local_name(node_or_tag: Any) -> str:
    tag = getattr(node_or_tag, "tag", node_or_tag)
    if not isinstance(tag, str):
        return ""
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _owning_paragraph(element: Any, section: "HwpxOxmlSection") -> "HwpxOxmlParagraph | None":
    """Return the innermost ``<hp:p>`` ancestor of *element* within *section*.

    Needed because ``_iter_picture_images`` finds ``<hp:pic>`` elements with a
    section-wide XPath search, not by iterating paragraphs, so no paragraph
    reference is available for free the way ``_iter_form_field_matches``
    (fields.py) tracks one while it walks paragraph-by-paragraph.

    Walks down from *section* rather than up from *element* via
    ``getparent()`` — mirrors ``oxml.memo._paragraph_containing`` (see there
    for why: lxml supports ``getparent()``, hand-built
    ``xml.etree.ElementTree`` test fixtures do not, and ``for child in node``
    works on both).
    """

    def _walk(node: Any, nearest: Any) -> Any:
        if _local_name(node) == "p":
            nearest = node
        if node is element:
            return nearest
        for child in node:
            found = _walk(child, nearest)
            if found is not None:
                return found
        return None

    node = _walk(section.element, None)
    if node is None:
        return None
    return HwpxOxmlParagraph(node, section)


def _png_dimensions(image_data: bytes) -> tuple[int, int] | None:
    if len(image_data) < 24 or not image_data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    width = int.from_bytes(image_data[16:20], "big")
    height = int.from_bytes(image_data[20:24], "big")
    if width <= 0 or height <= 0:
        return None
    return width, height


#: The image formats a picture takes, each with the format its bytes must show (``jpeg`` and
#: ``jpg``, ``tif`` and ``tiff`` are one each).
_IMAGE_FORMATS = {
    "png": "png", "jpg": "jpeg", "jpeg": "jpeg", "gif": "gif", "bmp": "bmp",
    "tif": "tiff", "tiff": "tiff", "svg": "svg", "wmf": "wmf", "emf": "emf",
}


def _sniff_image(data: bytes) -> str | None:
    """The image format the first bytes of *data* show, or ``None``."""

    head = bytes(data[:64])
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if head.startswith(b"BM"):
        return "bmp"
    if head.startswith((b"II*\x00", b"MM\x00*")):
        return "tiff"
    if head.startswith((b"\xd7\xcd\xc6\x9a", b"\x01\x00\x09\x00", b"\x02\x00\x09\x00")):
        return "wmf"
    if head.startswith(b"\x01\x00\x00\x00") and head[40:44] == b" EMF":
        return "emf"
    text = bytes(data[:1024]).lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if text.startswith((b"<svg", b"<?xml", b"<!doctype svg")) and b"<svg" in text:
        return "svg"
    return None


def check_image(image_data: Any, image_format: Any) -> str:
    """Refuse bytes that are not an image of a format a picture takes; return the format name.

    The format name must be one of :data:`_IMAGE_FORMATS` and the first bytes of *image_data*
    must show that format: Hancom shows an empty frame for anything else, and the save does
    not notice. Raises :class:`~hwpx.errors.HwpxValueError` (``code="media-image-invalid"``).
    """

    fmt = str(image_format).lower().lstrip(".") if isinstance(image_format, str) else ""
    allowed = sorted(_IMAGE_FORMATS)
    if fmt not in _IMAGE_FORMATS:
        raise HwpxValueError(
            f"그림 형식 이름 {image_format!r} 을(를) 모릅니다.",
            code="media-image-invalid",
            context={"format": repr(image_format), "allowed": allowed},
            suggestion="형식 이름은 " + ", ".join(allowed) + " 중 하나입니다(파일 확장자).",
        )
    if not isinstance(image_data, (bytes, bytearray, memoryview)):
        raise HwpxValueError(
            f"그림 데이터는 bytes 여야 합니다 — {type(image_data).__name__}.",
            code="media-image-invalid",
            context={"format": fmt, "type": type(image_data).__name__},
            suggestion="파일이면 pathlib.Path(경로).read_bytes() 로 읽어 넘기세요.",
        )
    found = _sniff_image(bytes(image_data))
    if found != _IMAGE_FORMATS[fmt]:
        what = "그림 파일이 아닙니다" if found is None else f"{found} 그림입니다"
        raise HwpxValueError(
            f"{fmt} 형식이라고 했지만 데이터의 첫 바이트를 보면 {what}.",
            code="media-image-invalid",
            context={"format": fmt, "detected": found},
            suggestion=(
                "그림 파일의 bytes 를 그대로 넘기세요."
                if found is None
                else f"형식 이름을 {found!r} 로 주세요."
            ),
        )
    return fmt


def _bin_data_stem(value: Any) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    stem = PurePosixPath(raw).stem
    return stem or None


#: ``align`` values an inline picture also takes as its paragraph alignment.
_INLINE_PICTURE_ALIGNMENT = {"LEFT": "LEFT", "CENTER": "CENTER", "RIGHT": "RIGHT"}


def add_picture(
    doc: "HwpxDocument",
    image_data: bytes,
    image_format: str,
    *,
    section: HwpxOxmlSection | None = None,
    width: int | None = None,
    height: int | None = None,
    width_mm: float | None = None,
    height_mm: float | None = None,
    alignment: str | None = None,
    brightness: int = 0,
    contrast: int = 0,
    effect: str = "REAL_PIC",
    alpha: int = 0,
    line_color: str | None = None,
    line_width_mm: float = 0.12,
    crop: tuple[int, int, int, int] | None = None,
    shadow: PictureShadow | None = None,
    glow: PictureGlow | None = None,
    soft_edge: int | None = None,
    reflection: PictureReflection | None = None,
    para_pr_id_ref: str | int | None = None,
    style: "int | str | Style | None" = None,
    char_pr_id_ref: str | int | None = None,
    run_attributes: dict[str, str] | None = None,
) -> HwpxOxmlPicture:
    """Embed image data and place a picture object in a new paragraph, the image adjusted and bordered as
    :meth:`HwpxOxmlParagraph.add_picture` takes it (*alignment* as a name, *line_width_mm* in mm)."""

    align = alignment
    check_image(image_data, image_format)
    validate_picture_align(align)  # before anything is stored: Hancom reads an unknown one as LEFT
    validate_picture_image(brightness, contrast, effect, alpha)  # ... and draws no other adjustment
    line_width_units(line_width_mm)  # a width in mm from 0, checked before anything is stored too
    if line_color is not None:
        normalize_color(line_color)
    resolved_width = width
    if resolved_width is None:
        resolved_width = _mm_to_hwp_units(width_mm) if width_mm is not None else 14400
    validate_shape_size(resolved_width, 0)  # validate before aspect-ratio arithmetic too

    resolved_height = height
    if resolved_height is None:
        if height_mm is not None:
            resolved_height = _mm_to_hwp_units(height_mm)
        else:
            dimensions = _png_dimensions(image_data)
            if dimensions is not None:
                source_width, source_height = dimensions
                resolved_height = round(resolved_width * source_height / source_width)
            else:
                resolved_height = resolved_width
    validate_shape_size(resolved_width, resolved_height)  # before anything is stored too
    validate_picture_crop(crop, resolved_width, resolved_height)
    validate_picture_effects(shadow, glow, soft_edge, reflection)

    # The paragraph first: it checks the section, the style and the paragraph and character shape ids
    # before it changes anything. The image was stored before it, so a call refused for one of those
    # (``style="no such style"``) left the image bytes in the saved file (7.0 development; 6.x looked the
    # style up first).
    paragraph = doc.add_paragraph(
        "",
        section=section,
        para_pr_id_ref=para_pr_id_ref,
        style=style,
        char_pr_id_ref=char_pr_id_ref,
        include_run=False,
    )
    stored: BinaryItem | None = None
    try:
        # Call the local primitive directly rather than `doc.add_image` — that
        # facade name moved in 6.0 (design table row 33), and going through it
        # would fire a DeprecationWarning on every `add_picture` call even though
        # `add_picture` itself is a kept (unmoved) root method.
        stored = add_image(doc, image_data, image_format)
        picture = paragraph.add_picture(
            str(stored),
            width=resolved_width,
            height=resolved_height,
            alignment=align,
            brightness=brightness,
            contrast=contrast,
            effect=effect,
            alpha=alpha,
            line_color=line_color,
            line_width_mm=line_width_mm,
            crop=crop,
            shadow=shadow,
            glow=glow,
            soft_edge=soft_edge,
            reflection=reflection,
            run_attributes=run_attributes,
            char_pr_id_ref=char_pr_id_ref,
        )
    except BaseException:
        # Whatever refused it, the call leaves neither the image nor the empty paragraph behind.
        if stored is not None:
            remove_image(doc, stored, force=True)
        paragraph.remove()
        raise
    paragraph_alignment = _INLINE_PICTURE_ALIGNMENT.get(str(align).strip().upper()) if align else None
    if paragraph_alignment is not None and doc._root.headers:
        # The picture sits in the text line, so Hancom places it by the
        # paragraph's alignment; hp:pos/@horzAlign alone does not move it.
        paragraph.para_pr_id_ref = doc._root.headers[0].ensure_paragraph_format(
            base_para_pr_id=paragraph.para_pr_id_ref, alignment=paragraph_alignment,
        )
    return picture


def _iter_picture_images(
    doc: "HwpxDocument",
) -> Iterator[tuple[int, HwpxOxmlSection, Any, Any]]:
    for section_index, section in enumerate(doc._root.sections):
        for picture in section.element.findall(f".//{_HP}pic"):
            image = picture.find(f"{_HC}img")
            if image is not None:
                yield section_index, section, picture, image


def _enclosing_paragraph(element: Any, section: "HwpxOxmlSection") -> "HwpxOxmlParagraph | None":
    """The innermost ``hp:p`` holding *element*: up its parents (lxml), else down from the section."""

    getparent = getattr(element, "getparent", None)
    if getparent is None:
        return _owning_paragraph(element, section)
    node = getparent()
    while node is not None and _local_name(node) != "p":
        node = node.getparent()
    return HwpxOxmlParagraph(node, section) if node is not None else None


def pictures(doc: "HwpxDocument") -> "tuple[HwpxOxmlPicture, ...]":
    """Every picture in the body, in document order -- the order (and so the ``index``) of
    :func:`replace_picture`: in table cells, text boxes, notes and groups too."""

    found: list[HwpxOxmlPicture] = []
    for _section_index, section, element, _image in _iter_picture_images(doc):
        paragraph = _enclosing_paragraph(element, section)
        if paragraph is not None:
            found.append(HwpxOxmlPicture(element, paragraph))
    return tuple(found)


def replace_picture(
    doc: "HwpxDocument",
    image_data: bytes,
    image_format: str,
    *,
    index: int = 0,
    old_item_id: str | None = None,
    remove_orphaned: bool = True,
    item_id: str | None = None,
) -> PictureReplacement:
    """Replace a body picture's image asset while preserving its geometry.

    The picture is the *index*-th of :func:`pictures` (document order), or with *old_item_id*
    the *index*-th of those showing that binary item. The existing ``<hp:pic>`` element is left
    in place.  Only the child ``<hc:img>`` ``binaryItemIDRef`` is changed, so size, position, crop,
    rotation, and wrapping geometry remain untouched.
    """

    check_image(image_data, image_format)
    from ..errors import HwpxIndexError

    if index < 0:
        raise HwpxIndexError(
            "index must be non-negative",
            code="media-picture-not-found",
            context={"pictureIndex": index},
            suggestion="index 는 0부터 셉니다. doc.media.pictures 로 그림 목록을 보세요.",
        )

    selected: tuple[int, HwpxOxmlSection, Any, Any] | None = None
    matched_index = -1
    for picture in _iter_picture_images(doc):
        _section_index, _section, _picture_element, image = picture
        current_ref = (image.get("binaryItemIDRef") or "").strip()
        if old_item_id is not None and current_ref != str(old_item_id):
            continue
        matched_index += 1
        if matched_index == index:
            selected = picture
            break

    if selected is None:
        message = f"picture index {index} is out of range" if old_item_id is None else (
            f"picture index {index} for binaryItemIDRef {old_item_id!r} is out of range"
        )
        raise HwpxIndexError(
            message,
            code="media-picture-not-found",
            context={"pictureIndex": index, "found": matched_index + 1,
                     "binaryItemIdRef": old_item_id},
            suggestion=f"그림이 {matched_index + 1}개 있습니다. doc.media.pictures 로 목록을 보세요.",
        )

    section_index, section, picture_element, image = selected
    old_ref = (image.get("binaryItemIDRef") or "").strip()
    # Call the local primitives directly rather than `doc.add_image`/
    # `doc.remove_image` — both names moved in 6.0 (design table rows 33/77),
    # and going through the facade would fire a DeprecationWarning on every
    # replace even when reached via the new `doc.media.replace_picture` path.
    new_ref = str(add_image(doc, image_data, image_format, item_id=item_id))
    image.set("binaryItemIDRef", new_ref)
    section.mark_dirty()

    removed_old_image = False
    if remove_orphaned and old_ref and old_ref != new_ref:
        # The old item is an orphan only if nothing else points at it: another
        # picture, but also an image fill in the header or a master page.
        target = _find_binary_item(doc, old_ref)
        if target is not None and not _binary_item_references(doc, target):
            removed_old_image = _remove_binary_item(doc, target)

    paragraph = _owning_paragraph(picture_element, section)
    if paragraph is None:  # pragma: no cover - defensive: <hp:pic> is always inside a <hp:p>
        raise HwpxStateError(
            "replaced picture element has no owning paragraph",
            code="media-owner-paragraph-missing",
        )

    return PictureReplacement(
        picture=HwpxOxmlPicture(picture_element, paragraph),
        item_id=new_ref,
        previous_item_id=old_ref or None,
        removed_orphans=(old_ref,) if removed_old_image else (),
    )


def add_image(
    doc: "HwpxDocument",
    image_data: bytes,
    image_format: str,
    *,
    item_id: str | None = None,
) -> BinaryItem:
    """Embed an image file and return it as a :class:`BinaryItem`.

    Args:
        image_data: Raw image bytes.
        image_format: Image format extension (``jpg``, ``png``, …).
        item_id: Optional explicit manifest item id.  When omitted an
                 auto-generated ``BIN####`` id is used.

    Returns:
        The created item. ``str(item)`` is the manifest item id that can be
        passed to ``binaryItemIDRef`` when constructing a ``<hp:pic>``
        element — the same string 5.x returned directly (design §2.6).
    """

    fmt = image_format.lower().lstrip(".")
    media_type = doc._FORMAT_TO_MEDIA_TYPE.get(fmt, f"image/{fmt}")

    existing_ids = _existing_image_item_ids(doc)

    # Determine a unique item id
    if item_id is None:
        n = 1
        while True:
            item_id = f"BIN{n:04d}"
            if item_id not in existing_ids:
                break
            n += 1
    elif item_id in existing_ids:
        raise HwpxValueError(
            f"image item_id {item_id!r} already exists",
            code="media-item-id-taken",
            context={"itemId": item_id},
            suggestion="Omit item_id to get an auto-assigned BIN#### id.",
        )

    # File path inside the ZIP
    bin_data_name = f"{item_id}.{fmt}"
    bin_data_path = f"BinData/{bin_data_name}"

    # 1) Write image bytes into the package
    doc._package.write(bin_data_path, image_data)

    # 2) Register in manifest. ``isEmbeded="1"`` (OWPML's single-d spelling) marks
    #    the BinData image as embedded — real Hancom drops the picture without it.
    doc._package.add_manifest_item(
        item_id, bin_data_path, media_type, extra_attrs={"isEmbeded": "1"}
    )

    # 3) Register in header binDataList
    header = doc._root.headers[0] if doc._root.headers else None
    if header is not None:
        header.add_bin_item(
            item_type="Embedding",
            bin_data_id=bin_data_name,
            format=fmt,
        )

    return BinaryItem(item_id=item_id, format=fmt, href=bin_data_path, size=len(image_data))


def _existing_image_item_ids(doc: "HwpxDocument") -> set[str]:
    existing_ids: set[str] = set()
    header = doc._root.headers[0] if doc._root.headers else None
    if header is not None:
        for item in header.list_bin_items():
            stem = _bin_data_stem(item.get("BinData"))
            if stem:
                existing_ids.add(stem)

    for item in doc._package._manifest_items():
        href = str(item.get("href", "")).strip()
        if is_binary_manifest_item(href, str(item.get("media-type", "")).strip()):
            item_id = str(item.get("id", "")).strip()
            if item_id:
                existing_ids.add(item_id)
            stem = _bin_data_stem(href)
            if stem:
                existing_ids.add(stem)

    for part_name in doc._package.part_names():
        path = PurePosixPath(str(part_name))
        if len(path.parts) >= 2 and path.parts[0] == "BinData" and path.stem:
            existing_ids.add(path.stem)
    return existing_ids


def list_images(doc: "HwpxDocument") -> tuple[BinaryItem, ...]:
    """Return every embedded binary data item as a :class:`BinaryItem`.

    Items the header ``binDataList`` lists come first. Binary items only the
    ``content.hpf`` manifest lists (href under ``BinData/`` or an ``image/*``
    media type) follow in manifest order -- Hancom-saved files usually
    have no ``binDataList`` at all. An item marked ``isEmbeded="0"`` whose
    href lies outside ``BinData/`` links a file outside the package and is
    left out; Hancom marks OLE objects ``isEmbeded="0"`` too but keeps their
    file in ``BinData/``, so they are listed. An embedded item whose part is
    missing is listed with ``size=0``.
    """

    header = doc._root.headers[0] if doc._root.headers else None

    items: list[BinaryItem] = []
    for entry in header.list_bin_items() if header is not None else ():
        bin_data = entry.get("BinData", "")
        item_id = _bin_data_stem(bin_data) or entry.get("id", "")
        href = f"BinData/{bin_data}" if bin_data else ""
        size = 0
        if href and doc._package.has_part(href):
            size = len(doc._package.read(href))
        items.append(
            BinaryItem(item_id=item_id, format=entry.get("Format", ""), href=href, size=size)
        )

    listed = {item.item_id for item in items}
    package = doc._package
    manifest_path = package.main_content.full_path
    part_names = package.part_names()
    for manifest_item in package._manifest_items():
        item_id = str(manifest_item.get("id", "")).strip()
        href = str(manifest_item.get("href", "")).strip()
        if not item_id or not href:
            continue
        if not is_binary_manifest_item(href, str(manifest_item.get("media-type", "")).strip()):
            continue
        if is_linked_file(href, manifest_item.get("isEmbeded")):
            continue  # links a file outside the package; not a binary it holds
        if item_id in listed or _bin_data_stem(href) in listed:
            continue
        part_name = resolve_part_name(manifest_path, href, known_parts=part_names)
        size = len(package.read(part_name)) if package.has_part(part_name) else 0
        fmt = PurePosixPath(href).suffix.lower().lstrip(".")
        items.append(BinaryItem(item_id=item_id, format=fmt, href=href, size=size))
        listed.add(item_id)
    return tuple(items)


def remove_image(
    doc: "HwpxDocument", item_id: "str | BinaryItem", *, force: bool = False
) -> bool:
    """Remove an embedded image by its manifest item id or part path.

    *item_id* is a manifest id (``"image1"``), a part path
    (``"BinData/image1.png"``), or a :class:`BinaryItem` from
    :func:`list_images`. This removes the binary data from the ZIP, the
    manifest entry, and the header binItem entry when there is one, so
    items only the manifest lists are removed too. A manifest item that is
    not a binary item (a section, the header) is not an image: nothing is
    removed and the result is ``False``.

    An item the document still points at -- from a picture, an image fill or
    bullet in the header, a master page, a video, an OLE object or an
    embedded font -- is refused with ``HwpxValueError`` (code
    ``media-item-in-use``) before anything changes. ``force=True`` removes
    it anyway and leaves those references dangling.

    Returns:
        ``True`` if any component was removed.
    """

    # 6.0: callers may hand back the BinaryItem that add_image returned; its
    # str() is the manifest id, which is the join key this walk uses.
    item_id = str(item_id)
    target = _find_binary_item(doc, item_id)
    if target is None:
        return False
    if not force:
        references = _binary_item_references(doc, target)
        if references:
            raise HwpxValueError(
                f"binary item {item_id!r} is still referenced: " + ", ".join(references),
                code="media-item-in-use",
                context={"itemId": item_id, "references": references},
                suggestion=(
                    "Remove or repoint the objects that use it first "
                    "(doc.media.pictures lists body pictures), "
                    "or pass force=True to remove it anyway."
                ),
            )
    return _remove_binary_item(doc, target)


def remove_unused_images(doc: "HwpxDocument") -> tuple[BinaryItem, ...]:
    """Remove every embedded binary item nothing in the document points at and
    return the removed items.

    Hancom drops such items when it saves a document; a picture removed from the
    body (``section.clear_body()``, a deleted paragraph) leaves its image behind.
    An item is kept while anything :func:`remove_image` checks points at it.
    """

    removed: list[BinaryItem] = []
    for item in list_images(doc):
        target = _find_binary_item(doc, str(item))
        if target is None or _binary_item_references(doc, target):
            continue
        if _remove_binary_item(doc, target):
            removed.append(item)
    return tuple(removed)


def _document_view(root: Any) -> "HwpxDocument | None":
    """The document *root* (a ``HwpxOxmlDocument``) and the package it was read from, as the helpers here take
    one; ``None`` for a document read from no package."""

    package = getattr(getattr(root, "_manifest_source", None), "__self__", None)
    if package is None:
        return None
    from types import SimpleNamespace

    from ..document import HwpxDocument

    return cast("HwpxDocument", SimpleNamespace(_root=root, _package=package,
                                                _FORMAT_TO_MEDIA_TYPE=HwpxDocument._FORMAT_TO_MEDIA_TYPE))


def carry_object_parts(element: Any, source_root: Any, target_root: Any) -> None:
    """Give the document *target_root* the images and charts the object *element* (a copy from the document
    *source_root*) shows, and point *element* at them there, as Hancom 2024 does when it pastes an object
    copied from another document (objlim evidence xpic, xpic2, xchart, xchart2): each image becomes a new
    binary item of the target, and each chart part a ``Chart/chartN.xml`` with the first number the target
    does not use (``chart2.xml`` beside a ``chart1.xml``)."""

    from ..opc.relationships import BINARY_ITEM_REF_ATTRS

    source, target = _document_view(source_root), _document_view(target_root)
    if source is None or target is None:
        return
    carried: dict[str, str] = {}
    for node in element.iter():
        for attribute in BINARY_ITEM_REF_ATTRS:
            reference = node.get(attribute)
            if not reference:
                continue
            if reference not in carried:
                found = _find_binary_item(source, reference)
                if found is None or not found.bin_data_path or not source._package.has_part(found.bin_data_path):
                    continue
                data = source._package.read(found.bin_data_path)
                fmt = PurePosixPath(found.bin_data_path).suffix.lstrip(".").lower() or "png"
                carried[reference] = str(add_image(target, data, fmt))
            node.set(attribute, carried[reference])
        chart = node.get("chartIDRef")
        if chart and source._package.has_part(chart):
            used = {name for name in target._package.part_names() if name.startswith("Chart/")}
            number = 1
            while f"Chart/chart{number}.xml" in used:
                number += 1
            name = f"Chart/chart{number}.xml"
            target._package.write(name, source._package.read(chart))
            node.set("chartIDRef", name)


def remove_orphaned_items(root: Any, references: "set[str]") -> tuple[BinaryItem, ...]:
    """Remove the binary items *references* name (``binaryItemIDRef`` values and the like of an object just
    taken out of the document *root*, a ``HwpxOxmlDocument``) that nothing in the document points at any
    more, and return them: :func:`remove_unused_images` limited to those items, for ``obj.remove()``.

    The package is the one *root* was read from (its manifest source); a document read from none removes
    nothing. An item still pointed at anywhere :func:`remove_image` checks stays.
    """

    package = getattr(getattr(root, "_manifest_source", None), "__self__", None)
    wanted: set[str] = set()
    for reference in references:
        wanted |= bin_ref_aliases(reference)
    if package is None or not wanted:
        return ()
    from types import SimpleNamespace

    view = cast("HwpxDocument", SimpleNamespace(_root=root, _package=package))
    removed: list[BinaryItem] = []
    for item in list_images(view):
        target = _find_binary_item(view, str(item))
        if target is None or target.aliases.isdisjoint(wanted) or _binary_item_references(view, target):
            continue
        if _remove_binary_item(view, target):
            removed.append(item)
    return tuple(removed)


class _BinaryItemTarget(NamedTuple):
    """One binary item as :func:`remove_image` found it."""

    item_id: str
    #: ``hh:binItem/@id`` of the header entry, when the header lists the item.
    bin_item_numeric_id: str | None
    #: The ``BinData/`` part (or the manifest href) holding the data.
    bin_data_path: str | None
    #: Every value a reference to this item may carry.
    aliases: frozenset[str]


def _find_binary_item(doc: "HwpxDocument", item_id: str) -> _BinaryItemTarget | None:
    """Find the binary item *item_id* names, or ``None`` when there is none.

    A manifest item outside ``BinData/`` without an ``image/*`` media type (a
    section, the header, settings) is not a binary item, so it is ``None``.
    """

    part_path = normalize_part_name(item_id) if "/" in item_id else None
    header = doc._root.headers[0] if doc._root.headers else None

    # Find file path and binItem numeric id from header metadata
    bin_data_path: str | None = None
    bin_item_numeric_id: str | None = None
    if header is not None:
        for bi in header.list_bin_items():
            bin_data_val = bi.get("BinData", "")
            if part_path is not None:
                matched = f"BinData/{bin_data_val}" == part_path
            else:
                # Match the data file name's stem ("BIN0001" matches "BIN0001.jpg"),
                # or the whole file name; a prefix match would take "image10.png"
                # for "image1".
                matched = item_id in (bin_data_val, _bin_data_stem(bin_data_val))
            if matched:
                bin_item_numeric_id = bi.get("id")
                if bin_data_val:
                    bin_data_path = f"BinData/{bin_data_val}"
                break

    # The manifest item remove_manifest_item() would take: by id, then by href.
    manifest_item = None
    for it in doc._package._manifest_items():
        if it.get("id") == item_id:
            manifest_item = it
            break
    if manifest_item is None and part_path is not None:
        for it in doc._package._manifest_items():
            if normalize_part_name(it.get("href", "")) == part_path:
                manifest_item = it
                break

    # Also try manifest-based lookup for the file path
    if bin_data_path is None:
        bin_data_path = part_path
    if bin_data_path is None and manifest_item is not None:
        bin_data_path = manifest_item.get("href") or None

    if bin_item_numeric_id is None:
        if manifest_item is not None:
            is_binary = is_binary_manifest_item(
                manifest_item.get("href", ""), manifest_item.get("media-type", "")
            )
        else:
            is_binary = bin_data_path is not None and is_binary_manifest_item(bin_data_path, "")
        if not is_binary:
            return None

    aliases: set[str] = set()
    for value in (
        None if part_path is not None else item_id,
        manifest_item.get("id") if manifest_item is not None else None,
        bin_data_path,
        bin_item_numeric_id,
    ):
        aliases.update(bin_ref_aliases(value))
    return _BinaryItemTarget(
        item_id=item_id,
        bin_item_numeric_id=bin_item_numeric_id,
        bin_data_path=bin_data_path,
        aliases=frozenset(aliases),
    )


def _binary_item_references(doc: "HwpxDocument", target: _BinaryItemTarget) -> list[str]:
    """Where the document points at *target*, as ``"part: element@attr"``.

    Each place is listed once, in document order, however often it recurs.
    """

    root = doc._root
    found: dict[str, None] = {}
    for part in (*root.headers, *root.sections, *root.master_pages, *root.histories):
        for element in part.element.iter():
            for attr in BINARY_ITEM_REF_ATTRS:
                value = element.get(attr)
                if value and not target.aliases.isdisjoint(bin_ref_aliases(value)):
                    found[f"{part.part_name}: {_local_name(element)}@{attr}"] = None
    return list(found)


def _remove_binary_item(doc: "HwpxDocument", target: _BinaryItemTarget) -> bool:
    removed = False
    header = doc._root.headers[0] if doc._root.headers else None

    # Remove from header binDataList (use the numeric id)
    if header is not None and target.bin_item_numeric_id is not None:
        if header.remove_bin_item(target.bin_item_numeric_id):
            removed = True

    # Remove from manifest (by id, or by href when given a part path)
    if doc._package.remove_manifest_item(target.item_id):
        removed = True

    # Remove from ZIP
    if target.bin_data_path and doc._package.has_part(target.bin_data_path):
        doc._package.delete(target.bin_data_path)
        removed = True

    return removed
