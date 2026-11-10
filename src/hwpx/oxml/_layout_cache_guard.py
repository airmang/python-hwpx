# SPDX-License-Identifier: Apache-2.0
"""Tell a line cache that outlived the paragraph content it was computed for.

Hancom trusts the line count of a cached ``hp:linesegarray`` and presses the
text into it, so a cache left on a paragraph whose content changed is worse
than no cache. The editing APIs clear the cache of the paragraph they change;
this is the net under them, for an API that forgets to. It needs no estimate
of text widths: a cache is kept only on the content it came with.

A section keeps hold of the cache elements its part was read with. At the
save of an edited section each of them that is still in the tree is compared
with the part as it was read: when the content of its paragraph differs, the
cache goes. A cache made or rewritten since (a cleared one written again on
purpose, a copied paragraph's) is not what the part was read with and is left
alone.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from lxml import etree as LET  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

_LINESEG_ARRAY_RE = re.compile(
    rb"<(?P<ns>(?:[A-Za-z_][\w.-]*:)?)linesegarray\b(?:[^>]*?/>|[^>]*>.*?</(?P=ns)linesegarray>)",
    re.DOTALL | re.IGNORECASE,
)

#: A cache element, the digest of the content its paragraph had with it, and the cache as it was.
TrackedCaches = list[tuple[Any, bytes, bytes]]


def _local(node: Any) -> str:
    tag = node.tag
    return tag.rpartition("}")[2] if isinstance(tag, str) else ""


def cache_elements(root: Any) -> list[Any]:
    """The line caches under *root* that sit directly in a paragraph, in document order."""

    found = []
    for node in root.iter():
        if _local(node).lower() == "linesegarray":
            parent = node.getparent()
            if parent is not None and _local(parent) == "p":
                found.append(node)
    return found


def _content_digest(paragraph: Any) -> bytes:
    """A digest of everything in *paragraph* but line caches (its own and those of paragraphs inside it)."""

    content = _LINESEG_ARRAY_RE.sub(b"", LET.tostring(paragraph, with_tail=False))
    return hashlib.blake2b(content, digest_size=16).digest()


def track(caches: list[Any], source_root: Any) -> TrackedCaches | None:
    """Pair the cache elements a part was read with (*caches*) with the content each came with,
    read from a fresh parse of the same part (*source_root*). ``None`` when the two do not line up."""

    originals = cache_elements(source_root)
    if len(originals) != len(caches):
        return None
    return [
        (cache, _content_digest(original.getparent()), LET.tostring(original, with_tail=False))
        for cache, original in zip(caches, originals)
    ]


def remove_outlived_caches(root: Any, tracked: TrackedCaches) -> tuple[int, TrackedCaches]:
    """Drop from *root* each tracked cache whose paragraph no longer has the content it came with.

    Returns how many were dropped, and what to track until the next save: every
    cache now in the tree, with its paragraph's content as it is now.
    """

    known = {id(cache): (digest, was) for cache, digest, was in tracked}
    removed = 0
    following: TrackedCaches = []
    for cache in cache_elements(root):
        paragraph = cache.getparent()
        digest = _content_digest(paragraph)
        now = LET.tostring(cache, with_tail=False)
        expected = known.get(id(cache))
        if expected is not None and expected[0] != digest and expected[1] == now:
            paragraph.remove(cache)  # the content changed under the cache it was read with
            removed += 1
        else:
            following.append((cache, digest, now))
    return removed, following
