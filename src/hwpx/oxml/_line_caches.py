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
that is, at this judgement, what it was at the last one holds nothing to judge
again. Nothing is taken on trust between two judgements -- what an edit, a
``mark_dirty()`` or anything else did to the tree in between shows in what is
compared, or the block is judged cache by cache.
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
#: What a block is, as far as any digest or cache comparison inside it can tell (:func:`_block_state`).
_State = tuple[bytes, Any, tuple[Any, ...]]
#: A child of the section's root that holds caches, its state when every cache in it was last judged (``None``:
#: one of them went then, so the next judgement looks at each again), and the caches left in it.
_Block = tuple[Any, "_State | None", tuple[Any, ...]]


def _entry(table: dict[int, Any], element: Any) -> Any:
    """What *table* holds for *element*, or ``None``. Every table is keyed by ``id()`` and each entry starts
    with the element it was made for: an entry counts only when that is *element* itself. While an entry
    holds its element, lxml keeps that element's proxy and no other element can take its id -- but a copy
    of the tables (``copy.deepcopy`` of a document) keeps the ids of the elements it was copied from,
    which elements of the copy can be given once those are gone."""

    found = table.get(id(element))
    return found if found is not None and found[0] is element else None


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


def _content_digest(paragraph: Any) -> bytes:
    """A digest of everything in *paragraph* but line caches (its own and those of paragraphs inside it)."""

    content = _CACHE_BYTES_RE.sub(b"", LET.tostring(paragraph, with_tail=False))
    return hashlib.blake2b(content, digest_size=16).digest()


def _whole_bytes(block: Any) -> bytes:
    """Everything in *block*, line caches too, as it serialises."""

    return LET.tostring(block, with_tail=False)  # type: ignore[no-any-return]


def _declared_on(element: Any) -> tuple[Any, ...]:
    """The namespace declarations *element* itself carries, in order (prefix, URI)."""

    found = []
    # lxml reports an element's own declarations as the events before the element's start
    for event, value in LET.iterwalk(element, events=("start-ns", "start")):
        if event != "start-ns":
            break
        found.append(value)
    return tuple(found)


def _names_above(node: Any, block: Any, known: dict[int, tuple[Any, tuple[Any, ...]]]) -> tuple[Any, ...]:
    """The qualified names of the elements above *node* up to *block*, nearest first.

    *known* holds what was found for an element already, with the element so that its id stays its own.
    Built going up and without recursion: a tree made in code may hold a paragraph any depth down."""

    climbed = []
    current = node
    names: tuple[Any, ...] = ()
    while current is not block:
        found = known.get(id(current))
        if found is not None and found[0] is current:
            names = found[1]
            break
        climbed.append(current)
        current = current.getparent()
    for element in reversed(climbed):  # nearest the block first, each from the one above it
        names = (element.getparent().tag, *names)
        known[id(element)] = (element, names)
    return names


def _block_state(block: Any, caches: list[Any], data: bytes) -> _State:
    """Everything that goes into the digest of a paragraph in *block* and into the bytes of a cache in it.

    Both are serialisations of an element inside the block. lxml writes such an element as a copy
    of its start tag followed by the element's content as it stands in the tree. The content is
    in *data*, the block's own serialisation, byte for byte. The copy's start tag is put together
    from more than the element's own, and this is the whole of it (libxml2's ``xmlStaticCopyNode``
    and ``xmlSearchNs``, lxml's ``_copyParentNamespaces``):

    1. the element's own declarations;
    2. a declaration for the prefix of its name, when it carries none: the namespace found by going
       up from the element, at each element above taking a declaration of that prefix it carries or
       else, where its own name is written with that prefix, the namespace its name is in;
    3. the same for each attribute's prefix -- and where the copy already has that prefix for
       another namespace than the attribute's, a prefix made up for the attribute's namespace;
    4. every declaration carried by the elements above, nearest first, one per prefix.

    What that reads and *data* does not hold: which declarations the block itself carries (its
    start tag in *data* is such a copy, own and inherited alike) and which each element over it
    does, in what order; the namespace each element above the one serialised is in, and its
    attributes' namespaces (an element is written with its prefix, whatever a nearer declaration
    makes of that prefix -- lxml leaves elements bound past such a declaration when it takes in
    a subtree -- and an element without a prefix may be in the default namespace or in none).

    So with the digest of *data* the state holds: the declarations carried by the block and by
    each element over it, with that element's prefix and qualified name; and for each cache the
    qualified names of the cache, of the paragraph holding it, of their attributes and of every
    element between the paragraph and the block.
    """

    known: dict[int, tuple[Any, tuple[Any, ...]]] = {}
    names = []
    for cache in caches:
        paragraph = cache.getparent()
        names.append(
            (
                cache.tag,
                tuple(cache.keys()),
                paragraph.tag,
                tuple(paragraph.keys()),
                _names_above(paragraph, block, known),
            )
        )
    over = tuple((_declared_on(node), node.prefix, node.tag) for node in block.iterancestors())
    return hashlib.blake2b(data, digest_size=16).digest(), (_declared_on(block), over), tuple(names)


