# SPDX-License-Identifier: Apache-2.0
"""Tell a line cache that outlived the paragraph content it was computed for.

Hancom trusts the line count of a cached ``hp:linesegarray`` and presses the
text into it, so a cache left on a paragraph whose content changed is worse
than no cache. The editing APIs clear the cache of the paragraph they change;
this is the net under them, for an API that forgets to. It needs no estimate
of text widths: a cache is kept only on the content it came with.

A section keeps hold of the cache elements its part was read with
(:class:`TrackedCaches`). At the save of an edited section each of them that
is still in the tree is compared with the part as it was read: when the
content of its paragraph differs, the cache goes. A cache made or rewritten
since (a cleared one written again on purpose, a copied paragraph's) is not
what the part was read with and is left alone.

A table's structure edit builds the table's rows and cells again, as new
elements the save could no longer pair with what was read. It has the caches
in the table judged before the rebuild and the rebuilt ones watched after it
(:meth:`TrackedCaches.judge_before_rebuild`, :meth:`TrackedCaches.judge_rebuilt`).
Those two look at the table and the paragraphs it sits in, not at the rest of
the section: nothing else loses its elements there, and the save still judges
every cache of the section.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from lxml import etree as LET  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

__all__ = ["TrackedCaches", "cache_elements"]

_CACHE_BYTES_RE = re.compile(
    rb"<(?P<ns>(?:[A-Za-z_][\w.-]*:)?)linesegarray\b(?:[^>]*?/>|[^>]*>.*?</(?P=ns)linesegarray>)",
    re.DOTALL | re.IGNORECASE,
)

#: A watched cache element, the digest of the content its paragraph had with it, and the cache as it was.
_Watched = tuple[Any, bytes, bytes]


def _local(node: Any) -> str:
    tag = node.tag
    return tag.rpartition("}")[2] if isinstance(tag, str) else ""


def _is_cache(tag: Any) -> bool:
    return isinstance(tag, str) and tag.rpartition("}")[2].lower() == "linesegarray"


def cache_elements(root: Any) -> list[Any]:
    """The line caches under *root* that sit directly in a paragraph, in document order."""

    found = []
    cache_tags: dict[Any, bool] = {}  # a part has a handful of tags and tens of thousands of nodes
    for node in root.iter():
        tag = node.tag
        is_cache = cache_tags.get(tag)
        if is_cache is None:
            is_cache = cache_tags[tag] = _is_cache(tag)
        if is_cache:
            parent = node.getparent()
            if parent is not None and _local(parent) == "p":
                found.append(node)
    return found


def _caches_around(element: Any) -> list[Any]:
    """The line caches of the paragraphs *element* sits in (the one holding it, and those holding that
    one's cell): the caches outside *element* whose paragraph's content changes when *element* does."""

    return [
        child
        for ancestor in element.iterancestors()
        if _local(ancestor) == "p"
        for child in ancestor
        if _is_cache(child.tag)
    ]


def _content_digest(paragraph: Any) -> bytes:
    """A digest of everything in *paragraph* but line caches (its own and those of paragraphs inside it)."""

    content = _CACHE_BYTES_RE.sub(b"", LET.tostring(paragraph, with_tail=False))
    return hashlib.blake2b(content, digest_size=16).digest()


def _content_as_read(source_xml: bytes, places: set[int]) -> dict[int, tuple[bytes, bytes]] | None:
    """What a part's bytes hold for its caches at *places* (counted among the part's caches as
    :func:`cache_elements` lists them): for each, the digest of its paragraph's content and the cache.

    The bytes are read only as far as the last of those paragraphs ends, so the caches of a table
    near the start of a long section cost a short read. ``None`` when the part ends before all were
    found (the caller then parses the whole part, which tells why).
    """

    from io import BytesIO

    from ..opc.xml_utils import guard_xml_bytes, normalize_hwpml_namespaces

    guard_xml_bytes(source_xml)
    found: dict[int, tuple[bytes, bytes]] = {}
    open_paragraphs: dict[int, list[Any]] = {}  # id(paragraph) -> the paragraph, then (place, cache)..
    cache_tags: dict[Any, bool] = {}
    place = 0
    for event, node in LET.iterparse(
        BytesIO(normalize_hwpml_namespaces(source_xml)), events=("start", "end"),
        resolve_entities=False, no_network=True, huge_tree=False,
    ):
        if event == "start":
            tag = node.tag
            is_cache = cache_tags.get(tag)
            if is_cache is None:
                is_cache = cache_tags[tag] = _is_cache(tag)
            if is_cache:
                parent = node.getparent()
                if parent is not None and _local(parent) == "p":
                    if place in places:
                        open_paragraphs.setdefault(id(parent), [parent]).append((place, node))
                    place += 1
        elif open_paragraphs and (held := open_paragraphs.pop(id(node), None)) is not None:
            _note_whole_paragraph(node, held, found)
            if len(found) == len(places):
                return found
    return None


def _note_whole_paragraph(paragraph: Any, held: list[Any], found: dict[int, tuple[bytes, bytes]]) -> None:
    """The paragraph has ended, so it and the caches in it are whole: note what they hold."""

    digest = _content_digest(paragraph)
    for place, cache in held[1:]:
        found[place] = (digest, LET.tostring(cache, with_tail=False))


class TrackedCaches:
    """The line caches a section watches, each with the content its paragraph had when it was last judged.

    It starts from the cache elements the part was read with (*caches*) and the part's bytes
    (*source_xml*). The content each of those came with is read from the bytes when the cache is
    first judged, not before: for the first table an edit rebuilds, the bytes are read as far as
    its caches reach; the next time, the whole part is parsed again for all that are left, after
    which the bytes go. When that parse does not line up with *caches*, nothing is judged from
    then on.
    """

    def __init__(self, caches: list[Any], source_xml: bytes) -> None:
        # by id(): the entries hold the elements, so lxml keeps their proxies and the ids stay theirs
        self._watched: dict[int, _Watched] = {}
        #: the caches as read that were not judged yet, each with its place among the part's caches
        self._as_read: dict[int, tuple[Any, int]] = {id(cache): (cache, place) for place, cache in enumerate(caches)}
        self._as_read_count = len(caches)
        self._source_xml: bytes | None = source_xml
        self._read_before = False  # the part was read short once
        self._judges = True
        self._rebuilding: tuple[Any, list[Any]] | None = None

    def _stop(self) -> None:
        self._judges = False
        self._watched, self._as_read, self._source_xml, self._rebuilding = {}, {}, None, None

    def _read_content_of(self, caches: list[Any], *, the_rest: bool) -> None:
        """Watch the as-read caches among *caches* with the content the part had for them. *the_rest*:
        no other as-read cache will be asked for, so the part's bytes go."""

        source = self._source_xml
        if source is None:
            return
        wanted = [found for cache in caches if (found := self._as_read.get(id(cache))) is not None]
        if not wanted and (self._read_before or not the_rest):
            if the_rest:  # the part lined up before, and nothing of it is asked for any more
                self._as_read, self._source_xml = {}, None
            return
        if wanted and not the_rest and not self._read_before and self._read_short(source, wanted):
            return
        # A save, or a second table: everything that is left, so that the part is not parsed again.
        # (A save that asks for nothing still parses once: that tells whether the part lines up.)
        self._read_whole(source, wanted if the_rest else list(self._as_read.values()))

    def _watch_as_read(self, cache: Any, digest: bytes, was: bytes) -> None:
        self._watched[id(cache)] = (cache, digest, was)
        del self._as_read[id(cache)]

    def _read_short(self, source: bytes, wanted: list[tuple[Any, int]]) -> bool:
        """The first table: read the part only as far as its caches reach. False when that did not
        find them all (the whole parse tells why)."""

        try:
            content = _content_as_read(source, {place for _cache, place in wanted})
        except Exception:
            content = None
        if content is None:
            return False
        self._read_before = True
        for cache, place in wanted:
            self._watch_as_read(cache, *content[place])
        if not self._as_read:
            self._source_xml = None
        return True

    def _read_whole(self, source: bytes, wanted: list[tuple[Any, int]]) -> None:
        from ..opc.xml_utils import parse_xml

        try:
            originals = cache_elements(parse_xml(source))
        except Exception:  # the part was read once already; without it nothing is judged
            originals = None
        if originals is None or len(originals) != self._as_read_count:
            self._stop()
            return
        for cache, place in wanted:
            original = originals[place]
            self._watch_as_read(cache, _content_digest(original.getparent()), LET.tostring(original, with_tail=False))
        self._as_read, self._source_xml = {}, None

    def _judge(self, caches: list[Any], following: dict[int, _Watched]) -> int:
        """Drop each of *caches* whose paragraph no longer has the content it was watched with, and put
        the others into *following* with the content their paragraph has now. Returns how many went."""

        removed = 0
        for cache in caches:
            paragraph = cache.getparent()
            digest = _content_digest(paragraph)
            now = LET.tostring(cache, with_tail=False)
            expected = self._watched.get(id(cache))
            if expected is not None and expected[1] != digest and expected[2] == now:
                paragraph.remove(cache)  # the content changed under the cache it was read with
                following.pop(id(cache), None)
                removed += 1
            else:
                following[id(cache)] = (cache, digest, now)
        return removed

    def judge_all(self, root: Any) -> int:
        """Drop from *root* each watched cache whose paragraph no longer has the content it came with.

        Returns how many were dropped. What is watched from here on: every cache now in the tree,
        with its paragraph's content as it is now.
        """

        if not self._judges:
            return 0
        caches = cache_elements(root)
        self._read_content_of(caches, the_rest=True)
        if not self._judges:
            return 0
        following: dict[int, _Watched] = {}
        removed = self._judge(caches, following)
        self._watched, self._rebuilding = following, None
        return removed

    def judge_before_rebuild(self, element: Any) -> int:
        """:meth:`judge_all` for the caches inside *element* (a table about to get new rows and cells)
        and those of the paragraphs it sits in. Returns how many were dropped."""

        if not self._judges:
            return 0
        inside = cache_elements(element)
        caches = inside + _caches_around(element)
        self._read_content_of(caches, the_rest=False)
        if not self._judges:
            return 0
        removed = self._judge(caches, self._watched)
        self._rebuilding = (element, inside)
        return removed

    def judge_rebuilt(self, element: Any) -> int:
        """After the rebuild :meth:`judge_before_rebuild` came before: let go of the caches *element*
        held then, watch the ones it holds now, and judge those of the paragraphs it sits in again
        (their content changed with the table). Returns how many were dropped."""

        if not self._judges:
            return 0
        caches = cache_elements(element)
        if self._rebuilding is not None and self._rebuilding[0] is element:
            held_now = {id(cache) for cache in caches}
            for cache in self._rebuilding[1]:
                if id(cache) not in held_now:
                    self._watched.pop(id(cache), None)
        self._rebuilding = None
        caches += _caches_around(element)
        self._read_content_of(caches, the_rest=False)
        if not self._judges:
            return 0
        return self._judge(caches, self._watched)
