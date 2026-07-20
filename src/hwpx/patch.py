# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import binascii
import html
import io
import re
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from .mutation_report import MutationReport, project_byte_splice, visual_value_from_status
from .quality import QualityPolicy, SavePipeline
from .quality.report import VisualCompleteReport

_PARAGRAPH_RE = re.compile(
    rb"<(?:[A-Za-z_][\w.-]*:)?p\b[^>]*>.*?</(?:[A-Za-z_][\w.-]*:)?p>",
    re.DOTALL,
)
_TEXT_RE = re.compile(
    rb"<(?:[A-Za-z_][\w.-]*:)?t\b[^>/]*>(?P<text>.*?)</(?:[A-Za-z_][\w.-]*:)?t>",
    re.DOTALL,
)
_SELF_CLOSING_TEXT_RE = re.compile(
    rb"<(?P<prefix>(?:[A-Za-z_][\w.-]*:)?)(?P<tag>t)\b(?P<attrs>[^>]*)/>",
    re.DOTALL,
)
_SELF_CLOSING_RUN_RE = re.compile(
    rb"<(?P<prefix>(?:[A-Za-z_][\w.-]*:)?)(?P<tag>run)\b(?P<attrs>[^>]*)/>",
    re.DOTALL,
)
_RUN_OPEN_RE = re.compile(
    rb"<(?P<prefix>(?:[A-Za-z_][\w.-]*:)?)(?P<tag>run)\b(?P<attrs>[^>]*)>",
    re.DOTALL,
)
# Layout cache Hangul emits as <hp:linesegarray> (with <hp:lineseg> children).
# Splicing new text into a paragraph invalidates its cached line geometry, so the
# byte path must drop the cache; otherwise Hangul renders the new text into the
# stale line slots and overlapping glyphs (글자 겹침) result. Matches the container
# form and the (rare) self-closing form, with any namespace prefix, case-insensitive
# to mirror the engine's own case-insensitive strip in opc/package.py.
_LINESEG_ARRAY_RE = re.compile(
    rb"<(?P<ns>(?:[A-Za-z_][\w.-]*:)?)linesegarray\b"
    rb"(?:[^>]*?/>|[^>]*>.*?</(?P=ns)linesegarray>)",
    re.DOTALL | re.IGNORECASE,
)


@dataclass(frozen=True)
class ParagraphTextPatch:
    section_path: str
    paragraph_index: int
    text: str


@dataclass(frozen=True)
class PatchSkipped:
    section_path: str
    paragraph_index: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sectionPath": self.section_path,
            "paragraphIndex": self.paragraph_index,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PatchApplied:
    section_path: str
    paragraph_index: int
    original_text: str
    replacement_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sectionPath": self.section_path,
            "paragraphIndex": self.paragraph_index,
            "originalText": self.original_text,
            "replacementText": self.replacement_text,
        }


@dataclass(frozen=True)
class BytePreservingPatchResult:
    data: bytes
    applied: tuple[PatchApplied, ...]
    skipped: tuple[PatchSkipped, ...]
    changed_parts: tuple[str, ...]
    byte_identical: bool
    zip_method: str
    open_safety: dict[str, Any]
    # The uniform Phase-B report from the single SavePipeline this byte-path write
    # funnelled through (plan §2 Phase B). Additive and defaulted so existing
    # keyword construction is unaffected.
    visual_complete: VisualCompleteReport | None = None

    @property
    def ok(self) -> bool:
        return bool(self.open_safety.get("ok")) and not self.skipped

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "applied": [item.to_dict() for item in self.applied],
            "skipped": [item.to_dict() for item in self.skipped],
            "changedParts": list(self.changed_parts),
            "byteIdentical": self.byte_identical,
            "zipMethod": self.zip_method,
            "openSafety": self.open_safety,
            "visualComplete": (
                None if self.visual_complete is None else self.visual_complete.to_dict()
            ),
        }

    def as_mutation_report(self, *, source: bytes | None = None) -> MutationReport:
        """Project this byte-splice result onto the ``hwpx.mutation-report/v1``
        spine (specs/032 §3). Additive — the fields above are untouched.

        Pass the original *source* bytes to get real changed-part ranges and a
        fully measured preservation summary; without it the projection degrades
        honestly (ranges ``None``, untouched counts zero-verified).
        """

        visual = (
            visual_value_from_status(self.visual_complete.visual_complete_status)
            if self.visual_complete is not None
            else "not_performed"
        )
        return project_byte_splice(
            data=self.data,
            changed_part_names=self.changed_parts,
            byte_identical=self.byte_identical,
            open_safety=self.open_safety,
            visual=visual,
            source=source,
        )


