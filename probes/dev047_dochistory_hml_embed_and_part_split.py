#!/usr/bin/env python3
"""DEV-047 -- the schema draws document history as one part holding every
revision. Real Hancom splits it into one part per revision and adds a
final-document snapshot that is not OWPML at all but legacy HWPML 2.91.

Schema claim: ``Document History XML schema.xml`` (targetNamespace
``http://www.owpml.org/owpml/2024/history``) declares a single root
``history`` of type ``HWPMLHistoryType``, whose ``historyEntry`` child is
``maxOccurs="unbounded"`` -- a single aggregate part. The schema says
nothing about part naming or package registration, and has no notion of a
"final document snapshot".

Real-document measurement: saving two versions in real Hancom (HWP
13.0.0.3901, 검토 > 문서 이력 관리 > 새 버전으로 저장) produces three parts.
``DocHistory/versionlog{N}.xml`` roots at ``hhs:history`` with
``version="1.0.0.1"`` but is split **one part per revision**, each holding
exactly one ``hhs:historyEntry``; its namespace is the 2011 Hancom one, not
the schema's 2024 owpml.org (the DEV-001 duality again).
``DocHistory/historylastdoc.hml`` is the snapshot, and it is
``<HWPML Style="embed" SubVersion="10.0.0.0" Version="2.91">`` registered
with ``media-type="application/hancomhml"`` -- a legacy-format document
living inside an OWPML package. The diff bodies address that HML tree too:
their ``path`` values are HWPML element names (``DOCSETTING``, ``CARETPOS``,
``SECTION``, ``P``, ``TEXT``, ``CHAR``), not OWPML's ``hs:sec``/``hp:p``/
``hp:run``/``hp:t``.

Our handling: ``oxml/history_part.py`` parses the ``hhs:`` side correctly,
and its deliberately conservative shape (six typed revision fields, nested
diffs kept as opaque ``DiffNode``) turns out to have been the right call --
pinning the diff vocabulary to OWPML names would have been silently wrong.
Two things do not line up, both in the part-discovery layer:
``history_paths()`` substring-matches ``"history"`` and so drags the HML
snapshot in as a history part (parsing it raises ``HwpxValueError``), and
``version_path()`` substring-matches ``"version"``, which -- with
``version.xml`` absent from the manifest (DEV-036) -- resolves to
``DocHistory/versionlog0.xml``. Round-trip is byte-lossless regardless.
Repairing discovery is a follow-up ticket; this probe pins the facts.

The gold is a probe-session artifact kept outside the repository, so the
real-document half SKIPs unless the file is present. Drop it at the path
below, or point ``HWPX_DEV047_GOLD`` at it, to run the full probe.
"""
from __future__ import annotations

import io
import os
import sys
import zipfile
from pathlib import Path

import lxml.etree as ET

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = REPO_ROOT / "DevDoc" / "OWPML SCHEMA" / "Document History XML schema.xml"
# 실물 gold는 박스 프로브 세션 산출물(사설)이라 저장소에 없다 — 있으면 검증하고
# 없으면 정직하게 건너뛴다(DEV-002의 사설 코퍼스 관행과 같다).
GOLD = Path(
    os.environ.get(
        "HWPX_DEV047_GOLD",
        REPO_ROOT / "tests" / "fixtures" / "gui_probes" / "version_history.hwpx",
    )
)

_XS = "{http://www.w3.org/2001/XMLSchema}"
_HHS_2011 = "http://www.hancom.co.kr/hwpml/2011/history"
_SCHEMA_NS = "http://www.owpml.org/owpml/2024/history"

HML_PART = "DocHistory/historylastdoc.hml"
HML_MEDIA_TYPE = "application/hancomhml"
# diff path 값에 등장하는 HWPML 요소 이름 — OWPML 어휘가 아니다.
HWPML_DIFF_NAMES = ("DOCSETTING", "CARETPOS", "SECTION", "P", "TEXT", "CHAR")


def _check_schema() -> None:
    if not SCHEMA_FILE.exists():
        print(f"SKIP: schema not present locally: {SCHEMA_FILE}")
        return

    root = ET.parse(str(SCHEMA_FILE)).getroot()
    assert root.get("targetNamespace") == _SCHEMA_NS, (
        f"history schema targetNamespace changed to {root.get('targetNamespace')!r} "
        "-- DEV-047's namespace-duality premise no longer holds"
    )

    roots = [
        element.get("name")
        for element in root.findall(f"./{_XS}element")
    ]
    assert roots == ["history"], (
        f"expected exactly one top-level element declaration ('history'), got "
        f"{roots} -- DEV-047's premise no longer holds"
    )

    history_type = next(
        element
        for element in root.iter(f"{_XS}complexType")
        if element.get("name") == "HWPMLHistoryType"
    )
    entry = history_type.find(f"./{_XS}sequence/{_XS}element")
    assert entry is not None and entry.get("name") == "historyEntry"
    assert entry.get("maxOccurs") == "unbounded", (
        "historyEntry is no longer maxOccurs='unbounded' -- DEV-047's premise "
        "(schema draws a single aggregate part) no longer holds"
    )
    print(
        "confirmed: schema declares ONE history root holding unbounded "
        "historyEntry children, in the 2024 owpml.org namespace"
    )

    text = SCHEMA_FILE.read_text(encoding="utf-8", errors="replace")
    for token in ("versionlog", "DocHistory", "hml", "lastdoc"):
        assert token not in text, (
            f"the schema now mentions {token!r} -- DEV-047's premise (schema "
            "silent on part naming and on the snapshot) no longer holds"
        )
    print("confirmed: schema says nothing about part naming or a snapshot part")