_STATES_DECIDE: bool | None = None


def _states_decide() -> bool:
    """Whether this lxml gives :func:`_block_state` what it takes it to, checked once on small trees.

    An element's own declarations must be reported as they are. A tree parsed twice must give one
    state and the same serialisations inside. And three pairs of blocks alike in every byte, in
    which elements inside serialise differently, must differ in state where they do: declarations
    in another order over the block; an element above a paragraph bound past a nearer declaration
    of its prefix; a block that carries a declaration against one that inherits it. Where any of
    it does not hold, no block is taken as unchanged: each cache is judged with its own digest
    every time, as before."""

    global _STATES_DECIDE
    if _STATES_DECIDE is None:
        declared = LET.fromstring('<r xmlns:a="u:a"><w xmlns:b="u:b" xmlns:a="u:a" xmlns="u:d"><a:p/></w></r>')
        inside = '<a:p b:k="1"><c/><d xmlns="u:d"/><a:linesegarray/></a:p>'
        plain = f'<r xmlns:a="u:a" xmlns:b="u:b"><w>{inside}</w></r>'

        def taking_in(root: str, subtree: str) -> Any:
            # a subtree whose top declares the root's namespace again as z: lxml strips that and
            # binds what used it to the root's declaration, past whatever declares the prefix between
            top = LET.fromstring(root)
            top.append(LET.fromstring(subtree))
            return top.find(".//*[@id='b']")

        held = "<a:p><a:linesegarray/></a:p>"
        hidden = taking_in('<r xmlns:a="u:a"/>', f'<z:e xmlns:z="u:a" id="b"><a:m xmlns:a="u:x"><z:d>{held}</z:d></a:m></z:e>')
        carried = taking_in('<r xmlns:a="u:a"/>', f'<z:e xmlns:z="u:a"><z:k xmlns:a="u:x" id="b">{held}</z:k></z:e>')
        inherited = taking_in('<r xmlns:a="u:a"/>', f'<z:e xmlns:z="u:a" xmlns:a="u:x"><z:k id="b">{held}</z:k></z:e>')
        trees = [
            LET.fromstring(plain)[0][0],
            LET.fromstring(plain)[0][0],
            LET.fromstring(f'<r xmlns:b="u:b" xmlns:a="u:a"><w>{inside}</w></r>')[0][0],
            hidden,
            LET.fromstring(LET.tostring(hidden.getparent())).find(".//*[@id='b']"),
            carried,
            inherited,
        ]
        states = [_block_state(block, cache_elements(block), _whole_bytes(block)) for block in trees]
        parts = [[LET.tostring(node, with_tail=False) for node in block.iter()] for block in trees]
        _STATES_DECIDE = (
            [_declared_on(node) for node in declared.iter()]
            == [(("a", "u:a"),), (("b", "u:b"), ("a", "u:a"), ("", "u:d")), ()]
            and states[0] == states[1]
            and parts[0] == parts[1]
            and all(states[one] != states[other] or parts[one] == parts[other] for one, other in ((0, 2), (3, 4), (5, 6)))
        )
    return _STATES_DECIDE


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

    The rule (:meth:`_judge`) is the one a judgement has always applied to each cache in the tree, in
    document order: a watched cache that is still the bytes it was while its paragraph's content is not
    goes, and every other cache is watched from then on with the content its paragraph has now. A
    judgement (:meth:`judge_all`) leaves exactly what applying that rule to every cache of the section
    leaves. It spends less than a digest of every paragraph by two things, each checked at the judgement
    itself against the tree as it is then:

    * **A block that is what it was is not judged again.** A block is a child of the section's root
      (a body paragraph, with whatever tables it holds). Every judgement takes the state
      (:func:`_block_state`) of every block that holds a cache. When that is the state the block had
      at the last judgement, the block holds the same cache elements in the same order, and no cache
      of it went at that judgement, then each paragraph in it has the content, and each cache the
      bytes, its entry was made with, so the rule keeps every one with the same entry. A block in
      which the rule dropped a cache is judged cache by cache the next time: the paragraphs around
      the dropped cache were digested before it went, and it may have taken text after it along.
    * **What the part was read with is not digested until it differs.** The caches as read
      (*caches*, with the part's bytes *source_xml*) start out watched "as read". The first judgement
      parses the part again, as it always did, and a block in the state of the block it was read as,
      with the caches read in it, keeps them "as read": their entries are what a digest of the parsed
      part gives, and what a digest of the tree gives. When such a block differs at a later
      judgement, the part is parsed once more for all that are left and its bytes go.

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

    # -- the part as read ------------------------------------------------------------------------

    def _stop(self) -> None:
        self._judges = False
        self._watched, self._as_read, self._blocks = {}, {}, {}
        self._source_xml = self._originals = None

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

    def _part_blocks(self) -> dict[int, tuple[Any, list[Any]]] | None:
        """The parsed part's blocks with their caches, by the place of the first cache in each. ``None``
        when the part does not line up (nothing is judged)."""

        parsed = self._parse_part()
        if parsed is None:
            return None
        found: dict[int, tuple[Any, list[Any]]] = {}
        place = 0
        for block, caches in parsed:
            found[place] = (block, caches)
            place += len(caches)
        return found

    def _expected(self, cache: Any) -> tuple[bytes, bytes] | None:
        """What *cache* is watched with: its paragraph's content digest and the cache's bytes."""

        watched = _entry(self._watched, cache)
        if watched is not None:
            return watched[1], watched[2]
        as_read = _entry(self._as_read, cache)
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
        structure edit is about to build again) changes no answer: the caches of the block holding it
        that are watched "as read" are watched with digests instead (of the tree, which in an unchanged
        block is the part), so that the judgement after the edit, which finds that block changed, does
        not have to parse the part for them.
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
        if not first:
            self._let_the_part_go(as_read, watched)
        self._originals = None
        if not as_read:
            self._source_xml = None
        self._watched, self._as_read, self._blocks = watched, as_read, blocks
        return removed

    def _judge_block(
        self,
        block: Any,
        rebuilding: bool,
        as_read_blocks: dict[int, tuple[Any, list[Any]]],
        watched: dict[int, _Watched],
        as_read: dict[int, tuple[Any, int]],
        blocks: dict[int, _Block],
    ) -> int | None:
        """Judge the caches in *block* into *watched*, *as_read* and *blocks*. Returns how many went
        (``None``: the part did not line up, and nothing is judged)."""

        caches = cache_elements(block)
        if not caches:
            return 0
        state = _block_state(block, caches, _whole_bytes(block))
        was = _entry(self._blocks, block)
        if _states_decide() and (
            (
                was is not None
                and was[1] == state
                and len(was[2]) == len(caches)
                and all(held is cache for held, cache in zip(was[2], caches))
                and all(
                    _entry(self._watched, cache) is not None or _entry(self._as_read, cache) is not None
                    for cache in caches
                )
            )
            or (as_read_blocks and self._is_as_read(caches, state, as_read_blocks))
        ):
            # Nothing in the block changed since its caches were last judged (or read): the rule keeps
            # each of them with the entry it has.
            for cache in caches:
                entry = _entry(self._watched, cache)
                if entry is None:
                    unread = None if rebuilding else _entry(self._as_read, cache)
                    if unread is not None:
                        as_read[id(cache)] = unread
                        continue
                    entry = _as_it_is(cache)  # as read, and the block is what it was read as
                watched[id(cache)] = entry
            blocks[id(block)] = (block, state, tuple(caches))
            return 0
        gone = self._judge(caches, watched, as_read)
        if not self._judges:
            return None
        # With a cache gone the block is no longer in the state taken above, and the digests of the
        # paragraphs around the cache were taken before it went (with the text after it, which went
        # along): judge each again the next time, as a look at every cache would.
        blocks[id(block)] = (block, None if gone else state, tuple(cache for cache in caches if id(cache) in watched))
        return gone

    def _is_as_read(
        self, caches: list[Any], state: _State, as_read_blocks: dict[int, tuple[Any, list[Any]]]
    ) -> bool:
        """Whether a block of the tree (its *caches* and *state*) is one of the parsed part's blocks,
        unchanged: the caches read in it, in their places, and the same state."""

        places = []
        for cache in caches:
            found = _entry(self._as_read, cache)
            if found is None:
                return False
            places.append(found[1])
        source = as_read_blocks.get(places[0])
        if source is None or places != list(range(places[0], places[0] + len(source[1]))):
            return False
        return _block_state(source[0], source[1], _whole_bytes(source[0])) == state
