"""Local-only structural sanitization for privacy-safe practice derivatives."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from hwpx.document import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety

from .registry import assert_redacted_payload

DERIVATIVE_ID_PATTERN = re.compile(r"^DER-[A-F0-9]{20}$")
_HUMAN_TEXT_NAMES = frozenset({"t", "title", "creator", "subject", "description", "keyword"})
_SYNTHETIC_ALPHABET = "가상연습자료"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _local_name(tag: object) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _synthetic_mask(value: str) -> str:
    cursor = 0
    result: list[str] = []
    for character in value:
        if character.isspace():
            result.append(character)
        else:
            result.append(_SYNTHETIC_ALPHABET[cursor % len(_SYNTHETIC_ALPHABET)])
            cursor += 1
    return "".join(result)


def _replace_text_tree(element: Any, original_chunks: set[str]) -> int:
    changed = 0
    for node in element.iter():
        if _local_name(node.tag) not in _HUMAN_TEXT_NAMES:
            continue
        for nested in node.iter():
            if nested.text and nested.text.strip():
                original_chunks.add(nested.text)
                nested.text = _synthetic_mask(nested.text)
                changed += 1
            if nested is not node and nested.tail and nested.tail.strip():
                original_chunks.add(nested.tail)
                nested.tail = _synthetic_mask(nested.tail)
                changed += 1
    return changed


def sanitize_document_copy(
    source_path: str | Path,
    destination_path: str | Path,
    *,
    derivative_id: str,
) -> dict[str, Any]:
    """Create an image-free, text-masked HWPX derivative without touching source."""
    if not DERIVATIVE_ID_PATTERN.fullmatch(derivative_id):
        raise ValueError("derivative_id must be an opaque DER identifier")
    source = Path(source_path).expanduser().resolve(strict=True)
    destination = Path(destination_path).expanduser().resolve(strict=False)
    if source == destination:
        raise ValueError("sanitized derivative destination must differ from source")
    if destination.exists():
        raise ValueError("sanitized derivative destination already exists")
    if not source.is_file() or source.suffix.casefold() != ".hwpx":
        raise ValueError("sanitization source must be an HWPX file")
    before = _sha256(source)
    document = HwpxDocument.open(source)
    binary_parts = [name for name in document._package.part_names() if name.startswith("BinData/")]
    if binary_parts:
        document.close()
        raise ValueError("image-bearing documents require a separate visual privacy review")

    # Thumbnails can rasterize private text even in otherwise image-free forms.
    # They are presentation caches, so remove them and their manifest entries.
    preview_parts = [
        name for name in document._package.part_names() if name.startswith("Preview/PrvImage")
    ]
    for item in list(document._package._manifest_items()):
        href = item.get("href", "") or ""
        if "Preview/PrvImage" in href:
            item_id = item.get("id")
            if item_id:
                document._package.remove_manifest_item(item_id)
    for name in preview_parts:
        document._package.delete(name)

    original_chunks: set[str] = set()
    changed = 0
    for section in document.sections:
        changed += _replace_text_tree(section.element, original_chunks)
        section.mark_dirty()
    try:
        manifest = document._package.manifest_tree()
        changed += _replace_text_tree(manifest, original_chunks)
        document._package.set_part(document._package.main_content.full_path, manifest)
    except Exception:
        document.close()
        raise
    if document._package.has_part("Preview/PrvText.txt"):
        document._package.set_part("Preview/PrvText.txt", b"")
    destination.parent.mkdir(parents=True, exist_ok=True)
    document.save_to_path(destination)
    document.close()

    after_source = _sha256(source)
    if after_source != before:
        destination.unlink(missing_ok=True)
        raise RuntimeError("source changed during sanitization")
    open_safety = validate_editor_open_safety(destination)
    if not open_safety.ok:
        destination.unlink(missing_ok=True)
        raise ValueError("sanitized derivative failed editor-open safety")
    output = _sha256(destination)
    reopened = HwpxDocument.open(destination)
    sanitized_text = "\n".join(
        text
        for section in reopened.sections
        for node in section.element.iter()
        if _local_name(node.tag) == "t"
        for text in ("".join(node.itertext()),)
    )
    reopened.close()
    leaked = [chunk for chunk in original_chunks if len(chunk.strip()) >= 4 and chunk in sanitized_text]
    if leaked:
        destination.unlink(missing_ok=True)
        raise ValueError("sanitized derivative retained source text")
    receipt = {
        "schema": "hwpx.sanitized-derivative-receipt/v1",
        "derivativeId": derivative_id,
        "contentSha256": output,
        "sourceUnchanged": True,
        "sanitizedTextSegments": changed,
        "retainedSourceTextSegments": 0,
        "embeddedBinaryParts": 0,
        "metadataScrubbed": True,
        "openSafety": {"ok": True},
        "realHancom": {"checked": False, "status": "unverified"},
    }
    assert_redacted_payload(receipt)
    return receipt


__all__ = ["DERIVATIVE_ID_PATTERN", "sanitize_document_copy"]
