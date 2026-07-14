from __future__ import annotations

import json

import pytest

from hwpx.agent.catalog import agent_catalog, agent_json_schemas, catalog_hash, human_help, node_help
from hwpx.agent.model import AgentContractError, NODE_KINDS, NODE_PROPERTY_CATALOG_V1


def test_catalog_help_and_schemas_share_one_kind_catalog() -> None:
    catalog = agent_catalog()
    schemas = agent_json_schemas()

    assert set(catalog["nodeKinds"]) == set(NODE_KINDS)
    assert schemas["node"]["properties"]["kind"]["enum"] == list(NODE_KINDS)
    for kind in NODE_KINDS:
        info = node_help(kind)
        assert info["readableProperties"] == list(NODE_PROPERTY_CATALOG_V1[kind]["readable"])
        assert info["editableProperties"] == list(NODE_PROPERTY_CATALOG_V1[kind]["editable"])
        assert f"\n{kind}\n" in "\n" + human_help()


def test_catalog_is_detached_deterministic_and_json_serializable() -> None:
    first = agent_catalog()
    first["nodeKinds"].clear()
    second = agent_catalog()

    assert second["nodeKinds"]
    assert catalog_hash() == catalog_hash()
    assert catalog_hash().startswith("sha256:")
    json.dumps(agent_json_schemas(), ensure_ascii=False, sort_keys=True)


def test_unknown_help_kind_fails_closed() -> None:
    with pytest.raises(AgentContractError, match="unknown node kind") as error:
        node_help("xml")
    assert error.value.code == "unknown_kind"
