# SPDX-License-Identifier: Apache-2.0
"""Shared namespace constants for the HWPML/OWPML XML schemas.

All modules that need HWPML namespace URIs should import from here
to avoid duplicating the definitions.
"""

import xml.etree.ElementTree as ET
from collections.abc import Mapping
from typing import Any

SUPPORTED_NAMESPACE_VERSIONS = ("2011", "2016", "2024")

NAMESPACE_URIS: dict[str, dict[str, str]] = {
    "app": {
        "2011": "http://www.hancom.co.kr/hwpml/2011/app",
        "2016": "http://www.hancom.co.kr/hwpml/2016/app",
        "2024": "http://www.owpml.org/owpml/2024/app",
    },
    "paragraph": {
        "2011": "http://www.hancom.co.kr/hwpml/2011/paragraph",
        "2016": "http://www.hancom.co.kr/hwpml/2016/paragraph",
        "2024": "http://www.owpml.org/owpml/2024/paragraph",
    },
    "section": {
        "2011": "http://www.hancom.co.kr/hwpml/2011/section",
        "2016": "http://www.hancom.co.kr/hwpml/2016/section",
        "2024": "http://www.owpml.org/owpml/2024/section",
    },
    "core": {
        "2011": "http://www.hancom.co.kr/hwpml/2011/core",
        "2016": "http://www.hancom.co.kr/hwpml/2016/core",
        "2024": "http://www.owpml.org/owpml/2024/core",
    },
    "head": {
        "2011": "http://www.hancom.co.kr/hwpml/2011/head",
        "2016": "http://www.hancom.co.kr/hwpml/2016/head",
        "2024": "http://www.owpml.org/owpml/2024/head",
    },
    "history": {
        "2011": "http://www.hancom.co.kr/hwpml/2011/history",
        "2016": "http://www.hancom.co.kr/hwpml/2016/history",
        "2024": "http://www.owpml.org/owpml/2024/history",
    },
    "master-page": {
        "2011": "http://www.hancom.co.kr/hwpml/2011/master-page",
        "2016": "http://www.hancom.co.kr/hwpml/2016/master-page",
        "2024": "http://www.owpml.org/owpml/2024/master-page",
    },
}


def namespace_uri(family: str, version: str = "2011") -> str:
    """Return the namespace URI for an OWPML *family* and *version*."""

    return NAMESPACE_URIS[family][version]


def qn(family: str, local_name: str, *, version: str = "2011") -> str:
    """Return an ElementTree qualified name for *local_name*."""

    return f"{{{namespace_uri(family, version)}}}{local_name}"


def namespace_version(uri: str) -> str | None:
    """Return the supported OWPML version for *uri*, if known."""

    for family in NAMESPACE_URIS.values():
        for version, candidate in family.items():
            if uri == candidate:
                return version
    return None


def namespace_family(uri: str) -> str | None:
    """Return the OWPML namespace family name for *uri*, if known."""

    for family, versions in NAMESPACE_URIS.items():
        if uri in versions.values():
            return family
    return None


def tag_namespace(tag: str) -> str | None:
    """Return the namespace URI from an expanded XML tag."""

    if tag.startswith("{"):
        return tag[1:].split("}", 1)[0]
    return None


def tag_local_name(tag: str) -> str:
    """Return the local-name component from an XML tag."""

    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def tag_in_family(tag: str, family: str) -> bool:
    """Return whether *tag* belongs to the namespace *family*."""

    uri = tag_namespace(tag)
    return uri is not None and namespace_family(uri) == family


def detect_namespaces(element: Any) -> dict[str, str]:
    """Detect OWPML namespace versions used by *element* and descendants."""

    detected: dict[str, str] = {}
    for node in element.iter():
        uri = tag_namespace(str(node.tag))
        if uri is None:
            continue
        family = namespace_family(uri)
        version = namespace_version(uri)
        if family is not None and version is not None:
            detected.setdefault(family, version)
    return detected


def element_qn_like(element: Any, family: str, local_name: str) -> str:
    """Build *local_name* in the namespace version used by *element*."""

    detected = detect_namespaces(element)
    version = detected.get(family, "2011")
    return qn(family, local_name, version=version)


def register_owpml_namespaces(register: Any = ET.register_namespace) -> None:
    """Register stable prefixes for the supported HWPML/OWPML namespaces."""

    for prefix, uri in DEFAULT_NAMESPACES.items():
        register(prefix, uri)


# HWPML 2011 (canonical / normalised form)
HP_NS = namespace_uri("paragraph")
HP = f"{{{HP_NS}}}"

HH_NS = namespace_uri("head")
HH = f"{{{HH_NS}}}"

HC_NS = namespace_uri("core")
HC = f"{{{HC_NS}}}"

HS_NS = namespace_uri("section")
HS = f"{{{HS_NS}}}"

# HWPML 2016 (for namespace registration only)
HP10_NS = namespace_uri("paragraph", "2016")
HS10_NS = namespace_uri("section", "2016")
HC10_NS = namespace_uri("core", "2016")
HH10_NS = namespace_uri("head", "2016")

OPF_NS = "http://www.idpf.org/2007/opf/"
XML_NS = "http://www.w3.org/XML/1998/namespace"

# Hancom Office emits this broad namespace surface on HWPML document roots and
# may treat declarations that generic XML serializers consider optional as part
# of the package compatibility contract. Keep section/header roots close to the
# shape Hancom writes so read-modify-save roundtrips do not look tampered with.
HWPML_COMPAT_ROOT_NAMESPACES = {
    "ha": namespace_uri("app"),
    "hp": HP_NS,
    "hp10": HP10_NS,
    "hs": HS_NS,
    "hc": HC_NS,
    "hh": HH_NS,
    "hhs": namespace_uri("history"),
    "hm": namespace_uri("master-page"),
    "hpf": "http://www.hancom.co.kr/schema/2011/hpf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "opf": OPF_NS,
    "ooxmlchart": "http://www.hancom.co.kr/hwpml/2016/ooxmlchart",
    "hwpunitchar": "http://www.hancom.co.kr/hwpml/2016/HwpUnitChar",
    "epub": "http://www.idpf.org/2007/ops",
    "config": "urn:oasis:names:tc:opendocument:xmlns:config:1.0",
}

DEFAULT_NAMESPACES: Mapping[str, str] = HWPML_COMPAT_ROOT_NAMESPACES
