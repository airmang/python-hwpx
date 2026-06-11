# SPDX-License-Identifier: Apache-2.0
"""ID reference integrity checks for HWPX documents."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping


_ATTR_TO_TABLE = {
    "charPrIDRef": "char_properties",
    "paraPrIDRef": "paragraph_properties",
    "styleIDRef": "styles",
    "nextStyleIDRef": "styles",
    "charStyleIDRef": "styles",
    "borderFillIDRef": "border_fills",
    "bulletIDRef": "bullets",
    "numberingIDRef": "numberings",
    "tabPrIDRef": "tab_properties",
    "binaryItemIDRef": "bin_data",
    "memoShapeIDRef": "memo_shapes",
}

_FONT_REF_ATTR_TO_TABLE = {
    "hangul": "fontfaces.hangul",
    "latin": "fontfaces.latin",
    "hanja": "fontfaces.hanja",
    "japanese": "fontfaces.japanese",
    "other": "fontfaces.other",
    "symbol": "fontfaces.symbol",
    "user": "fontfaces.user",
}

_FONTFACE_LANG_TO_ATTR = {
    "HANGUL": "hangul",
    "LATIN": "latin",
    "HANJA": "hanja",
    "JAPANESE": "japanese",
    "OTHER": "other",
    "SYMBOL": "symbol",
    "USER": "user",
}

_ALLOWED_SENTINELS = {
    "charPrIDRef": {"4294967295"},
}

_EMPTY_TABLE_IS_ALLOWED = {"memoShapeIDRef"}


@dataclass(frozen=True)
class DanglingIDRef:
    """A header-table ID reference that does not resolve."""

    attr: str
    value: str
    table: str
    part: str
    element: str
    severity: str = "error"

    def __str__(self) -> str:
        return (
            f"{self.severity}: {self.part}:{self.element}@{self.attr}="
            f"{self.value!r} does not resolve in {self.table}"
        )


@dataclass(frozen=True)
class IgnoredIDRef:
    """An ID-like reference intentionally left outside this gate."""

    attr: str
    value: str
    part: str
    element: str
    reason: str


@dataclass(frozen=True)
class OrphanBinData:
    """A BinData image asset that is not referenced by any picture object."""

    item_id: str
    aliases: tuple[str, ...]
    sources: tuple[str, ...]
    path: str | None = None
    severity: str = "error"

    def __str__(self) -> str:
        path = f" path={self.path!r}" if self.path else ""
        return (
            f"{self.severity}: BinData asset {self.item_id!r}{path} is not "
            f"referenced by any binaryItemIDRef"
        )


@dataclass(frozen=True)
class IdIntegrityReport:
    """Result of checking known HWPX header-table ID references."""

    dangling: list[DanglingIDRef]
    ignored: list[IgnoredIDRef]
    orphan_bin_data: list[OrphanBinData] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.dangling and not self.orphan_bin_data


def check_id_integrity(document: Any) -> IdIntegrityReport:
    """Return dangling known header-table ID references for *document*.

    Unknown ``*IDRef`` attributes are recorded as ignored rather than failed.
    This keeps the gate focused on header mapping tables and avoids false
    positives for local references such as field begin/end ids.
    """

    oxml = getattr(document, "oxml", document)
    tables = _collect_definition_tables(document, oxml)
    dangling: list[DanglingIDRef] = []
    ignored: list[IgnoredIDRef] = []
    binary_refs: set[str] = set()

    for part_name, root in _iter_xml_parts(oxml):
        for element in root.iter():
            element_name = _local_name(element.tag)
            for raw_attr, raw_value in element.attrib.items():
                attr = _local_name(raw_attr)
                value = str(raw_value).strip()
                if not value:
                    continue
                if attr == "binaryItemIDRef":
                    _add_bin_aliases(binary_refs, value)
                table = _table_for_reference(element_name, attr, element)
                if table is None:
                    if attr.endswith("IDRef") or attr.endswith("IdRef"):
                        ignored.append(
                            IgnoredIDRef(
                                attr=attr,
                                value=value,
                                part=part_name,
                                element=element_name,
                                reason="unknown_idref",
                            )
                        )
                    continue
                if value in _ALLOWED_SENTINELS.get(attr, set()):
                    continue
                if attr in _EMPTY_TABLE_IS_ALLOWED and not tables.get(table):
                    ignored.append(
                        IgnoredIDRef(
                            attr=attr,
                            value=value,
                            part=part_name,
                            element=element_name,
                            reason="empty_optional_table",
                        )
                    )
                    continue
                if not _contains_id(tables.get(table, set()), value):
                    dangling.append(
                        DanglingIDRef(
                            attr=attr,
                            value=value,
                            table=table,
                            part=part_name,
                            element=element_name,
                        )
                    )

            if element_name == "fontRef":
                for attr, table in _FONT_REF_ATTR_TO_TABLE.items():
                    value = str(element.get(attr, "")).strip()
                    if value and not _contains_id(tables.get(table, set()), value):
                        dangling.append(
                            DanglingIDRef(
                                attr=f"fontRef.{attr}",
                                value=value,
                                table=table,
                                part=part_name,
                                element=element_name,
                            )
                        )

    orphan_bin_data = _find_orphan_bin_data(document, binary_refs)
    return IdIntegrityReport(
        dangling=dangling,
        ignored=ignored,
        orphan_bin_data=orphan_bin_data,
    )


def _collect_definition_tables(document: Any, oxml: Any) -> dict[str, set[str]]:
    tables: dict[str, set[str]] = {
        "char_properties": _key_set(getattr(oxml, "char_properties", {})),
        "paragraph_properties": _key_set(getattr(oxml, "paragraph_properties", {})),
        "border_fills": _key_set(getattr(oxml, "border_fills", {})),
        "styles": _key_set(getattr(oxml, "styles", {})),
        "bullets": _key_set(getattr(oxml, "bullets", {})),
        "memo_shapes": _key_set(getattr(oxml, "memo_shapes", {})),
        "bin_data": set(),
        "numberings": set(),
        "tab_properties": set(),
    }
    for table in _FONT_REF_ATTR_TO_TABLE.values():
        tables[table] = set()

    for header in getattr(oxml, "headers", []):
        for element in header.element.iter():
            name = _local_name(element.tag)
            if name == "binItem":
                _add_aliases(tables["bin_data"], element.get("id"))
                _add_bin_aliases(tables["bin_data"], element.get("BinData"))
            elif name == "numbering":
                _add_aliases(tables["numberings"], element.get("id"))
            elif name == "tabPr":
                _add_aliases(tables["tab_properties"], element.get("id"))
            elif name == "fontface":
                attr = _FONTFACE_LANG_TO_ATTR.get((element.get("lang") or "").upper())
                if attr is None:
                    continue
                table = tables[f"fontfaces.{attr}"]
                for child in element:
                    if _local_name(child.tag) == "font":
                        _add_aliases(table, child.get("id"))

    package = getattr(document, "package", None)
    manifest_items = getattr(package, "_manifest_items", None)
    if callable(manifest_items):
        for item in manifest_items():
            if _is_bin_data_manifest_item(item):
                _add_bin_aliases(tables["bin_data"], item.get("id"))
                _add_bin_aliases(tables["bin_data"], item.get("href"))

    part_names = getattr(package, "part_names", None)
    if callable(part_names):
        for part_name in part_names():
            path = PurePosixPath(str(part_name))
            if len(path.parts) >= 2 and path.parts[0] == "BinData":
                tables["bin_data"].add(path.name)
                tables["bin_data"].add(path.stem)

    return tables


def _find_orphan_bin_data(document: Any, binary_refs: set[str]) -> list[OrphanBinData]:
    assets: dict[str, dict[str, Any]] = {}

    oxml = getattr(document, "oxml", document)
    for header in getattr(oxml, "headers", []):
        for element in header.element.iter():
            if _local_name(element.tag) != "binItem":
                continue
            bin_data = element.get("BinData")
            if not bin_data:
                continue
            path = f"BinData/{bin_data}"
            _record_bin_asset(
                assets,
                source="header",
                path=path,
                values=(element.get("id"), bin_data, path),
            )

    package = getattr(document, "package", None)
    manifest_items = getattr(package, "_manifest_items", None)
    if callable(manifest_items):
        for item in manifest_items():
            if not _is_bin_data_manifest_item(item):
                continue
            _record_bin_asset(
                assets,
                source="manifest",
                path=item.get("href"),
                values=(item.get("id"), item.get("href")),
            )

    part_names = getattr(package, "part_names", None)
    if callable(part_names):
        for part_name in part_names():
            path = PurePosixPath(str(part_name))
            if len(path.parts) >= 2 and path.parts[0] == "BinData":
                _record_bin_asset(
                    assets,
                    source="package",
                    path=str(path),
                    values=(str(path), path.name, path.stem),
                )

    orphans: list[OrphanBinData] = []
    for key, asset in sorted(assets.items()):
        aliases = set(asset["aliases"])
        if aliases.intersection(binary_refs):
            continue
        orphans.append(
            OrphanBinData(
                item_id=key,
                aliases=tuple(sorted(aliases)),
                sources=tuple(sorted(asset["sources"])),
                path=asset.get("path"),
            )
        )
    return orphans


def _record_bin_asset(
    assets: dict[str, dict[str, Any]],
    *,
    source: str,
    path: Any,
    values: Iterable[Any],
) -> None:
    aliases: set[str] = set()
    for value in values:
        _add_bin_aliases(aliases, value)
    if not aliases:
        return
    key = _bin_asset_key(path, aliases)
    asset = assets.setdefault(key, {"aliases": set(), "sources": set(), "path": None})
    asset["aliases"].update(aliases)
    asset["sources"].add(source)
    if asset["path"] is None and path:
        asset["path"] = str(path)


def _bin_asset_key(path: Any, aliases: set[str]) -> str:
    if path:
        posix = PurePosixPath(str(path))
        if posix.stem:
            return posix.stem
    return sorted(aliases)[0]


def _is_bin_data_manifest_item(item: Any) -> bool:
    href = str(item.get("href", "")).strip()
    media_type = str(item.get("media-type", "")).strip().lower()
    if href:
        path = PurePosixPath(href)
        if len(path.parts) >= 2 and path.parts[0] == "BinData":
            return True
    return media_type.startswith("image/")


def _iter_xml_parts(oxml: Any) -> Iterable[tuple[str, Any]]:
    for header in getattr(oxml, "headers", []):
        yield getattr(header, "part_name", "header"), header.element
    for section in getattr(oxml, "sections", []):
        yield getattr(section, "part_name", "section"), section.element
    for master_page in getattr(oxml, "master_pages", []):
        yield getattr(master_page, "part_name", "master_page"), master_page.element
    for history in getattr(oxml, "histories", []):
        yield getattr(history, "part_name", "history"), history.element
    version = getattr(oxml, "version", None)
    if version is not None:
        yield getattr(version, "part_name", "version"), version.element


def _table_for_reference(element_name: str, attr: str, element: Any) -> str | None:
    if element_name == "style" and attr == "paraPrIDRef":
        if (element.get("type") or "").upper() == "CHAR":
            return None
    if element_name == "heading" and attr == "idRef":
        heading_type = (element.get("type") or "").upper()
        if heading_type == "BULLET":
            return "bullets"
        if heading_type == "NUMBER":
            return "numberings"
        return None
    return _ATTR_TO_TABLE.get(attr)


def _key_set(mapping: Mapping[Any, Any]) -> set[str]:
    values: set[str] = set()
    for key in mapping:
        _add_aliases(values, key)
    return values


def _add_aliases(target: set[str], value: Any) -> None:
    if value is None:
        return
    raw = str(value).strip()
    if not raw:
        return
    target.add(raw)
    try:
        target.add(str(int(raw)))
    except ValueError:
        pass


def _add_bin_aliases(target: set[str], value: Any) -> None:
    if value is None:
        return
    raw = str(value).strip()
    if not raw:
        return
    target.add(raw)
    path = PurePosixPath(raw)
    if path.name:
        target.add(path.name)
    if path.stem:
        target.add(path.stem)
    if path.name and len(path.parts) == 1 and raw != path.name:
        target.add(path.name)
    try:
        target.add(str(int(raw)))
    except ValueError:
        pass


def _contains_id(values: set[str], value: str) -> bool:
    if value in values:
        return True
    try:
        return str(int(value)) in values
    except ValueError:
        return False


def _local_name(name: Any) -> str:
    text = str(name)
    if "}" in text:
        return text.rsplit("}", 1)[1]
    return text