@dataclass(frozen=True)
class _ParagraphSpan:
    index: int
    start: int
    end: int
    payload: bytes


@dataclass(frozen=True)
class _ZipCentralEntry:
    raw: bytes
    filename: str
    header_offset: int
    compress_type: int
    flag_bits: int
    crc: int
    compressed_size: int
    file_size: int
    name: bytes
    extra: bytes
    comment: bytes
    fields: tuple[int, ...]


def paragraph_patch(
    source: str | Path | bytes,
    patches: Sequence[ParagraphTextPatch | Mapping[str, Any]],
    *,
    output_path: str | Path | None = None,
) -> BytePreservingPatchResult:
    """Patch paragraph text through byte-offset splices.

    The supported surface is intentionally narrow: replace the text of existing
    section paragraphs by zero-based paragraph index. Unsupported edits are
    reported in ``skipped`` and never mutate the source bytes.
    """

    source_bytes = _read_source_bytes(source)
    normalized_patches = tuple(_normalize_patch(item) for item in patches)
    if not normalized_patches:
        open_safety, visual_complete = _finalize(source_bytes, output_path, source=source)
        return BytePreservingPatchResult(
            data=source_bytes,
            applied=(),
            skipped=(),
            changed_parts=(),
            byte_identical=True,
            zip_method="none",
            open_safety=open_safety,
            visual_complete=visual_complete,
        )

    with ZipFile(io.BytesIO(source_bytes), "r") as archive:
        parts = {info.filename: archive.read(info.filename) for info in archive.infolist() if not info.is_dir()}

    changed_parts: dict[str, bytes] = {}
    applied: list[PatchApplied] = []
    skipped: list[PatchSkipped] = []
    by_section: dict[str, list[ParagraphTextPatch]] = {}
    for patch in normalized_patches:
        by_section.setdefault(patch.section_path, []).append(patch)

    for section_path, section_patches in by_section.items():
        original_xml = parts.get(section_path)
        if original_xml is None:
            skipped.extend(
                PatchSkipped(section_path, patch.paragraph_index, "section part not found")
                for patch in section_patches
            )
            continue
        updated_xml, section_applied, section_skipped = _patch_section_xml(
            section_path,
            original_xml,
            section_patches,
        )
        applied.extend(section_applied)
        skipped.extend(section_skipped)
        if updated_xml != original_xml:
            changed_parts[section_path] = updated_xml

    if skipped:
        open_safety, visual_complete = _finalize(source_bytes, output_path, source=source)
        return BytePreservingPatchResult(
            data=source_bytes,
            applied=tuple(applied),
            skipped=tuple(skipped),
            changed_parts=(),
            byte_identical=True,
            zip_method="skipped",
            open_safety=open_safety,
            visual_complete=visual_complete,
        )

    if not changed_parts:
        open_safety, visual_complete = _finalize(source_bytes, output_path, source=source)
        return BytePreservingPatchResult(
            data=source_bytes,
            applied=tuple(applied),
            skipped=(),
            changed_parts=(),
            byte_identical=True,
            zip_method="none",
            open_safety=open_safety,
            visual_complete=visual_complete,
        )

    try:
        output = _patch_zip_entries(source_bytes, changed_parts)
        zip_method = "partial-local-record-copy"
    except ValueError:
        output = _rewrite_zip_entries(source_bytes, changed_parts)
        zip_method = "zipfile-rewrite-fallback"

    open_safety, visual_complete = _finalize(output, output_path, source=source)
    return BytePreservingPatchResult(
        data=output,
        applied=tuple(applied),
        skipped=(),
        changed_parts=tuple(changed_parts),
        byte_identical=output == source_bytes,
        zip_method=zip_method,
        open_safety=open_safety,
        visual_complete=visual_complete,
    )


