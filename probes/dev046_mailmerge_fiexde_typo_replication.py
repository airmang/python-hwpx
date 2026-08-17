#!/usr/bin/env python3
"""DEV-046 -- the mail-merge display field carries a parameter literally
named ``Fiexde``. Hancom's own ParameterSetTable spells it that way and so
does the real output; there is no "correct" spelling to compare against.

Schema claim: none. ``hp:parameters`` content is entirely outside the
schema (DEV-011, DEV-037) -- it does not name a single parameter, let alone
type one. This entry records the case where the *parameter name itself* is
frozen as a typo.

Real-document measurement: real Hancom (HWP 13.0.0.3901, 도구 > 메일 머지 >
메일 머지 필드 넣기) emits ``hp:fieldBegin type="MAILMERGE"`` carrying five
parameters, the first of which is ``<hp:booleanParam name="Fiexde">1</...>``
(the rest: ``Prop``=8, ``Command``=field name, ``FieldType``=USER_DEFINE,
``FieldValue``=field name), with the cached text being the double-braced
``{{name}}`` verbatim. This is the **second independent subsystem** to show
the spelling -- DEV-038 found the same literal on cross-reference fields --
so it is a vendor-wide parameter name, not one field's quirk. The vendored
corpus has zero ``MAILMERGE`` fields across all 71 fixtures, so this gold is
the only real-document evidence.

Our handling: not an authoring-correctness bug. ``toc_author.py``'s
``add_page_crossref`` already replicates the misspelling verbatim
(``_param(params, "booleanParam", "Fiexde", "1")  # sic``, DEV-038), and
``tools/mail_merge.py`` does plain-text ``{{key}}`` substitution without
authoring the native ``MAILMERGE`` field at all -- so there is currently
nothing to "correct". What this entry pins is the contract for whoever
opens that authoring path: replicate the spelling (the DEV-026
``trackchageConfig`` / DEV-009 ``NOMAL`` typo-replication class). A side
finding this probe also checks: the gold's cached text matches our own
placeholder syntax exactly.
"""
from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

import lxml.etree as ET

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLD = REPO_ROOT / "tests" / "fixtures" / "gui_probes" / "mailmerge_display_fields.hwpx"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures"
SCHEMA_DIR = REPO_ROOT / "DevDoc" / "OWPML SCHEMA"

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

EXPECTED_PARAMETERS = {
    "Fiexde": ("booleanParam", "1"),
    "Prop": ("integerParam", "8"),
    "Command": ("stringParam", None),
    "FieldType": ("stringParam", "USER_DEFINE"),
    "FieldValue": ("stringParam", None),
}


def _check_schema_silence() -> None:
    if not SCHEMA_DIR.is_dir():
        print("SKIP: DevDoc/OWPML SCHEMA/ not present -- schema-silence step skipped")
        return
    hits = [
        path.name
        for path in sorted(SCHEMA_DIR.glob("*.xml"))
        if b"Fiexde" in path.read_bytes()
    ]
    assert not hits, (
        f"the schema now mentions 'Fiexde' ({hits}) -- DEV-046's premise "
        "(parameter names live entirely outside the schema) no longer holds"
    )
    print("confirmed: no schema file names this parameter -- the only reference is real output")


def _check_gold() -> None:
    with zipfile.ZipFile(GOLD) as archive:
        section_xml = archive.read("Contents/section0.xml")
    root = ET.parse(io.BytesIO(section_xml)).getroot()

    fields = [
        el
        for el in root.iter(f"{_HP}fieldBegin")
        if el.get("type") == "MAILMERGE"
    ]
    assert fields, (
        "no hp:fieldBegin type='MAILMERGE' in the gold -- DEV-046's premise "
        "no longer holds, recheck the deviation entry"
    )
    print(f"real Hancom output: {len(fields)} MAILMERGE display field(s)")

    for field in fields:
        parameters = field.find(f"{_HP}parameters")
        assert parameters is not None, "MAILMERGE field with no hp:parameters"

        observed = {
            child.get("name"): (ET.QName(child).localname, child.text)
            for child in parameters
        }
        assert set(observed) == set(EXPECTED_PARAMETERS), (
            f"parameter set changed: expected {sorted(EXPECTED_PARAMETERS)}, "
            f"got {sorted(observed)} -- DEV-046's premise no longer holds"
        )
        for name, (tag, value) in EXPECTED_PARAMETERS.items():
            observed_tag, observed_value = observed[name]
            assert observed_tag == tag, (
                f"{name} is now a {observed_tag}, expected {tag}"
            )
            if value is not None:
                assert observed_value == value, (
                    f"{name} is now {observed_value!r}, expected {value!r}"
                )

    print(
        "confirmed: the parameter is literally named 'Fiexde' "
        "(booleanParam=1), alongside Prop/Command/FieldType/FieldValue"
    )

    # The cached text is the double-braced placeholder verbatim.
    cached = [
        (el.text or "")
        for el in root.iter(f"{_HP}t")
        if "{{" in (el.text or "")
    ]
    assert cached, "expected a cached '{{...}}' text run next to the field"
    print(f"confirmed: cached text uses double braces verbatim -- {cached!r}")

    sys.path.insert(0, str(REPO_ROOT / "src"))
    from hwpx.tools.mail_merge import _PLACEHOLDER_RE

    for text in cached:
        assert _PLACEHOLDER_RE.search(text), (
            f"our placeholder syntax no longer matches Hancom's cached text "
            f"{text!r} -- the side finding this entry records is stale"
        )
    print("confirmed: our own placeholder syntax matches that cached text")


