# SPDX-License-Identifier: Apache-2.0
"""Shared namespace constants for the HWPML/OWPML XML schemas.

All modules that need HWPML namespace URIs should import from here
to avoid duplicating the definitions.
"""

# HWPML 2011 (canonical / normalised form)
HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HP = f"{{{HP_NS}}}"

HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
HH = f"{{{HH_NS}}}"

HC_NS = "http://www.hancom.co.kr/hwpml/2011/core"
HC = f"{{{HC_NS}}}"

HS_NS = "http://www.hancom.co.kr/hwpml/2011/section"
HS = f"{{{HS_NS}}}"

# HWPML 2016 (for namespace registration only)
HP10_NS = "http://www.hancom.co.kr/hwpml/2016/paragraph"
HS10_NS = "http://www.hancom.co.kr/hwpml/2016/section"
HC10_NS = "http://www.hancom.co.kr/hwpml/2016/core"
HH10_NS = "http://www.hancom.co.kr/hwpml/2016/head"

OPF_NS = "http://www.idpf.org/2007/opf/"
XML_NS = "http://www.w3.org/XML/1998/namespace"

# Hancom Office emits this broad namespace surface on HWPML document roots and
# may treat declarations that generic XML serializers consider optional as part
# of the package compatibility contract. Keep section/header roots close to the
# shape Hancom writes so read-modify-save roundtrips do not look tampered with.
HWPML_COMPAT_ROOT_NAMESPACES = {
    "ha": "http://www.hancom.co.kr/hwpml/2011/app",
    "hp": HP_NS,
    "hp10": HP10_NS,
    "hs": HS_NS,
    "hc": HC_NS,
    "hh": HH_NS,
    "hhs": "http://www.hancom.co.kr/hwpml/2011/history",
    "hm": "http://www.hancom.co.kr/hwpml/2011/master-page",
    "hpf": "http://www.hancom.co.kr/schema/2011/hpf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "opf": OPF_NS,
    "ooxmlchart": "http://www.hancom.co.kr/hwpml/2016/ooxmlchart",
    "hwpunitchar": "http://www.hancom.co.kr/hwpml/2016/HwpUnitChar",
    "epub": "http://www.idpf.org/2007/ops",
    "config": "urn:oasis:names:tc:opendocument:xmlns:config:1.0",
}