def _read_source_bytes(source: str | Path | bytes) -> bytes:
    if isinstance(source, bytes):
        return source
    return Path(source).read_bytes()


def _finalize(
    payload: bytes,
    output_path: str | Path | None,
    *,
    source: str | Path | bytes,
) -> tuple[dict[str, Any], VisualCompleteReport]:
    """Funnel the produced bytes through the single SavePipeline (byte path).

    The lineseg-stripping ZIP-splice above is untouched; this performs only the
    open-safety gate + the (now atomic) write + the uniform ``VisualCompleteReport``,
    so the byte path no longer bypasses the gate (plan §2 Phase B, "zero bypass").
    ``publish="always"`` preserves the byte path's historical behaviour of writing
    the produced bytes regardless of the gate verdict; ``open_safety`` is surfaced
    exactly as the prior ``validate_editor_open_safety(...).to_dict()`` did.
    """

    before = source if isinstance(source, (str, Path)) else None
    report = SavePipeline().run(
        payload,
        output_path=output_path,
        quality=QualityPolicy.transparent(),
        before=before,
        publish="always",
        source_label="patch.paragraph_patch",
    )
    open_safety = report.open_safety.detail or {
        "ok": report.open_safety.ok,
        "summary": report.open_safety.summary,
    }
    return open_safety, report


def _normalize_patch(item: ParagraphTextPatch | Mapping[str, Any]) -> ParagraphTextPatch:
    if isinstance(item, ParagraphTextPatch):
        return item
    section_path = str(item.get("section_path") or item.get("sectionPath") or "Contents/section0.xml")
    paragraph_index = item.get("paragraph_index", item.get("paragraphIndex"))
    if paragraph_index is None:
        raise ValueError("paragraph patch requires paragraph_index/paragraphIndex")
    text = item.get("text")
    if text is None:
        raise ValueError("paragraph patch requires text")
    return ParagraphTextPatch(
        section_path=section_path,
        paragraph_index=int(paragraph_index),
        text=str(text),
    )


def _paragraph_spans(section_xml: bytes) -> list[_ParagraphSpan]:
    return [
        _ParagraphSpan(index=index, start=match.start(), end=match.end(), payload=match.group(0))
        for index, match in enumerate(_PARAGRAPH_RE.finditer(section_xml))
    ]


def _strip_paragraph_layout_cache(paragraph: bytes) -> bytes:
    """Remove a paragraph's ``<hp:linesegarray>`` layout cache.

    Run after a text splice: the cached line geometry describes the *old* text, so
    leaving it in place makes Hangul lay the new text onto stale line slots and
    overlap (글자 겹침). Stripping it forces a recompute on open.
    """

    return _LINESEG_ARRAY_RE.sub(b"", paragraph)


