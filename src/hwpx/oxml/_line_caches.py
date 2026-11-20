# SPDX-License-Identifier: Apache-2.0
"""Tell a line cache that outlived the paragraph content it was computed for.

Hancom trusts the line count of a cached ``hp:linesegarray`` and presses the
text into it, so a cache left on a paragraph whose content changed is worse
than no cache. The editing APIs clear the cache of the paragraph they change;
this is the net under them, for an API that forgets to. It needs no estimate
of text widths: a cache is kept only on the content it came with.

A section keeps hold of the cache elements its part was read with
(:class:`TrackedCaches`). At the save of an edited section, and before and
after a table's structure edit (which builds the table's rows and cells again,
as new elements the save could no longer pair with what was read), each of
them that is still in the tree is compared with the part as it was read: when
the content of its paragraph differs, the cache goes. A cache made or
rewritten since (a cleared one written again on purpose, a copied
paragraph's) is not what the part was read with and is left alone.

Every judgement looks at every cache of the section, so a caller can rely on
any cache it finds after one. What keeps that from costing a digest of each
paragraph each time is in the class below: a paragraph of the section's body
whose bytes are those of the last judgement holds nothing to judge again.
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
#: A child of the section's root that holds caches, the digest of its bytes when every cache in it was last
#: judged (``None``: one of them went then, so the next judgement looks at each again), and those caches' ids.
_Block = tuple[Any, "bytes | None", tuple[int, ...]]


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


def _whole_bytes(block: Any) -> bytes:
    """Everything in *block*, line caches too: what it serialises to, which is what every digest and every
    cache comparison of the paragraphs inside it is taken from."""

    return LET.tostring(block, with_tail=False)  # type: ignore[no-any-return]


def _bytes_digest(data: bytes) -> bytes:
    return hashlib.blake2b(data, digest_size=16).digest()


def _as_it_is(cache: Any) -> _Watched:
    return cache, _content_digest(cache.getparent()), LET.tostring(cache, with_tail=False)


def _block_of(root: Any, element: Any) -> Any:
    """The child of *root* that *element* is in (or is), or ``None`` when it is not under *root*."""

    node = element
    while node is not None:
        parent = node.getparent()
        if parent is root:
            return node
        node = parent
    return None


class TrackedCaches:
    """The line caches a section watches, each with the content its paragraph had when it was last judged.

    The rule (:meth:`_judge`) is the one a judgement has always applied to each cache in the tree: a
    watched cache that is still the bytes it was while its paragraph's content is not goes, and every
    other cache is watched from then on with the content its paragraph has now. A judgement
    (:meth:`judge_all`) leaves exactly what applying that rule to every cache of the section leaves. It
    spends less than a digest of every paragraph by two things that do not change an answer:

    * **A block whose bytes did not change is not judged again.** A block is a child of the section's
      root (a body paragraph, with whatever tables it holds). When a block serialises to the bytes it
      had at the last judgement and holds the same cache elements, each paragraph in it has the content
      and each cache the bytes it was watched with, so the rule keeps every one with the same entry.
      The serialisation is taken at every judgement, so an edit made in the tree directly is seen like
      any other. A block in which a cache went is judged cache by cache the next time.
    * **What the part was read with is not digested until it differs.** The caches as read
      (*caches*, with the part's bytes *source_xml*) start out watched "as read". The first judgement
      parses the part again, as it always did, and a block that serialises to the bytes of the block
      it was read as keeps its caches "as read": their entries are what a digest of the parsed part
      would give. When such a block changes later, the part is parsed once more for all that are left
      and its bytes go.

    When the parsed part does not line up with *caches*, nothing is judged from then on.
    """

    def __init__(self, caches: list[Any], source_xml: bytes) -> None:
        # by id(): the entries hold the elements, so lxml keeps their proxies and the ids stay theirs
        self._watched: dict[int, _Watched] = {}
        #: the caches watched as read, each with its place among the part's caches
        self._as_read: dict[int, tuple[Any, int]] = {id(cache): (cache, place) for place, cache in enumerate(caches)}
        self._as_read_count = len(caches)
        self._source_xml: bytes | None = source_xml
        self._blocks: dict[int, _Block] = {}
        self._judged_once = False
        self._judges = True
        #: the part's caches parsed again, while a judgement needs them
        self._originals: list[Any] | None = None
        #: the block a structure edit said it would rebuild, at the judgement before it
        self._rebuilding: Any = None

    # -- the part as read ------------------------------------------------------------------------

    def _stop(self) -> None:
        self._judges = False
        self._watched, self._as_read, self._blocks = {}, {}, {}
        self._source_xml = self._originals = self._rebuilding = None

    def _parse_part(self) -> list[tuple[Any, list[Any]]] | None:
        """The part parsed again: each child of its root that holds caches, with them. ``None`` (and
        nothing is judged any more) when it cannot be parsed or its caches do not line up."""

        from ..opc.xml_utils import parse_xml

        blocks: list[tuple[Any, list[Any]]] = []
        source = self._source_xml
        if source is None:  # its bytes went with the last cache watched as read
            self._stop()
            return None
        try:
            for block in parse_xml(source):
                caches = cache_elements(block)
                if caches:
                    blocks.append((block, caches))
        except Exception:  # the part was read once already; without it nothing is judged
            self._stop()
            return None
        originals = [cache for _block, caches in blocks for cache in caches]
        if len(originals) != self._as_read_count:
            self._stop()
            return None
        self._originals = originals
        return blocks

    def _expected(self, cache: Any) -> tuple[bytes, bytes] | None:
        """What *cache* is watched with: its paragraph's content digest and the cache's bytes."""

        watched = self._watched.get(id(cache))
        if watched is not None:
            return watched[1], watched[2]
        as_read = self._as_read.get(id(cache))
        if as_read is None:
            return None
        if self._originals is None and self._parse_part() is None:
            return None
        assert self._originals is not None
        return _as_it_is(self._originals[as_read[1]])[1:]

    def _let_the_part_go(self, as_read: dict[int, tuple[Any, int]], watched: dict[int, _Watched]) -> None:
        """After the part was parsed a second time: watch everything still *as_read* with what the part
        holds for it (into *watched*), so that the part's bytes are not needed again."""

        if self._originals is not None and self._judges:
            for cache, place in as_read.values():
                watched[id(cache)] = (cache, *_as_it_is(self._originals[place])[1:])
            as_read.clear()
        self._originals = None
        if not as_read:
            self._source_xml = None

    # -- the rule --------------------------------------------------------------------------------

    def _judge(self, caches: list[Any], watched: dict[int, _Watched], as_read: dict[int, tuple[Any, int]]) -> int:
        """Drop each of *caches* whose paragraph no longer has the content it was watched with, and put
        the others into *watched* with the content their paragraph has now (none of them stays in
        *as_read*). Returns how many went."""

        removed = 0
        for cache in caches:
            paragraph = cache.getparent()
            digest = _content_digest(paragraph)
            now = LET.tostring(cache, with_tail=False)
            expected = self._expected(cache)
            if not self._judges:  # the part did not line up: nothing was to be judged
                return 0
            as_read.pop(id(cache), None)
            if expected is not None and expected[0] != digest and expected[1] == now:
                paragraph.remove(cache)  # the content changed under the cache it was read with
                watched.pop(id(cache), None)
                removed += 1
            else:
                watched[id(cache)] = (cache, digest, now)
        return removed

    # -- judgements ------------------------------------------------------------------------------

    def judge_all(self, root: Any, *, about_to_rebuild: Any = None) -> int:
        """Drop from *root* each watched cache whose paragraph no longer has the content it came with.

        Returns how many were dropped. What is watched from here on: every cache now in the tree,
        with its paragraph's content as it is now. *about_to_rebuild* (a table whose rows and cells a
        structure edit is about to build again) changes no answer: it has the block holding it watched
        with digests rather than "as read", for :meth:`judge_rebuilt` after the edit.
        """

        if not self._judges:
            return 0
        first = not self._judged_once
        as_read_blocks = self._part_blocks() if first else {}
        if as_read_blocks is None:
            return 0
        self._judged_once = True
        rebuilding = _block_of(root, about_to_rebuild) if about_to_rebuild is not None else None
        removed = 0
        watched: dict[int, _Watched] = {}
        as_read: dict[int, tuple[Any, int]] = {}
        blocks: dict[int, _Block] = {}
        for block in root:
            gone = self._judge_block(block, block is rebuilding, as_read_blocks, watched, as_read, blocks)
            if gone is None:
                return 0
            removed += gone
            if gone and block is rebuilding:
                # The paragraphs around a cache that went were digested before it went: the judgement
                # after the rebuild cannot take this block's other caches as just judged.
                rebuilding = None
        if not first:
            self._let_the_part_go(as_read, watched)
        self._originals = None
        if not as_read:
            self._source_xml = None
        self._watched, self._as_read, self._blocks, self._rebuilding = watched, as_read, blocks, rebuilding
        return removed

    def _part_blocks(self) -> dict[int, tuple[Any, int, int]] | None:
        """The parsed part's blocks, by the place of the first cache in each: the block, that place and
        how many caches it holds. ``None`` when the part does not line up (nothing is judged)."""

        parsed = self._parse_part()
        if parsed is None:
            return None
        found: dict[int, tuple[Any, int, int]] = {}
        place = 0
        for block, caches in parsed:
            found[place] = (block, place, len(caches))
            place += len(caches)
        return found

    def _judge_block(
        self,
        block: Any,
        rebuilding: bool,
        as_read_blocks: dict[int, tuple[Any, int, int]],
        watched: dict[int, _Watched],
        as_read: dict[int, tuple[Any, int]],
        blocks: dict[int, _Block],
    ) -> int | None:
        """Judge the caches in *block* into *watched*, *as_read* and *blocks*. Returns how many went
        (``None``: the part did not line up, and nothing is judged)."""

        caches = cache_elements(block)
        if not caches:
            return 0
        ids = tuple(id(cache) for cache in caches)
        data = _whole_bytes(block)
        digest = _bytes_digest(data)
        was = self._blocks.get(id(block))
        if (was is not None and was[0] is block and was[1] == digest and was[2] == ids) or (
            as_read_blocks and self._is_as_read(caches, data, as_read_blocks)
        ):
            # Nothing in the block changed since its caches were last judged (or read): the rule keeps
            # each of them with the entry it has.
            for cache in caches:
                entry = self._watched.get(id(cache))
                if entry is None:
                    unread = None if rebuilding else self._as_read.get(id(cache))
                    if unread is not None:
                        as_read[id(cache)] = unread
                        continue
                    entry = _as_it_is(cache)  # as read, and the block is what it was read as
                watched[id(cache)] = entry
            blocks[id(block)] = (block, digest, ids)
            return 0
        gone = self._judge(caches, watched, as_read)
        if not self._judges:
            return None
        # With a cache gone the block is no longer the bytes digested above, and the digests of the
        # paragraphs around the cache were taken before it went: judge each again the next time.
        blocks[id(block)] = (block, None if gone else digest, tuple(i for i in ids if i in watched))
        return gone

    def _is_as_read(self, caches: list[Any], data: bytes, as_read_blocks: dict[int, tuple[Any, int, int]]) -> bool:
        """Whether a block of the tree (its *caches* and bytes *data*) is one of the parsed part's blocks,
        unchanged: the same caches, in their places, and the same bytes."""

        places = []
        for cache in caches:
            found = self._as_read.get(id(cache))
            if found is None:
                return False
            places.append(found[1])
        source = as_read_blocks.get(places[0])
        if source is None or source[2] != len(places) or places != list(range(source[1], source[1] + source[2])):
            return False
        return _whole_bytes(source[0]) == data

    def judge_rebuilt(self, root: Any, element: Any, holder: Any) -> int:
        """:meth:`judge_all`, straight after the structure edit that :meth:`judge_all` was told about
        (*about_to_rebuild* was *element*) built *element*'s rows and cells again and cleared the caches
        of *holder* (the paragraph holding the table) and of the paragraphs holding that one's cell.

        Between the two judgements nothing changed but *element*'s own content and those caches, so the
        rule gives every cache outside *element* whose paragraph does not hold it the answer it gave a
        moment ago, with the same content: only the caches now in *element* and those of the paragraphs
        it sits in are judged, and the caches *element* held before are no longer watched. Whenever that
        cannot be said (no judgement told of this block, a cache of the block went at that judgement, or
        *holder* is not in it), the whole section is judged.
        """

        if not self._judges:
            return 0
        block = _block_of(root, element)
        if block is None or block is not self._rebuilding or _block_of(root, holder) is not block:
            return self.judge_all(root)
        self._rebuilding = None
        in_block = cache_elements(block)
        held = {id(cache) for cache in in_block}
        was = self._blocks.pop(id(block), None)
        if was is not None:
            for key in was[2]:
                if key not in held:  # a cache of the rows and cells that went, or one the edit cleared
                    self._watched.pop(key, None)
                    self._as_read.pop(key, None)
        judged = {id(cache) for cache in cache_elements(element)}
        judged.update(id(cache) for cache in _caches_around(element))
        # in document order, as a judgement of the whole section meets them
        gone = self._judge([cache for cache in in_block if id(cache) in judged], self._watched, self._as_read)
        if not self._judges:
            return 0
        self._let_the_part_go(self._as_read, self._watched)
        ids = tuple(
            key for key in (id(cache) for cache in in_block) if key in self._watched or key in self._as_read)
        if ids:
            self._blocks[id(block)] = (block, None if gone else _bytes_digest(_whole_bytes(block)), ids)
        return gone