def _check_corpus_absence() -> None:
    fixtures = sorted(FIXTURE_ROOT.rglob("*.hwpx"))
    fixtures = [path for path in fixtures if path != GOLD]
    if not fixtures:
        print("SKIP: no vendored corpus files found -- corpus-absence step skipped")
        return
    hits = []
    for path in fixtures:
        try:
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    if not name.endswith((".xml", ".hpf", ".rels")):
                        continue
                    if b"MAILMERGE" in archive.read(name):
                        hits.append(path.name)
                        break
        except zipfile.BadZipFile:
            continue
    assert not hits, (
        f"MAILMERGE fields now exist in the vendored corpus ({hits}) -- "
        "DEV-046 can cite corpus evidence instead of the GUI gold alone"
    )
    print(f"confirmed: {len(fixtures)} corpus fixtures, MAILMERGE occurrences 0")


def _check_our_handling() -> None:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    source = (REPO_ROOT / "src" / "hwpx" / "tools" / "toc_author.py").read_text(
        encoding="utf-8"
    )
    assert re.search(r'"Fiexde"', source), (
        "add_page_crossref no longer emits the 'Fiexde' spelling verbatim -- "
        "DEV-038/DEV-046's typo-replication contract is broken"
    )
    print("confirmed: our cross-reference authoring still replicates the spelling verbatim")

    # The native field authoring path replicates the spelling too -- author
    # one live rather than trusting the source text.
    from hwpx.document import HwpxDocument
    from hwpx.tools.mail_merge import _PLACEHOLDER_RE

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("Name: ")
    paragraph.add_mail_merge_field("name")

    authored = [
        el
        for el in paragraph.element.iter(f"{_HP}fieldBegin")
        if el.get("type") == "MAILMERGE"
    ]
    assert len(authored) == 1, (
        f"expected add_mail_merge_field to author exactly one MAILMERGE "
        f"field, got {len(authored)}"
    )
    parameters = authored[0].find(f"{_HP}parameters")
    assert parameters is not None
    observed = {
        child.get("name"): (ET.QName(child).localname, child.text)
        for child in parameters
    }
    assert set(observed) == set(EXPECTED_PARAMETERS), (
        f"our authoring emits {sorted(observed)}, the gold has "
        f"{sorted(EXPECTED_PARAMETERS)} -- the replicated contract drifted"
    )
    assert observed["Fiexde"] == ("booleanParam", "1"), (
        "add_mail_merge_field no longer emits the 'Fiexde' spelling verbatim "
        "-- DEV-046's typo-replication contract is broken"
    )
    print(
        "confirmed: our native MAILMERGE authoring replicates the spelling "
        "verbatim, with the gold's full 5-parameter set"
    )

    cached = [el.text for el in paragraph.element.iter(f"{_HP}t") if el.text]
    assert any(_PLACEHOLDER_RE.search(text) for text in cached), (
        f"authored cache text {cached!r} is no longer a placeholder our own "
        "batch generator recognises"
    )
    print(f"confirmed: authored cache text feeds our own merge tool -- {cached!r}")


def main() -> None:
    _check_schema_silence()

    if not GOLD.exists():
        print(f"SKIP: gold not present locally: {GOLD}")
    else:
        _check_gold()

    _check_corpus_absence()
    _check_our_handling()


if __name__ == "__main__":
    main()