def _patch_section_xml(
    section_path: str,
    section_xml: bytes,
    patches: Sequence[ParagraphTextPatch],
) -> tuple[bytes, list[PatchApplied], list[PatchSkipped]]:
    spans = {span.index: span for span in _paragraph_spans(section_xml)}
    edits: list[tuple[int, int, bytes]] = []
    applied: list[PatchApplied] = []
    skipped: list[PatchSkipped] = []

    for patch in patches:
        if "\n" in patch.text or "\r" in patch.text:
            skipped.append(
                PatchSkipped(section_path, patch.paragraph_index, "line break insertion is unsupported")
            )
            continue
        span = spans.get(patch.paragraph_index)
        if span is None:
            skipped.append(PatchSkipped(section_path, patch.paragraph_index, "paragraph index not found"))
            continue
        edit = _text_edit_for_paragraph(span.payload, patch.text)
        if edit is None:
            skipped.append(
                PatchSkipped(section_path, patch.paragraph_index, "paragraph has no patchable hp:run")
            )
            continue
        start, end, replacement, original_text = edit
        if original_text == patch.text:
            continue
        # Apply the text splice within the paragraph, then strip its now-stale
        # layout cache and replace the whole paragraph span. This guarantees the
        # patched paragraph carries no <hp:linesegarray>, so Hangul recomputes the
        # line layout for the new text instead of reusing the old geometry.
        patched_paragraph = _apply_edits(span.payload, [(start, end, replacement)])
        patched_paragraph = _strip_paragraph_layout_cache(patched_paragraph)
        edits.append((span.start, span.end, patched_paragraph))
        applied.append(
            PatchApplied(
                section_path=section_path,
                paragraph_index=patch.paragraph_index,
                original_text=original_text,
                replacement_text=patch.text,
            )
        )

    if skipped or not edits:
        return section_xml, applied, skipped
    return _apply_edits(section_xml, edits), applied, skipped


def _text_edit_for_paragraph(paragraph: bytes, replacement_text: str) -> tuple[int, int, bytes, str] | None:
    escaped = html.escape(replacement_text, quote=False).encode("utf-8")
    text_matches = list(_TEXT_RE.finditer(paragraph))
    if text_matches:
        original_text = "".join(
            html.unescape(match.group("text").decode("utf-8", "replace"))
            for match in text_matches
        )
        first = text_matches[0]
        edits = [(first.start("text"), first.end("text"), escaped)]
        edits.extend((match.start("text"), match.end("text"), b"") for match in text_matches[1:])
        updated = _apply_edits(paragraph, edits)
        return 0, len(paragraph), updated, original_text

    self_closing_text = _SELF_CLOSING_TEXT_RE.search(paragraph)
    if self_closing_text is not None:
        prefix = self_closing_text.group("prefix")
        attrs = self_closing_text.group("attrs").rstrip()
        tag = prefix + b"t"
        replacement = b"<" + tag + attrs + b">" + escaped + b"</" + tag + b">"
        return self_closing_text.start(), self_closing_text.end(), replacement, ""

    self_closing_run = _SELF_CLOSING_RUN_RE.search(paragraph)
    if self_closing_run is not None:
        prefix = self_closing_run.group("prefix")
        attrs = self_closing_run.group("attrs").rstrip()
        run_tag = prefix + b"run"
        text_tag = prefix + b"t"
        replacement = (
            b"<"
            + run_tag
            + attrs
            + b"><"
            + text_tag
            + b">"
            + escaped
            + b"</"
            + text_tag
            + b"></"
            + run_tag
            + b">"
        )
        return self_closing_run.start(), self_closing_run.end(), replacement, ""

    run_open = _RUN_OPEN_RE.search(paragraph)
    if run_open is None:
        return None
    prefix = run_open.group("prefix")
    text_tag = prefix + b"t"
    insertion = b"<" + text_tag + b">" + escaped + b"</" + text_tag + b">"
    return run_open.end(), run_open.end(), insertion, ""


def _apply_edits(payload: bytes, edits: Sequence[tuple[int, int, bytes]]) -> bytes:
    result = bytearray()
    cursor = 0
    for start, end, replacement in sorted(edits, key=lambda item: item[0]):
        if start < cursor:
            raise ValueError("overlapping byte edits are not supported")
        result.extend(payload[cursor:start])
        result.extend(replacement)
        cursor = end
    result.extend(payload[cursor:])
    return bytes(result)


