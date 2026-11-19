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
from typing import TYPE_CHECKING, Any, Mapping, Sequence
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from .opc.package import duplicate_entry_names, refuse_duplicate_entry_names
from .opc.security import guard_zip_file, read_member, read_zip_members
from .mutation_report import MutationReport, project_byte_splice, visual_value_from_status
from .oxml.namespaces import NAMESPACE_URIS
from .quality import QualityPolicy, SavePipeline
from .quality.report import VisualCompleteReport

if TYPE_CHECKING:
    from .opc.zip_records import CentralEntry

_PARAGRAPH_RE = re.compile(
    rb"<(?:[A-Za-z_][\w.-]*:)?p\b[^>]*>.*?</(?:[A-Za-z_][\w.-]*:)?p>",
    re.DOTALL,
)
_TEXT_RE = re.compile(
    rb"<(?P<prefix>(?:[A-Za-z_][\w.-]*:)?)t\b[^>/]*>(?P<text>.*?)</(?:[A-Za-z_][\w.-]*:)?t>",
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
#: Markup between XML character data: comments, CDATA, processing instructions,
#: declarations and tags. A quoted attribute value may hold ``>``.
_MARKUP_PATTERN = r"<!--.*?-->|<!\[CDATA\[.*?\]\]>|<\?.*?\?>|<![^>]*>|<(?:[^>\"']|\"[^\"]*\"|'[^']*')*>"


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
    #: Edits that matched but were thrown away because another patch skipped.
    #:
    #: This family is all-or-nothing: one skip discards the whole set. Those
    #: edits used to be reported in ``applied``, which said the operation had
    #: done something it had not. They are reported here instead, so the
    #: diagnostic value survives without the receipt claiming work.
    discarded: tuple[PatchApplied, ...] = ()
    #: True when ``output_path`` received the unmodified source bytes.
    #:
    #: The byte-splice family writes ``output_path`` even when everything was
    #: skipped, so the file exists and opens and is simply not edited. That is
    #: documented behaviour, kept for consistency across the op family; this
    #: flag makes it impossible to mistake the written file for an edited one
    #: without reading prose.
    output_is_source_copy: bool = False
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
            "discarded": [item.to_dict() for item in self.discarded],
            "outputIsSourceCopy": self.output_is_source_copy,
        }

    def as_mutation_report(self, *, source: bytes | str | Path | None = None) -> MutationReport:
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

    Only the paragraph's own text and its own ``hp:linesegarray`` layout cache
    change: a table or text box inside it keeps its paragraphs, their text and
    their caches byte for byte. An archive holding one entry name twice is
    refused before anything is written (``save-duplicate-entry-names``).
    """

    source_bytes = _read_source_bytes(source)
    normalized_patches = tuple(_normalize_patch(item) for item in patches)
    if not normalized_patches:
        # The early return still hands the source to the save pipeline, so it has
        # to clear the same limits as the patching path below.
        with ZipFile(io.BytesIO(source_bytes), "r") as archive:
            guard_zip_file(archive)
            refuse_duplicate_entry_names(duplicate_entry_names(archive.infolist()))
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
        guard_zip_file(archive)
        refuse_duplicate_entry_names(duplicate_entry_names(archive.infolist()))
        parts = read_zip_members(archive)

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
        # All-or-nothing: one skip discards the whole set. Report the matched
        # edits as discarded rather than applied — nothing was applied.
        open_safety, visual_complete = _finalize(source_bytes, output_path, source=source)
        return BytePreservingPatchResult(
            data=source_bytes,
            applied=(),
            skipped=tuple(skipped),
            changed_parts=(),
            byte_identical=True,
            zip_method="skipped",
            open_safety=open_safety,
            visual_complete=visual_complete,
            discarded=tuple(applied),
            output_is_source_copy=output_path is not None,
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

    # Every byte patch built on this module (body_patch, table_patch) ends here before it writes: an
    # archive holding one name twice is refused, as the document save refuses it. The payload holds the
    # source's names (a patch changes contents, never the entry list), so it answers for the source.
    with ZipFile(io.BytesIO(payload), "r") as archive:
        refuse_duplicate_entry_names(duplicate_entry_names(archive.infolist()))
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


_MARKUP_BYTES_RE = re.compile(_MARKUP_PATTERN.encode("ascii"), re.DOTALL)
_TAG_NAME_BYTES_RE = re.compile(rb"<(/?)([^\s/>]+)")


def _paragraph_extent(section_xml: bytes, start: int) -> tuple[int, list[tuple[int, int]]] | None:
    """Where the paragraph that opens at *start* ends, and the spans of the paragraphs nested in it
    (table cells, text boxes) -- ``None`` when it never closes.

    ``_PARAGRAPH_RE`` finds a paragraph's start, but its match stops at the first ``</p>``, which for a
    paragraph holding a table is a cell's. The element is followed to its own end here.
    """

    depth = 0
    nested: list[tuple[int, int]] = []
    nested_start: int | None = None
    for markup in _MARKUP_BYTES_RE.finditer(section_xml, start):
        token = markup.group(0)
        if token.startswith((b"<!", b"<?")):
            continue
        name = _TAG_NAME_BYTES_RE.match(token)
        if name is None or name.group(2).rpartition(b":")[2] != b"p":
            continue
        if name.group(1):
            depth -= 1
            if depth == 1 and nested_start is not None:
                nested.append((nested_start, markup.end()))
                nested_start = None
            if depth == 0:
                return markup.end(), nested
        elif token.endswith(b"/>"):
            if depth == 0:
                return markup.end(), nested
            if depth == 1:
                nested.append((markup.start(), markup.end()))
        else:
            depth += 1
            if depth == 2:
                nested_start = markup.start()
    return None


def _own_paragraph_edits(
    paragraph: bytes, nested: Sequence[tuple[int, int]], replacement_text: str
) -> tuple[list[tuple[int, int, bytes]], str] | None:
    """The splices that make *replacement_text* a paragraph's own text and drop its own layout cache.

    *nested* are the spans (relative to *paragraph*) of the paragraphs inside it; their text, runs and
    caches are not the paragraph's and are left as they are. ``None`` when the paragraph has no run of
    its own to hold text. The second value is the paragraph's own text before the edit.
    """

    def own(match: re.Match[bytes]) -> bool:
        return not any(start <= match.start() < end for start, end in nested)

    edits: list[tuple[int, int, bytes]] = []
    text_matches = [match for match in _TEXT_RE.finditer(paragraph) if own(match)]
    if text_matches:
        original_text = "".join(
            html.unescape(match.group("text").decode("utf-8", "replace"))
            for match in text_matches
        )
        first = text_matches[0]
        edits.append(
            (first.start("text"), first.end("text"), _escaped_text(replacement_text, first.group("prefix")))
        )
        edits.extend((match.start("text"), match.end("text"), b"") for match in text_matches[1:])
    else:
        original_text = ""
        self_closing_text = next((m for m in _SELF_CLOSING_TEXT_RE.finditer(paragraph) if own(m)), None)
        self_closing_run = next((m for m in _SELF_CLOSING_RUN_RE.finditer(paragraph) if own(m)), None)
        run_open = next((m for m in _RUN_OPEN_RE.finditer(paragraph) if own(m)), None)
        if self_closing_text is not None:
            prefix = self_closing_text.group("prefix")
            tag = prefix + b"t"
            edits.append(
                (
                    self_closing_text.start(),
                    self_closing_text.end(),
                    b"<" + tag + self_closing_text.group("attrs").rstrip() + b">"
                    + _escaped_text(replacement_text, prefix) + b"</" + tag + b">",
                )
            )
        elif self_closing_run is not None:
            prefix = self_closing_run.group("prefix")
            run_tag, text_tag = prefix + b"run", prefix + b"t"
            edits.append(
                (
                    self_closing_run.start(),
                    self_closing_run.end(),
                    b"<" + run_tag + self_closing_run.group("attrs").rstrip() + b"><" + text_tag + b">"
                    + _escaped_text(replacement_text, prefix) + b"</" + text_tag + b"></" + run_tag + b">",
                )
            )
        elif run_open is not None:
            prefix = run_open.group("prefix")
            text_tag = prefix + b"t"
            edits.append(
                (
                    run_open.end(),
                    run_open.end(),
                    b"<" + text_tag + b">" + _escaped_text(replacement_text, prefix) + b"</" + text_tag + b">",
                )
            )
        else:
            return None
    # The paragraph's own cache describes its old text (글자 겹침 if kept); a nested paragraph's
    # cache describes text this edit does not touch.
    edits.extend(
        (match.start(), match.end(), b"") for match in _LINESEG_ARRAY_RE.finditer(paragraph) if own(match)
    )
    return edits, original_text


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
        span = spans.get(patch.paragraph_index)
        if span is None:
            skipped.append(PatchSkipped(section_path, patch.paragraph_index, "paragraph index not found"))
            continue
        extent = _paragraph_extent(section_xml, span.start)
        if extent is None:
            skipped.append(PatchSkipped(section_path, patch.paragraph_index, "paragraph does not close"))
            continue
        end, nested = extent
        paragraph = section_xml[span.start:end]
        own = _own_paragraph_edits(
            paragraph, [(start - span.start, stop - span.start) for start, stop in nested], patch.text
        )
        if own is None:
            skipped.append(
                PatchSkipped(section_path, patch.paragraph_index, "paragraph has no patchable hp:run")
            )
            continue
        paragraph_edits, original_text = own
        if original_text == patch.text:
            continue
        # Only the paragraph's own text and its own <hp:linesegarray> change, so Hangul recomputes the
        # line layout for the new text; paragraphs nested in it (table cells) keep their bytes.
        edits.extend((span.start + start, span.start + stop, data) for start, stop, data in paragraph_edits)
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


#: A tab, or a line break typed as "\n", "\r\n" or "\r".
_TEXT_MARK_SPLIT_RE = re.compile(r"(\t|\r\n|\r|\n)")


def _escaped_text(text: str, prefix: bytes) -> bytes:
    """*text* escaped for ``hp:t``, each tab written as an ``hp:tab`` element and
    each line break as an ``hp:lineBreak``, the way Hancom writes them.

    Hancom reads a tab only as that element; a raw tab character inside
    ``hp:t`` keeps it laying the paragraph out forever.
    """

    tab, line_break = b"<" + prefix + b"tab/>", b"<" + prefix + b"lineBreak/>"
    return b"".join(
        (tab if part == "\t" else line_break) if index % 2 else html.escape(part, quote=False).encode("utf-8")
        for index, part in enumerate(_TEXT_MARK_SPLIT_RE.split(text))
    )


def _text_edit_for_paragraph(paragraph: bytes, replacement_text: str) -> tuple[int, int, bytes, str] | None:
    text_matches = list(_TEXT_RE.finditer(paragraph))
    if text_matches:
        original_text = "".join(
            html.unescape(match.group("text").decode("utf-8", "replace"))
            for match in text_matches
        )
        first = text_matches[0]
        escaped = _escaped_text(replacement_text, first.group("prefix"))
        edits = [(first.start("text"), first.end("text"), escaped)]
        edits.extend((match.start("text"), match.end("text"), b"") for match in text_matches[1:])
        updated = _apply_edits(paragraph, edits)
        return 0, len(paragraph), updated, original_text

    self_closing_text = _SELF_CLOSING_TEXT_RE.search(paragraph)
    if self_closing_text is not None:
        prefix = self_closing_text.group("prefix")
        attrs = self_closing_text.group("attrs").rstrip()
        tag = prefix + b"t"
        escaped = _escaped_text(replacement_text, prefix)
        replacement = b"<" + tag + attrs + b">" + escaped + b"</" + tag + b">"
        return self_closing_text.start(), self_closing_text.end(), replacement, ""

    self_closing_run = _SELF_CLOSING_RUN_RE.search(paragraph)
    if self_closing_run is not None:
        prefix = self_closing_run.group("prefix")
        attrs = self_closing_run.group("attrs").rstrip()
        run_tag = prefix + b"run"
        text_tag = prefix + b"t"
        escaped = _escaped_text(replacement_text, prefix)
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
    insertion = b"<" + text_tag + b">" + _escaped_text(replacement_text, prefix) + b"</" + text_tag + b">"
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
    """Write every entry of *source* again with ``zipfile``, *replacements* in place of their contents.

    The way out for an archive whose records cannot be moved one by one (ZIP64, bytes before the first
    record, ...). What the file says is kept all the same: each entry's ZipInfo (compression ``mimetype``
    included), the central directory's order, the order the records lie in, and the archive comment. An
    archive holding one name twice is refused (``save-duplicate-entry-names``): a replacement by name
    would land on every entry of that name."""

    from .opc.zip_records import ZipRecordsUnsupported, lay_out_records

    buffer = io.BytesIO()
    with ZipFile(io.BytesIO(source), "r") as src:
        # Also reached directly by the public rewrite_package_parts(), so the
        # entry-count, total-size and ratio limits have to be applied here too.
        guard_zip_file(src)
        infos = src.infolist()
        refuse_duplicate_entry_names(duplicate_entry_names(infos))
        # Read before writing: writestr() changes the ZipInfo it is given.
        physical = [info.filename for info in sorted(infos, key=lambda info: info.header_offset)]
        with ZipFile(buffer, "w") as dst:
            for info in infos:
                payload = replacements.get(info.filename, read_member(src, info))
                dst.writestr(info, payload)
            dst.comment = src.comment
    written = buffer.getvalue()
    try:
        return lay_out_records(written, physical)
    except ZipRecordsUnsupported:
        return written


def paragraph_chunks(section: bytes) -> list[bytes]:
    """Return paragraph XML chunks in document order, including nested cells."""

    return [match.group(0) for match in _PARAGRAPH_RE.finditer(section)]


def rewrite_package_parts(
    source: bytes,
    replacements: Mapping[str, bytes],
) -> bytes:
    """Rewrite selected ZIP members while preserving names and ZipInfo metadata.

    This is the explicit whole-package fallback for callers that already own
    complete replacement member bytes. Prefer higher-level patch APIs when a
    byte-splice contract is available. Every entry is compressed again; the
    entries' ZipInfo, both entry orders and the archive comment stay. An archive
    holding one name twice is refused (``save-duplicate-entry-names``).
    """

    return _rewrite_zip_entries(source, replacements)


_MARKUP_RE = re.compile(_MARKUP_PATTERN, re.DOTALL)
_XML_REFERENCE_RE = re.compile(r"&(#x[0-9A-Fa-f]+|#[0-9]+|lt|gt|amp|quot|apos);")
_XML_ENTITIES = {"lt": "<", "gt": ">", "amp": "&", "quot": '"', "apos": "'"}
_TAG_NAME_RE = re.compile(r"<(/?)([^\s/>]+)")
#: One attribute of a start tag. Walking a tag attribute by attribute keeps an
#: ``xmlns`` that only appears inside another attribute's value from counting.
_ATTRIBUTE_RE = re.compile(r"""\s+([^\s=/>]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_PARAGRAPH_NAMESPACES = frozenset(NAMESPACE_URIS["paragraph"].values())


@dataclass(frozen=True)
class PackageTextReplaceResult:
    """What :func:`replace_package_text` changed, and whether the output may be written."""

    data: bytes
    #: Every ZIP entry of the package, in order.
    entries: tuple[str, ...]
    scanned_parts: tuple[str, ...]
    changed_parts: tuple[str, ...]
    #: Scanned parts left untouched because they are not UTF-8.
    undecodable_parts: tuple[str, ...]
    replacements: int
    layout_caches_removed: int
    byte_identical: bool
    zip_method: str
    open_safety: dict[str, Any]
    visual_complete: VisualCompleteReport | None = None
    #: Where the output was written; ``None`` when no path was given or the gate failed.
    output_path: str | None = None

    @property
    def ok(self) -> bool:
        return bool(self.open_safety.get("ok"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "entries": list(self.entries),
            "scannedParts": list(self.scanned_parts),
            "changedParts": list(self.changed_parts),
            "undecodableParts": list(self.undecodable_parts),
            "replacements": self.replacements,
            "layoutCachesRemoved": self.layout_caches_removed,
            "byteIdentical": self.byte_identical,
            "zipMethod": self.zip_method,
            "openSafety": self.open_safety,
            "visualComplete": (
                None if self.visual_complete is None else self.visual_complete.to_dict()
            ),
            "outputPath": self.output_path,
        }

    def as_mutation_report(self, *, source: bytes | str | Path | None = None) -> MutationReport:
        """Project this result onto the ``hwpx.mutation-report/v1`` spine, as
        :meth:`BytePreservingPatchResult.as_mutation_report` does.

        Pass the original *source* to get real changed-part ranges and a
        measured preservation summary; without it ranges are ``None``.
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


def _unescape_xml_text(text: str) -> str:
    def resolve(match: re.Match[str]) -> str:
        name = match.group(1)
        if name.startswith("#x"):
            return chr(int(name[2:], 16))
        if name.startswith("#"):
            return chr(int(name[1:]))
        return _XML_ENTITIES[name]

    return _XML_REFERENCE_RE.sub(resolve, text)


def _escape_xml_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _replace_in_text_nodes(xml: str, replacements: Mapping[str, str]) -> tuple[str, int, list[int]]:
    """Replace inside character data only; tags, attributes, comments and CDATA stay as they are.

    Returns the new text, the number of replacements, and where in the new text each changed run of
    character data starts (so the caller can tell which paragraph's text changed).
    """

    pieces: list[str] = []
    changed_at: list[int] = []
    written = 0
    count = 0
    cursor = 0
    for markup in (*_MARKUP_RE.finditer(xml), None):
        end = len(xml) if markup is None else markup.start()
        segment = xml[cursor:end]
        if segment:
            text = _unescape_xml_text(segment)
            replaced = text
            for old, new in replacements.items():
                hits = replaced.count(old)
                if hits:
                    replaced = replaced.replace(old, new)
                    count += hits
            piece = segment if replaced == text else _escape_xml_text(replaced)
            if piece != segment:
                changed_at.append(written)
            pieces.append(piece)
            written += len(piece)
        if markup is None:
            break
        pieces.append(markup.group(0))
        written += len(markup.group(0))
        cursor = markup.end()
    return "".join(pieces), count, changed_at


def _namespace_declarations(tag: str, start: int) -> dict[str, str]:
    """The ``xmlns`` / ``xmlns:prefix`` attributes of a start *tag*, read from *start*."""

    declared: dict[str, str] = {}
    attribute = _ATTRIBUTE_RE.match(tag, start)
    while attribute is not None:
        name, double, single = attribute.groups()
        if name == "xmlns" or name.startswith("xmlns:"):
            declared[name[6:]] = _unescape_xml_text(double if double is not None else single)
        attribute = _ATTRIBUTE_RE.match(tag, attribute.end())
    return declared


def _strip_layout_caches(xml: str, changed_at: Sequence[int]) -> tuple[str, int]:
    """Cut the ``linesegarray`` layout cache of each paragraph whose own text changed.

    *changed_at* are the offsets in *xml* where changed character data starts. Text belongs to the
    innermost paragraph (``p`` in the paragraph namespace) around it, so a paragraph whose words changed
    loses its cache and a table-cell paragraph inside it, whose words did not, keeps its own -- and the
    other way round. Walks the same markup tokens as :func:`_replace_in_text_nodes`, so text that only
    looks like the element -- inside CDATA, a comment, a processing instruction or an attribute value --
    is never matched. Prefixes resolve through the ``xmlns`` declarations in scope. Bytes outside the
    removed elements stay as they are; an element that never closes is left alone.
    """

    # (cache start, cache end, start of the paragraph that holds it)
    caches: list[tuple[int, int, int | None]] = []
    changed_paragraphs: set[int] = set()
    pending = sorted(changed_at)
    next_change = 0
    # One entry per open element: the namespace declarations it adds, and its start when it is a paragraph.
    scopes: list[tuple[dict[str, str], int | None]] = []
    paragraphs: list[int] = []  # starts of the open paragraphs, innermost last
    cut_start: int | None = None
    cut_depth = 0
    cut_owner: int | None = None

    def resolve(prefix: str, declared: dict[str, str]) -> str | None:
        uri = declared.get(prefix)
        if uri is None:
            uri = next((scope[prefix] for scope, _ in reversed(scopes) if prefix in scope), None)
        return uri

    for markup in _MARKUP_RE.finditer(xml):
        # Changed text before this token belongs to the innermost open paragraph.
        while next_change < len(pending) and pending[next_change] < markup.start():
            if paragraphs:
                changed_paragraphs.add(paragraphs[-1])
            next_change += 1
        token = markup.group(0)
        name = _TAG_NAME_RE.match(token)
        if name is None or token.startswith(("<!", "<?")):
            continue
        if name.group(1):
            if scopes:
                _, paragraph_start = scopes.pop()
                if paragraph_start is not None and paragraphs:
                    paragraphs.pop()
            if cut_start is not None and len(scopes) == cut_depth:
                caches.append((cut_start, markup.end(), cut_owner))
                cut_start = None
            continue
        declared = _namespace_declarations(token, name.end())
        self_closing = token.endswith("/>")
        prefix, _, local = name.group(2).rpartition(":")
        in_paragraph_namespace = resolve(prefix, declared) in _PARAGRAPH_NAMESPACES
        if cut_start is None and local.lower() == "linesegarray" and in_paragraph_namespace:
            owner = paragraphs[-1] if paragraphs else None
            if self_closing:
                caches.append((markup.start(), markup.end(), owner))
                continue
            cut_start, cut_depth, cut_owner = markup.start(), len(scopes), owner
        if not self_closing:
            is_paragraph = local == "p" and in_paragraph_namespace
            scopes.append((declared, markup.start() if is_paragraph else None))
            if is_paragraph:
                paragraphs.append(markup.start())

    spans = [(start, end) for start, end, owner in caches if owner is not None and owner in changed_paragraphs]
    if not spans:
        return xml, 0
    pieces: list[str] = []
    cursor = 0
    for start, end in spans:
        pieces.append(xml[cursor:start])
        cursor = end
    pieces.append(xml[cursor:])
    return "".join(pieces), len(spans)


def _gate_and_publish(
    payload: bytes,
    output_path: str | Path | None,
    *,
    source: str | Path | bytes,
    source_label: str,
) -> tuple[dict[str, Any], VisualCompleteReport | None]:
    """Run the open-safety gate and write *output_path* only when it passes.

    A package the gate cannot even parse counts as failing it: nothing is
    written and the reason is the open-safety summary.
    """

    try:
        report = SavePipeline().run(
            payload,
            output_path=output_path,
            quality=QualityPolicy.transparent(),
            before=source if isinstance(source, (str, Path)) else None,
            publish="on_pass",
            source_label=source_label,
        )
    except ValueError as exc:
        return {"ok": False, "summary": str(exc)}, None
    open_safety = report.open_safety.detail or {
        "ok": report.open_safety.ok,
        "summary": report.open_safety.summary,
    }
    if not report.ok:
        open_safety = {**open_safety, "ok": False}
    return open_safety, report


def replace_package_text(
    source: str | Path | bytes,
    replacements: Mapping[str, str],
    *,
    output_path: str | Path | None = None,
    part_suffixes: Sequence[str] = (".xml", ".hpf"),
) -> PackageTextReplaceResult:
    """Replace plain text in the character data of the XML parts of a package.

    For template placeholders that may sit anywhere in the package: body,
    table cells, headers and footers, and ``content.hpf`` metadata. Each part
    whose name ends with one of *part_suffixes* (case-insensitive) is read as
    UTF-8 and only its character data is searched — element and attribute
    names, attribute values, comments and CDATA are not. Keys and values are
    plain text: ``&`` or ``<`` in them is escaped on the way in. A key split
    across elements (two runs, say) is not found. *replacements* apply in
    order, each to the text the previous one left.

    Each paragraph whose own text changed loses its ``hp:linesegarray`` layout
    cache, so Hangul lays out the new text again instead of drawing it into
    stale line slots. Text belongs to the innermost paragraph around it: a
    table-cell paragraph inside a changed paragraph keeps its cache when its
    own text did not change, and the other way round. Look-alike text in
    CDATA, comments, processing instructions or attribute values is never
    taken for the element. Everything else -- other paragraphs, other parts,
    ZIP entries -- keeps its bytes. An archive holding one entry name twice
    is refused before anything is written (``save-duplicate-entry-names``):
    a replacement by name would land on every entry of that name. The output goes
    through the open-safety gate; *output_path* is written atomically only
    when the gate passes (``ok``), and otherwise left as it was.
    """

    if any(not old for old in replacements):
        from .errors import HwpxValueError

        raise HwpxValueError(
            "replacement key must not be empty",
            code="package-text-replacement-key-empty",
            suggestion="Drop the empty key; every key is text to find.",
        )
    source_bytes = _read_source_bytes(source)
    suffixes = tuple(suffix.lower() for suffix in part_suffixes)
    with ZipFile(io.BytesIO(source_bytes), "r") as archive:
        guard_zip_file(archive)
        refuse_duplicate_entry_names(duplicate_entry_names(archive.infolist()))
        entries = tuple(info.filename for info in archive.infolist())
        names = [
            info.filename
            for info in archive.infolist()
            if not info.is_dir() and info.filename.lower().endswith(suffixes)
        ]
        parts = read_zip_members(archive, names=names)

    changed: dict[str, bytes] = {}
    undecodable: list[str] = []
    total = 0
    caches_removed = 0
    for name in names:
        try:
            xml = parts[name].decode("utf-8")
        except UnicodeDecodeError:
            undecodable.append(name)
            continue
        replaced, count, changed_at = _replace_in_text_nodes(xml, replacements)
        if not count or replaced == xml:
            continue
        replaced, removed = _strip_layout_caches(replaced, changed_at)
        changed[name] = replaced.encode("utf-8")
        total += count
        caches_removed += removed

    if changed:
        try:
            output = _patch_zip_entries(source_bytes, changed)
            zip_method = "partial-local-record-copy"
        except ValueError:
            output = _rewrite_zip_entries(source_bytes, changed)
            zip_method = "zipfile-rewrite-fallback"
    else:
        output, zip_method = source_bytes, "none"

    open_safety, report = _gate_and_publish(
        output, output_path, source=source, source_label="patch.replace_package_text"
    )
    return PackageTextReplaceResult(
        data=output,
        entries=entries,
        scanned_parts=tuple(names),
        changed_parts=tuple(changed),
        undecodable_parts=tuple(undecodable),
        replacements=total,
        layout_caches_removed=caches_removed,
        byte_identical=output == source_bytes,
        zip_method=zip_method,
        open_safety=open_safety,
        visual_complete=report,
        output_path=None if report is None else report.output_path,
    )


def _patch_zip_entries(source: bytes, replacements: Mapping[str, bytes]) -> bytes:
    """Replace the content of *replacements*' entries; every other entry keeps its local record byte for byte.

    Written through :func:`hwpx.opc.zip_records.assemble`, the engine's one record-keeping ZIP writer. Raises
    ``ValueError`` (:class:`~hwpx.opc.zip_records.ZipRecordsUnsupported`) for an archive it cannot keep
    record by record; the callers then rewrite the whole package."""

    from .opc.zip_records import assemble, read_records

    archive = read_records(source)
    missing = set(replacements) - set(archive.by_name)
    if missing:
        raise ValueError(f"replacement entry not found: {sorted(missing)!r}")

    local_order = sorted(archive.entries, key=lambda entry: entry.header_offset)
    position = {entry.filename: index for index, entry in enumerate(local_order)}
    records: list[tuple[bytes, bytes]] = []
    for entry in local_order:
        replacement = replacements.get(entry.filename)
        if replacement is None:
            records.append((archive.local_record(entry), entry.raw))
            continue
        compressed = _compress_for_entry(replacement, entry.compress_type)
        crc = binascii.crc32(replacement) & 0xFFFFFFFF
        flags = entry.flag_bits & ~0x08
        stats = {"flags": flags, "crc": crc, "compressed_size": len(compressed), "file_size": len(replacement)}
        records.append(
            (
                _local_header(entry, **stats) + compressed,
                _central_header(entry, **stats, header_offset=0),
            )
        )
    central_order = [position[entry.filename] for entry in archive.entries]
    return assemble(records, archive.eocd, central_order=central_order)


def _compress_for_entry(payload: bytes, compress_type: int) -> bytes:
    if compress_type == ZIP_STORED:
        return payload
    if compress_type == ZIP_DEFLATED:
        compressor = zlib.compressobj(level=6, wbits=-15)
        return compressor.compress(payload) + compressor.flush()
    raise ValueError(f"unsupported ZIP compression method: {compress_type}")


def _local_header(
    entry: CentralEntry,
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
    entry: CentralEntry,
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


__all__ = [
    "BytePreservingPatchResult",
    "PackageTextReplaceResult",
    "ParagraphTextPatch",
    "PatchApplied",
    "PatchSkipped",
    "paragraph_chunks",
    "paragraph_patch",
    "replace_package_text",
    "rewrite_package_parts",
]
