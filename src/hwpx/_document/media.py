# SPDX-License-Identifier: Apache-2.0
"""Picture/image domain owner behind the HwpxDocument facade."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Iterator, cast

from ..errors import HwpxStateError, HwpxValueError
from ..objects.binary_item import BinaryItem, PictureRef
from ..objects.results import PictureReplacement
from ..oxml import HwpxOxmlInlineObject, HwpxOxmlParagraph
from ..oxml.namespaces import HC, HP
from ._units import _mm_to_hwp_units

if TYPE_CHECKING:
    from hwpx.document import HwpxDocument
    from ..oxml import HwpxOxmlSection

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


def _bin_data_stem(value: Any) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    stem = PurePosixPath(raw).stem
    return stem or None


def add_picture(
    doc: "HwpxDocument",
    image_data: bytes,
    image_format: str,
    *,
    section: HwpxOxmlSection | None = None,
    section_index: int | None = None,
    width: int | None = None,
    height: int | None = None,
    width_mm: float | None = None,
    height_mm: float | None = None,
    align: str | None = None,
    para_pr_id_ref: str | int | None = None,
    style_id_ref: str | int | None = None,
    char_pr_id_ref: str | int | None = None,
    run_attributes: dict[str, str] | None = None,
    **extra_attrs: str,
) -> HwpxOxmlInlineObject:
    """Embed image data and place a picture object in a new paragraph."""

    # Call the local primitive directly rather than `doc.add_image` — that
    # facade name moved in 6.0 (design table row 33), and going through it
    # would fire a DeprecationWarning on every `add_picture` call even though
    # `add_picture` itself is a kept (unmoved) root method.
    binary_item_id_ref = str(add_image(doc, image_data, image_format))

    resolved_width = width
    if resolved_width is None:
        resolved_width = _mm_to_hwp_units(width_mm) if width_mm is not None else 14400

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

    paragraph = doc.add_paragraph(
        "",
        section=section,
        section_index=section_index,
        para_pr_id_ref=para_pr_id_ref,
        style_id_ref=style_id_ref,
        char_pr_id_ref=char_pr_id_ref,
        include_run=False,
        **cast(Any, extra_attrs),
    )
    return paragraph.add_picture(
        binary_item_id_ref,
        width=resolved_width,
        height=resolved_height,
        align=align,
        run_attributes=run_attributes,
        char_pr_id_ref=char_pr_id_ref,
    )


def _iter_picture_images(
    doc: "HwpxDocument",
) -> Iterator[tuple[int, HwpxOxmlSection, Any, Any]]:
    for section_index, section in enumerate(doc._root.sections):
        for picture in section.element.findall(f".//{_HP}pic"):
            image = picture.find(f"{_HC}img")
            if image is not None:
                yield section_index, section, picture, image


def _parse_hwpunit(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:  # pragma: no cover - defensive: non-numeric sz attrs
        return None


def picture_references(doc: "HwpxDocument") -> tuple[PictureRef, ...]:
    """Return body picture references in document order."""

    refs: list[PictureRef] = []
    for picture_index, (section_index, _section, picture, image) in enumerate(_iter_picture_images(doc)):
        size = picture.find(f"{_HP}sz")
        refs.append(
            PictureRef(
                picture_index=picture_index,
                section_index=section_index,
                binary_item_id_ref=image.get("binaryItemIDRef"),
                width=_parse_hwpunit(size.get("width") if size is not None else None),
                height=_parse_hwpunit(size.get("height") if size is not None else None),
            )
        )
    return tuple(refs)


def replace_picture(
    doc: "HwpxDocument",
    image_data: bytes,
    image_format: str,
    *,
    picture_index: int = 0,
    binary_item_id_ref: str | None = None,
    remove_orphaned: bool = True,
    item_id: str | None = None,
) -> PictureReplacement:
    """Replace a body picture's image asset while preserving its geometry.

    The existing ``<hp:pic>`` element is left in place.  Only the child
    ``<hc:img>`` ``binaryItemIDRef`` is changed, so size, position, crop,
    rotation, and wrapping geometry remain untouched.
    """

    if picture_index < 0:
        raise IndexError("picture_index must be non-negative")

    selected: tuple[int, HwpxOxmlSection, Any, Any] | None = None
    matched_index = -1
    for current_index, picture in enumerate(_iter_picture_images(doc)):
        _section_index, _section, _picture_element, image = picture
        current_ref = (image.get("binaryItemIDRef") or "").strip()
        if binary_item_id_ref is not None and current_ref != str(binary_item_id_ref):
            continue
        matched_index += 1
        if matched_index == picture_index:
            selected = picture
            break

    if selected is None:
        if binary_item_id_ref is None:
            raise IndexError(f"picture_index {picture_index} is out of range")
        raise IndexError(
            f"picture_index {picture_index} for binaryItemIDRef "
            f"{binary_item_id_ref!r} is out of range"
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
        if not any(
            (other_image.get("binaryItemIDRef") or "").strip() == old_ref
            for _other_section_index, _other_section, _other_picture, other_image in _iter_picture_images(doc)
        ):
            removed_old_image = remove_image(doc, old_ref)

    paragraph = _owning_paragraph(picture_element, section)
    if paragraph is None:  # pragma: no cover - defensive: <hp:pic> is always inside a <hp:p>
        raise HwpxStateError(
            "replaced picture element has no owning paragraph",
            code="media-owner-paragraph-missing",
        )

    return PictureReplacement(
        picture=HwpxOxmlInlineObject(picture_element, paragraph),
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
        media_type = str(item.get("media-type", "")).strip().lower()
        href_path = PurePosixPath(href)
        if (
            media_type.startswith("image/")
            or (len(href_path.parts) >= 2 and href_path.parts[0] == "BinData")
        ):
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
    """Return every embedded binary data item as a :class:`BinaryItem`."""

    header = doc._root.headers[0] if doc._root.headers else None
    if header is None:
        return ()

    items: list[BinaryItem] = []
    for entry in header.list_bin_items():
        bin_data = entry.get("BinData", "")
        item_id = _bin_data_stem(bin_data) or entry.get("id", "")
        href = f"BinData/{bin_data}" if bin_data else ""
        size = 0
        if href and doc._package.has_part(href):
            size = len(doc._package.read(href))
        items.append(
            BinaryItem(item_id=item_id, format=entry.get("Format", ""), href=href, size=size)
        )
    return tuple(items)


def remove_image(doc: "HwpxDocument", item_id: str) -> bool:
    """Remove an embedded image by its manifest item id.

    This removes the binary data from the ZIP, the manifest entry, and
    the header binItem entry.

    Returns:
        ``True`` if any component was removed.
    """

    # 6.0: callers may hand back the BinaryItem that add_image returned; its
    # str() is the manifest id, which is the join key this walk uses.
    item_id = str(item_id)
    removed = False
    header = doc._root.headers[0] if doc._root.headers else None

    # Find file path and binItem numeric id from header metadata
    bin_data_path: str | None = None
    bin_item_numeric_id: str | None = None
    if header is not None:
        for bi in header.list_bin_items():
            bin_data_val = bi.get("BinData", "")
            # Match by data file name prefix (e.g. "BIN0001" matches "BIN0001.jpg")
            if bin_data_val.startswith(item_id):
                bin_item_numeric_id = bi.get("id")
                if bin_data_val:
                    bin_data_path = f"BinData/{bin_data_val}"
                break

    # Also try manifest-based lookup for the file path
    if bin_data_path is None:
        manifest_el = doc._package._manifest_element()
        if manifest_el is not None:
            ns = {"opf": "http://www.idpf.org/2007/opf/"}
            for it in manifest_el.findall("opf:item", ns):
                if it.get("id") == item_id:
                    href = it.get("href", "")
                    if href:
                        bin_data_path = href
                    break

    # Remove from header binDataList (use the numeric id)
    if header is not None and bin_item_numeric_id is not None:
        if header.remove_bin_item(bin_item_numeric_id):
            removed = True

    # Remove from manifest
    if doc._package.remove_manifest_item(item_id):
        removed = True

    # Remove from ZIP
    if bin_data_path and doc._package.has_part(bin_data_path):
        doc._package.delete(bin_data_path)
        removed = True

    return removed
