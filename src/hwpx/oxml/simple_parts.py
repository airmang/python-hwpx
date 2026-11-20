# SPDX-License-Identifier: Apache-2.0
"""Simple package-part OXML wrappers."""

from __future__ import annotations

from typing import TYPE_CHECKING
import xml.etree.ElementTree as ET

from ._document_primitives import _serialize_xml

if TYPE_CHECKING:
    from ._document_primitives import IdSource
    from .document_parts import HwpxOxmlDocument
    from .header import Style
    from .history_part import History
    from .master_page import MasterPage
    from .paragraph import HwpxOxmlParagraph
    from .settings import ApplicationSettings
    from .version_part import HcfVersion


class _HwpxOxmlSimplePart:
    """Common base for standalone XML parts that are not sections or headers."""

    def __init__(
        self,
        part_name: str,
        element: ET.Element,
        document: "HwpxOxmlDocument" | None = None,  # type: ignore[reportGeneralTypeIssues]  # frozen public annotation
    ):
        self.part_name = part_name
        self._element = element
        self._document = document
        self._dirty = False
        self._source: bytes | None = None  # the part's bytes as read, when it was read from a package

    @property
    def element(self) -> ET.Element:
        return self._element

    @property
    def document(self) -> "HwpxOxmlDocument" | None:  # type: ignore[reportGeneralTypeIssues]  # frozen public annotation
        return self._document

    def attach_document(self, document: "HwpxOxmlDocument") -> None:
        self._document = document

    @property
    def _ids(self) -> "IdSource | None":
        """The id/clock source of this part's document (a master page holds paragraphs, as a section does)."""

        return self._document._id_source if self._document is not None else None

    @property
    def dirty(self) -> bool:
        return self._dirty

    def mark_dirty(self) -> None:
        self._dirty = True

    def reset_dirty(self) -> None:
        self._dirty = False

    def replace_element(self, element: ET.Element) -> None:
        self._element = element
        self.mark_dirty()

    def to_bytes(self) -> bytes:
        return _serialize_xml(self._element)