def _rewrite_zip_entries(source: bytes, replacements: Mapping[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(io.BytesIO(source), "r") as src:
        with ZipFile(buffer, "w") as dst:
            for info in src.infolist():
                payload = replacements.get(info.filename, src.read(info.filename))
                dst.writestr(info, payload)
    return buffer.getvalue()


def _find_eocd(source: bytes) -> tuple[int, bytes]:
    start = max(0, len(source) - (65535 + 22))
    offset = source.rfind(b"PK\x05\x06", start)
    if offset < 0 or offset + 22 > len(source):
        raise ValueError("ZIP EOCD not found")
    comment_length = struct.unpack_from("<H", source, offset + 20)[0]
    end = offset + 22 + comment_length
    if end > len(source):
        raise ValueError("ZIP EOCD comment is truncated")
    return offset, source[offset:end]


def _parse_central_directory(source: bytes) -> tuple[list[_ZipCentralEntry], int, int, bytes]:
    eocd_offset, eocd = _find_eocd(source)
    (
        _signature,
        disk_no,
        cd_disk,
        disk_entries,
        total_entries,
        cd_size,
        cd_offset,
        _comment_len,
    ) = struct.unpack_from("<IHHHHIIH", eocd, 0)
    if disk_no != 0 or cd_disk != 0 or disk_entries != total_entries:
        raise ValueError("multi-disk ZIP archives are unsupported")
    if total_entries == 0xFFFF or cd_size == 0xFFFFFFFF or cd_offset == 0xFFFFFFFF:
        raise ValueError("ZIP64 central directories are unsupported")
    if cd_offset + cd_size > eocd_offset:
        raise ValueError("central directory offsets are invalid")

    entries: list[_ZipCentralEntry] = []
    cursor = cd_offset
    end = cd_offset + cd_size
    while cursor < end:
        if source[cursor:cursor + 4] != b"PK\x01\x02":
            raise ValueError("central directory entry signature mismatch")
        fixed = struct.unpack_from("<IHHHHHHIIIHHHHHII", source, cursor)
        (
            _sig,
            _ver_made,
            _ver_needed,
            flag_bits,
            compress_type,
            _mtime,
            _mdate,
            crc,
            compressed_size,
            file_size,
            name_len,
            extra_len,
            comment_len,
            _disk_start,
            _internal_attr,
            _external_attr,
            header_offset,
        ) = fixed
        entry_end = cursor + 46 + name_len + extra_len + comment_len
        name = source[cursor + 46:cursor + 46 + name_len]
        extra = source[cursor + 46 + name_len:cursor + 46 + name_len + extra_len]
        comment = source[cursor + 46 + name_len + extra_len:entry_end]
        entries.append(
            _ZipCentralEntry(
                raw=source[cursor:entry_end],
                filename=name.decode("utf-8"),
                header_offset=header_offset,
                compress_type=compress_type,
                flag_bits=flag_bits,
                crc=crc,
                compressed_size=compressed_size,
                file_size=file_size,
                name=name,
                extra=extra,
                comment=comment,
                fields=fixed,
            )
        )
        cursor = entry_end
    if len(entries) != total_entries:
        raise ValueError("central directory entry count mismatch")
    return entries, cd_offset, cd_size, eocd


def _patch_zip_entries(source: bytes, replacements: Mapping[str, bytes]) -> bytes:
    entries, cd_start, _cd_size, eocd = _parse_central_directory(source)
    missing = set(replacements) - {entry.filename for entry in entries}
    if missing:
        raise ValueError(f"replacement entry not found: {sorted(missing)!r}")

    local_order = sorted(entries, key=lambda entry: entry.header_offset)
    local_ends: dict[str, int] = {}
    for index, entry in enumerate(local_order):
        next_offset = local_order[index + 1].header_offset if index + 1 < len(local_order) else cd_start
        if entry.header_offset >= next_offset:
            raise ValueError("local file header offsets are invalid")
        local_ends[entry.filename] = next_offset

    output = bytearray()
    new_offsets: dict[str, int] = {}
    new_stats: dict[str, tuple[int, int, int, int]] = {}
    for entry in local_order:
        new_offsets[entry.filename] = len(output)
        replacement = replacements.get(entry.filename)
        if replacement is None:
            output.extend(source[entry.header_offset:local_ends[entry.filename]])
            new_stats[entry.filename] = (
                entry.flag_bits,
                entry.crc,
                entry.compressed_size,
                entry.file_size,
            )
            continue
        compressed = _compress_for_entry(replacement, entry.compress_type)
        crc = binascii.crc32(replacement) & 0xFFFFFFFF
        flags = entry.flag_bits & ~0x08
        output.extend(
            _local_header(
                entry,
                flags=flags,
                crc=crc,
                compressed_size=len(compressed),
                file_size=len(replacement),
            )
        )
        output.extend(compressed)
        new_stats[entry.filename] = (flags, crc, len(compressed), len(replacement))

    cd_offset = len(output)
    for entry in entries:
        flags, crc, compressed_size, file_size = new_stats[entry.filename]
        output.extend(
            _central_header(
                entry,
                flags=flags,
                crc=crc,
                compressed_size=compressed_size,
                file_size=file_size,
                header_offset=new_offsets[entry.filename],
            )
        )
    cd_size = len(output) - cd_offset
    output.extend(_eocd_with_offsets(eocd, cd_size=cd_size, cd_offset=cd_offset))
    return bytes(output)


def _compress_for_entry(payload: bytes, compress_type: int) -> bytes:
    if compress_type == ZIP_STORED:
        return payload
    if compress_type == ZIP_DEFLATED:
        compressor = zlib.compressobj(level=6, wbits=-15)
        return compressor.compress(payload) + compressor.flush()
    raise ValueError(f"unsupported ZIP compression method: {compress_type}")


def _local_header(
    entry: _ZipCentralEntry,
    *,
    flags: int,
    crc: int,
    compressed_size: int,
    file_size: int,
) -> bytes:
    (
        _sig,
        _ver_made,
        ver_needed,
        _flags,
        compress_type,
        mtime,
        mdate,
        _crc,
        _compressed_size,
        _file_size,
        _name_len,
        _extra_len,
        _comment_len,
        _disk_start,
        _internal_attr,
        _external_attr,
        _header_offset,
    ) = entry.fields
    return (
        struct.pack(
            "<IHHHHHIIIHH",
            0x04034B50,
            ver_needed,
            flags,
            compress_type,
            mtime,
            mdate,
            crc,
            compressed_size,
            file_size,
            len(entry.name),
            len(entry.extra),
        )
        + entry.name
        + entry.extra
    )


def _central_header(
    entry: _ZipCentralEntry,
    *,
    flags: int,
    crc: int,
    compressed_size: int,
    file_size: int,
    header_offset: int,
) -> bytes:
    (
        _sig,
        ver_made,
        ver_needed,
        _flags,
        compress_type,
        mtime,
        mdate,
        _crc,
        _compressed_size,
        _file_size,
        _name_len,
        _extra_len,
        _comment_len,
        disk_start,
        internal_attr,
        external_attr,
        _header_offset,
    ) = entry.fields
    return (
        struct.pack(
            "<IHHHHHHIIIHHHHHII",
            0x02014B50,
            ver_made,
            ver_needed,
            flags,
            compress_type,
            mtime,
            mdate,
            crc,
            compressed_size,
            file_size,
            len(entry.name),
            len(entry.extra),
            len(entry.comment),
            disk_start,
            internal_attr,
            external_attr,
            header_offset,
        )
        + entry.name
        + entry.extra
        + entry.comment
    )


def _eocd_with_offsets(eocd: bytes, *, cd_size: int, cd_offset: int) -> bytes:
    if cd_size > 0xFFFFFFFF or cd_offset > 0xFFFFFFFF:
        raise ValueError("ZIP64 output would be required")
    updated = bytearray(eocd)
    struct.pack_into("<II", updated, 12, cd_size, cd_offset)
    return bytes(updated)


__all__ = [
    "BytePreservingPatchResult",
    "ParagraphTextPatch",
    "PatchApplied",
    "PatchSkipped",
    "paragraph_patch",
]