def _check_gold() -> None:
    with zipfile.ZipFile(GOLD) as archive:
        names = archive.namelist()
        version_logs = sorted(
            name for name in names if name.startswith("DocHistory/versionlog")
        )
        assert version_logs, (
            "no DocHistory/versionlog*.xml in the gold -- DEV-047's premise "
            "no longer holds, recheck the deviation entry"
        )
        assert len(version_logs) >= 2, (
            f"expected one part per revision (>=2 for a two-version gold), "
            f"found {version_logs}"
        )

        for name in version_logs:
            root = ET.parse(io.BytesIO(archive.read(name))).getroot()
            assert root.tag == f"{{{_HHS_2011}}}history", (
                f"{name} roots at {root.tag} -- expected hhs:history in the "
                "2011 Hancom namespace"
            )
            entries = root.findall(f"{{{_HHS_2011}}}historyEntry")
            assert len(entries) == 1, (
                f"{name} holds {len(entries)} historyEntry children -- "
                "DEV-047's premise (one revision per part) no longer holds"
            )
        print(
            f"real Hancom output: {len(version_logs)} versionlog parts, "
            "exactly one historyEntry each (schema draws one aggregate part)"
        )

        assert HML_PART in names, (
            f"{HML_PART} missing from the gold -- DEV-047's snapshot premise "
            "no longer holds"
        )
        snapshot = archive.read(HML_PART)
        assert snapshot.lstrip().startswith(b"<HWPML"), (
            "the snapshot part no longer roots at <HWPML> -- DEV-047's "
            "legacy-format premise no longer holds"
        )
        assert b'Version="2.91"' in snapshot[:200], (
            "the snapshot is no longer declared HWPML 2.91"
        )
        print(
            "confirmed: the final-document snapshot is legacy HWPML 2.91 "
            "embedded inside the OWPML package, not OWPML"
        )

        manifest = archive.read("Contents/content.hpf").decode("utf-8", "replace")
        assert HML_MEDIA_TYPE in manifest, (
            f"expected the snapshot registered with media-type "
            f"{HML_MEDIA_TYPE!r} in content.hpf"
        )
        print(f"confirmed: content.hpf registers it as media-type={HML_MEDIA_TYPE}")

        # The diff bodies address the HML tree, not the OWPML one.
        latest = ET.parse(io.BytesIO(archive.read(version_logs[-1]))).getroot()
        paths = [
            element.get("path", "")
            for element in latest.iter()
            if element.get("path")
        ]
        assert paths, "expected diff entries carrying path attributes"
        assert any(
            name in path for path in paths for name in HWPML_DIFF_NAMES
        ), (
            f"diff paths {paths} no longer use HWPML element names -- "
            "DEV-047's addressing premise no longer holds"
        )
        assert not any(path.startswith(("hp:", "hs:", "hh:")) for path in paths), (
            f"diff paths {paths} now use OWPML prefixes -- recheck the entry"
        )
        print(f"confirmed: diff paths address the HWPML tree -- {paths}")


def _check_our_handling() -> None:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from hwpx.errors import HwpxValueError
    from hwpx.opc.package import HwpxPackage
    from hwpx.oxml.history_part import parse_history

    package = HwpxPackage.open(str(GOLD))

    history_paths = package.history_paths()
    assert HML_PART in history_paths, (
        "history_paths() no longer drags the HML snapshot in -- part "
        "discovery was repaired, update DEV-047's 'our handling' column"
    )
    print(f"reproduced: history_paths() returns {history_paths} (HML snapshot included)")

    hml_root = package.get_xml(HML_PART)
    try:
        parse_history(hml_root)
    except HwpxValueError as error:
        print(f"reproduced: parsing that part raises HwpxValueError -- {error.args[0]}")
    else:  # pragma: no cover - defensive
        raise AssertionError(
            "parse_history now accepts the HWPML snapshot -- DEV-047's "
            "'our handling' column is stale"
        )

    version_path = package.version_path()
    assert version_path is not None and version_path.startswith(
        "DocHistory/versionlog"
    ), (
        f"version_path() resolved to {version_path!r} -- the DEV-036 "
        "manifest omission plus 'version' substring collision was repaired, "
        "update DEV-047's 'our handling' column"
    )
    print(f"reproduced: version_path() mis-resolves to {version_path}")

    # Round-trip stays byte-lossless despite the discovery mismatch.
    from hwpx.document import HwpxDocument

    document = HwpxDocument.open(str(GOLD))
    rewritten = document.to_bytes()
    with zipfile.ZipFile(GOLD) as original, zipfile.ZipFile(
        io.BytesIO(rewritten)
    ) as produced:
        assert sorted(original.namelist()) == sorted(produced.namelist())
        differing = [
            name
            for name in original.namelist()
            if original.read(name) != produced.read(name)
        ]
    assert not differing, f"round-trip changed {differing}"
    print("confirmed: round-trip stays byte-lossless for every member")


def main() -> None:
    _check_schema()

    if not GOLD.exists():
        print(f"SKIP: probe-session gold not present locally: {GOLD}")
        return

    _check_gold()
    _check_our_handling()


if __name__ == "__main__":
    main()