class HwpxOxmlMasterPage(_HwpxOxmlSimplePart):
    """Represents a master page part in the package.

    실코퍼스 1파일 실측 기반 역설계(스키마 미선언 루트 네임스페이스 —
    :mod:`.master_page` 독스트링 참조). 읽기 전용: 이 트레인은 원장 read=none
    해소가 목표라 쓰기 경로는 열지 않는다.
    """

    def _remove_outlived_layout_caches(self, *, force: bool = False) -> int:
        """Nothing to track: what a table's structure edit asks of the section holding it
        (``HwpxOxmlSection._remove_outlived_layout_caches``). A master page read from a file keeps no
        record of the line caches it was read with; without this the edit raised ``AttributeError``
        after it had changed the table."""

        return 0

    def to_model(self) -> "MasterPage":
        from .master_page import parse_master_page

        return parse_master_page(self._element)

    @property
    def id(self) -> str | None:
        """The id sections link with (``hp:masterPage/@idRef``, ``doc.page.master_page_refs()``)."""

        return self._element.get("id")

    @property
    def page_type(self) -> str | None:
        """The pages it is drawn on: ``BOTH``, ``EVEN``, ``ODD``, ``LAST_PAGE`` or ``OPTIONAL_PAGE``."""

        return self._element.get("type")

    @property
    def paragraphs(self) -> "tuple[HwpxOxmlParagraph, ...]":
        """The master page's paragraphs as paragraph objects (tables, pictures and
        shapes on it are reached through them, as in the body). Edits are saved."""

        from .master_page_authoring import master_page_paragraphs

        return master_page_paragraphs(self)

    @property
    def text(self) -> str:
        """The master page's paragraph texts, one line each."""

        return "\n".join(paragraph.text for paragraph in self.paragraphs)

    def add_paragraph(
        self,
        text: str = "",
        *,
        style: "int | str | Style | None" = None,
        para_pr_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> "HwpxOxmlParagraph":
        """Append a paragraph (with *text*) to the master page and return it.

        ``style`` (a name, a numeric id or a ``Style``) gives the paragraph that style and its
        paragraph and character shapes unless they are passed; ``para_pr_id_ref`` and
        ``char_pr_id_ref`` name the shapes directly, as every ``add_paragraph`` takes them.
        """

        from .master_page_authoring import add_master_page_paragraph

        return add_master_page_paragraph(
            self, text, style=style, para_pr_id_ref=para_pr_id_ref, char_pr_id_ref=char_pr_id_ref
        )


class HwpxOxmlHistory(_HwpxOxmlSimplePart):
    """Represents a document history part.

    스키마 전용 역설계, 실코퍼스 0건(``.history_part`` 독스트링 참조) — 실
    문서 하나 확보 전까지 잠정으로 표기한다. 읽기 전용: 이 트레인은 원장
    read=none 해소가 목표라 쓰기 경로는 열지 않는다.
    """

    @property
    def is_version_log(self) -> bool:
        """Whether this part is a version log (root ``hhs:history``).

        한/글은 버전 이력이 있는 문서에 ``DocHistory/versionlog*.xml``(버전
        기록)과 함께 ``DocHistory/historylastdoc.hml``을 둔다. 뒤의 것은 마지막
        문서의 HWPML 스냅숏(루트 ``HWPML``)이고 버전 기록이 아니다.
        """

        from .utils import local_name

        return local_name(self._element) == "history"

    def to_model(self) -> "History":
        """Return the version log, or an empty one for the HWPML snapshot part.

        ``historylastdoc.hml``에는 ``historyEntry``가 없으므로 항목 없는
        :class:`History`(``version=None``)를 돌려준다. 원본 XML은 ``element``로
        읽는다. 버전 기록인지는 :attr:`is_version_log`로 가린다.
        """

        from .history_part import History, parse_history

        if not self.is_version_log:
            return History(version=None, entries=[])
        return parse_history(self._element)


class HwpxOxmlVersion(_HwpxOxmlSimplePart):
    """Represents the ``version.xml`` part.

    실코퍼스 47/47 전수 실측 기반 역설계(스키마 미선언 루트 네임스페이스 —
    :mod:`.version_part` 독스트링 참조). 읽기 전용: 이 트레인은 원장 read=none
    해소가 목표라 쓰기 경로는 열지 않는다.
    """

    def to_model(self) -> "HcfVersion":
        from .version_part import parse_hcf_version

        return parse_hcf_version(self._element)


class HwpxOxmlSettings(_HwpxOxmlSimplePart):
    """Represents the ``settings.xml`` part (``ha:HWPApplicationSetting``).

    실코퍼스 177파일 전수 실측 기반 역설계(스키마 미선언 — :mod:`.settings`
    독스트링 참조). 읽기 전용: 이 트레인은 원장 read=none 해소가 목표라
    쓰기 경로는 열지 않는다.
    """

    def to_model(self) -> "ApplicationSettings":
        from .settings import parse_application_settings

        return parse_application_settings(self._element)

    def to_bytes(self) -> bytes:
        """The part as read with only its ``ha:CaretPosition`` rewritten -- the one thing the engine changes in
        it (``doc.set_caret``/``reset_caret``) -- so the rest keeps the bytes Hangul or the template wrote."""

        import re

        caret = next((child for child in self._element if str(child.tag).endswith("}CaretPosition")), None)
        if self._source is None or caret is None:
            return super().to_bytes()
        values = " ".join(f'{key}="{value}"' for key, value in caret.attrib.items())
        found = re.search(rb"<([\w.-]+:)?CaretPosition\b[^>]*/>", self._source)
        if found is not None:
            prefix = (found.group(1) or b"").decode()
            return self._source[:found.start()] + f"<{prefix}CaretPosition {values}/>".encode() + self._source[found.end():]
        root = re.search(rb"<([\w.-]+:)?HWPApplicationSetting\b[^>]*?(/?)>", self._source)
        if root is None or root.group(2):
            return super().to_bytes()
        prefix = (root.group(1) or b"").decode()
        return self._source[:root.end()] + f"<{prefix}CaretPosition {values}/>".encode() + self._source[root.end():]


__all__ = [
    "HwpxOxmlHistory",
    "HwpxOxmlMasterPage",
    "HwpxOxmlSettings",
    "HwpxOxmlVersion",
]
