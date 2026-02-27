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
