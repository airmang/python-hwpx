# SPDX-License-Identifier: Apache-2.0
"""``describe_capabilities()`` does not report an extra that adds nothing as installed.

``visual``, ``xlsx`` and ``preview`` are empty extras kept so that old install commands
(``pip install "python-hwpx[visual]"``) still resolve. They pull nothing in, so a bare install and
an install with the extra are the same thing. Through 7.0.0 the report said ``true`` for all three
on every install; it now says ``false`` and ``extrasNote`` says why and where the features are.
"""

from __future__ import annotations

import json

import pytest


def test_capabilities_do_not_report_the_empty_extras_as_installed() -> None:
    from hwpx.capabilities import contract_json_schema, describe_capabilities

    caps = describe_capabilities()
    assert caps["extras"] == {"visual": False, "xlsx": False, "preview": False}
    assert "python-hwpx-automation" in caps["extrasNote"]
    for name in caps["extras"]:
        assert name in caps["extrasNote"]
    # the public shape: the same keys, booleans, as the schema says
    schema = contract_json_schema("hwpx.capabilities/v1")
    assert schema["properties"]["extras"] == {"type": "object", "additionalProperties": {"type": "boolean"}}
    assert schema["properties"]["extrasNote"] == {"type": "string"}
    assert "extrasNote" not in schema["required"]


def test_the_capabilities_command_prints_the_same_report(capsys: pytest.CaptureFixture[str]) -> None:
    from hwpx.capabilities import _verify_main  # what `python -m hwpx.capabilities` runs

    assert _verify_main([]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["extras"] == {"visual": False, "xlsx": False, "preview": False}
    assert printed["extrasNote"]
