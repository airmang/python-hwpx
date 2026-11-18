#!/usr/bin/env python3
"""DEV-037 -- a CLICKHERE placeholder field's ``Command`` parameter carries
a schema-opaque nested length-prefixed micro-format
(``Clickhere:set:{len}:{payload}``, with nested ``Direction:wstring:{len}:``
sub-payloads). Its length prefixes count UTF-16 code units, which differs
from the codepoint count only for non-BMP characters (surrogate pairs) in
the field's prompt/memo text; our writer counts the same way.

Schema claim: ``hp:parameters``' type ``hp:ParameterList``
(``ParaList XML schema.xml``, ``stringParam``/``integerParam``/
``listParam`` etc.) is a fully generic name-value bag -- neither the
meaning of the ``Command``/``Direction``/``Prop``/``HelpState`` parameter
*names*, nor any grammar for a string parameter's own text content, is
expressible in the schema.

Real-document measurement: not corpus-dependent -- this probe demonstrates
the format directly from our own live authoring output, including the
UTF-16 boundary case, by round-tripping a genuinely non-BMP character
(an emoji, which requires a UTF-16 surrogate pair) through
``doc.fields.add()``.

Our handling: ``paragraph.py``'s form-field authoring builds
``Clickhere:set:{n}:{payload} `` with a nested
``Direction:wstring:{n}:{prompt}`` segment, each ``n`` in UTF-16 code
units. Until 7.0 the writer used Python's ``len()`` (codepoint count); for
text within the Basic Multilingual Plane the two counts coincide, so the
corpus never showed the difference. Hancom Office 2024 settled it (two
made-up documents, a field prompt of one emoji and one letter, opened and
saved again): with the UTF-16 count the saved ``Direction`` parameter keeps
both characters, with the codepoint count it keeps only the first -- Hancom
reads the prefix as UTF-16 code units.

Run: ``python probes/dev037_clickhere_command_length_prefix_format.py``
"""

from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

SCHEMA_DIR = ROOT / "DevDoc" / "OWPML SCHEMA"


def _extract_command(section_xml: str) -> str:
    match = re.search(
        r'<hp:stringParam name="Command"[^>]*>([^<]*)</hp:stringParam>', section_xml
    )
    assert match is not None, "expected a Command stringParam"
    return match.group(1)


def main() -> int:
    schema_file = SCHEMA_DIR / "ParaList XML schema.xml"
    if schema_file.exists():
        text = schema_file.read_text("utf-8")
        assert 'type="hp:ParameterList"' in text
        print("confirmed hp:parameters is typed as the fully generic hp:ParameterList -- "
              "parameter names and string-payload grammar are outside the schema")
    else:
        print("SKIP: DevDoc/OWPML SCHEMA/ not present in this checkout — schema-text step skipped")

    from hwpx.document import HwpxDocument

    # Plain BMP-only case: codepoint count == UTF-16 code-unit count.
    doc = HwpxDocument.new()
    doc.fields.add("필드1", prompt="프롬프트")
    data = doc.to_bytes()
    doc.close()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        name = next(n for n in archive.namelist() if n.startswith("Contents/section"))
        section_xml = archive.read(name).decode("utf-8")
    command = _extract_command(section_xml)
    outer_match = re.match(r"Clickhere:set:(\d+):(.*)", command, re.DOTALL)
    assert outer_match is not None, command
    outer_len, payload_plus_trailing_space = outer_match.groups()
    # The writer appends one more literal space after computing len(payload), so the
    # captured tail is one character longer than the length prefix it was measured from.
    payload = payload_plus_trailing_space[:-1]
    assert int(outer_len) == len(payload), (
        f"expected Clickhere:set length prefix to equal len(payload) in the BMP-only case, "
        f"got {outer_len} vs {len(payload)}"
    )
    print(f"confirmed BMP-only case: Command={command!r} -- length prefix matches both "
          f"codepoint count and UTF-16 code-unit count (they coincide here)")

    # Boundary case: a non-BMP character (surrogate pair in UTF-16).
    doc2 = HwpxDocument.new()
    emoji_prompt = "프" + "\U0001F600"  # U+1F600, requires a UTF-16 surrogate pair
    codepoint_len = len(emoji_prompt)
    utf16_unit_len = len(emoji_prompt.encode("utf-16-le")) // 2
    assert utf16_unit_len != codepoint_len, "expected the two counts to diverge for this fixture"

    doc2.fields.add("필드2", prompt=emoji_prompt)
    data2 = doc2.to_bytes()
    doc2.close()
    with zipfile.ZipFile(io.BytesIO(data2)) as archive:
        name2 = next(n for n in archive.namelist() if n.startswith("Contents/section"))
        section_xml2 = archive.read(name2).decode("utf-8")
    command2 = _extract_command(section_xml2)
    direction_match = re.search(r"Direction:wstring:(\d+):", command2)
    assert direction_match is not None, command2
    declared_len = int(direction_match.group(1))

    assert declared_len == utf16_unit_len, (
        f"expected our writer's length prefix to equal the UTF-16 code-unit count "
        f"({utf16_unit_len}), the unit Hancom reads; got {declared_len} "
        f"(the codepoint count is {codepoint_len})"
    )
    print(f"confirmed the boundary case with a non-BMP character: prompt={emoji_prompt!r}, "
          f"declared length={declared_len} = UTF-16 code-unit count (codepoint count "
          f"{codepoint_len}), the unit Hancom Office 2024 reads the prefix in")

    print("PASS: DEV-037 reproduced (schema opacity + live BMP and non-BMP boundary evidence)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
