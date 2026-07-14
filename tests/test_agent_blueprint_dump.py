from __future__ import annotations

import hashlib
import io
import json
import zipfile
from copy import deepcopy
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.agent import HwpxAgentDocument
from hwpx.agent.blueprint import (
    build_blueprint_bundle,
    dump_document_blueprint,
    read_blueprint_bundle,
    repack_blueprint_bundle,
    validate_blueprint_manifest,
    with_blueprint_hash,
)
from hwpx.agent.model import AgentContractError
from hwpx.oxml.namespaces import HP


PNG = (
    Path(__file__).parent
    / "fixtures/fuzz_regressions/visual_review_seed_000000_000999_screenshots/seed-000003-710dbd610d8d.png"
).read_bytes()


def _write_supported_fixture(path: Path, *, paragraph_id: str = "102") -> str:
    with HwpxDocument.new() as document:
        paragraph = document.sections[0].paragraphs[0]
        paragraph.element.set("id", paragraph_id)
        paragraph.text = "결재 요청 본문"
        paragraph.add_rectangle(width=7200, height=3600, fill_color="#FFFFFF")
        paragraph.add_footnote("승인 근거")
        image_ref = document.add_image(PNG, "png")
        paragraph.add_picture(image_ref, width=7200, height=3600)
        table = paragraph.add_table(2, 2)
        table.rows[0].cells[0].text = "항목"
        table.rows[0].cells[1].text = "내용"
        table.rows[1].cells[0].text = "담당"
        table.rows[1].cells[1].text = "홍길동"
        table.rows[0].cells[0].set_span(2, 1)

        begin_run = paragraph.element.makeelement(f"{HP}run", {"charPrIDRef": "0"})
        begin_ctrl = begin_run.makeelement(f"{HP}ctrl", {"type": "FORM"})
        begin_ctrl.append(
            begin_ctrl.makeelement(
                f"{HP}fieldBegin",
                {"id": "601", "fieldName": "담당자", "type": "FORM", "editable": "true"},
            )
        )
        begin_run.append(begin_ctrl)
        paragraph.element.append(begin_run)
        end_run = paragraph.element.makeelement(f"{HP}run", {"charPrIDRef": "0"})
        end_ctrl = end_run.makeelement(f"{HP}ctrl", {"type": "FORM"})
        end_ctrl.append(end_ctrl.makeelement(f"{HP}fieldEnd", {"beginIDRef": "601"}))
        end_run.append(end_ctrl)
        paragraph.element.append(end_run)
        paragraph.section.mark_dirty()
        document.save_to_path(path)
    with HwpxAgentDocument.open(path) as agent:
        return next(
            record.path
            for record in agent.records
            if record.kind == "paragraph" and record.attributes.get("id") == paragraph_id
        )


def _write_unsupported_fixture(path: Path) -> str:
    root_path = _write_supported_fixture(path)
    with HwpxDocument.open(path) as document:
        paragraph = document.sections[0].paragraphs[0]
        paragraph.runs[0].element.append(paragraph.runs[0].element.makeelement(f"{HP}mysteryObject", {}))
        paragraph.section.mark_dirty()
        document.save_to_path(path)
    return root_path


def _malicious_zip(entries: list[tuple[zipfile.ZipInfo | str, bytes]]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for info, payload in entries:
            archive.writestr(info, payload)
    return stream.getvalue()


def test_supported_dump_is_byte_identical_and_dependency_complete(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    root = _write_supported_fixture(source)
    first = dump_document_blueprint(source, path=root, mode="portable")
    second = dump_document_blueprint(source, path=root, mode="portable")

    assert first.bundle_bytes == second.bundle_bytes
    assert first.bundle_sha256 == second.bundle_sha256
    assert first.manifest["blueprintHash"] == second.manifest["blueprintHash"]
    assert first.manifest["fidelity"] == {"replayable": True, "ceiling": "exact", "reasons": []}
    assert {node["kind"] for node in first.manifest["nodes"]} >= {
        "paragraph",
        "run",
        "table",
        "row",
        "cell",
        "picture",
        "shape",
        "footnote",
        "form-field",
    }
    assert first.manifest["styles"]
    assert first.manifest["resources"]
    assert len(first.assets) == 1
    assert read_blueprint_bundle(first.bundle_bytes).manifest == first.manifest


def test_dump_logical_ids_ignore_native_id_perturbation(tmp_path: Path) -> None:
    first_source = tmp_path / "first.hwpx"
    second_source = tmp_path / "second.hwpx"
    first_root = _write_supported_fixture(first_source, paragraph_id="102")
    second_root = _write_supported_fixture(second_source, paragraph_id="999")
    first = dump_document_blueprint(first_source, path=first_root)
    second = dump_document_blueprint(second_source, path=second_root)

    first_graph = [(node["blueprintId"], node["kind"], node["children"]) for node in first.manifest["nodes"]]
    second_graph = [(node["blueprintId"], node["kind"], node["children"]) for node in second.manifest["nodes"]]
    assert first_graph == second_graph
    assert first.manifest["root"]["blueprintId"] == second.manifest["root"]["blueprintId"] == "n000001"


def test_unsupported_dump_is_explicit_and_strict_mode_refuses(tmp_path: Path) -> None:
    source = tmp_path / "unsupported.hwpx"
    root = _write_unsupported_fixture(source)
    with pytest.raises(AgentContractError) as error:
        dump_document_blueprint(source, path=root, require_replayable=True)
    assert error.value.code == "unsupported_content"

    result = dump_document_blueprint(source, path=root, require_replayable=False)
    assert result.manifest["fidelity"]["replayable"] is False
    assert result.manifest["fidelity"]["ceiling"] == "unsupported"
    assert any(item["kind"] == "mysteryObject" for item in result.manifest["unsupported"])


def test_source_bound_dump_records_revision_and_dependency_fingerprints(tmp_path: Path) -> None:
    source = tmp_path / "bound.hwpx"
    root = _write_supported_fixture(source)
    result = dump_document_blueprint(source, path=root, mode="source-bound")
    assert result.manifest["source"]["revision"] == "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
    assert all(item["signature"].startswith("sha256:") for item in result.manifest["styles"])


def test_safe_repack_rehashes_typed_manifest_and_preserves_assets(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    root = _write_supported_fixture(source)
    dumped = dump_document_blueprint(source, path=root)
    edited = deepcopy(dumped.manifest)
    edited["nodes"][0]["properties"]["text"] = "수정된 결재 본문"
    destination = tmp_path / "edited.hwpxbp"
    repacked = repack_blueprint_bundle(dumped.bundle_bytes, destination, edited)
    assert repacked.manifest["blueprintHash"] != dumped.manifest["blueprintHash"]
    assert repacked.assets == dumped.assets


@pytest.mark.parametrize(
    "entry",
    ["/absolute.png", "../parent.png", "assets/nested.zip", "assets/file.xml", "unknown.bin"],
)
def test_bundle_rejects_unsafe_unknown_and_nested_entries(entry: str) -> None:
    bundle = _malicious_zip([("blueprint.json", b"{}"), (entry, b"x")])
    with pytest.raises(AgentContractError):
        read_blueprint_bundle(bundle)


def test_bundle_rejects_duplicate_manifest_and_symlink() -> None:
    with pytest.warns(UserWarning, match="Duplicate name"):
        duplicate = _malicious_zip([("blueprint.json", b"{}"), ("blueprint.json", b"{}")])
    with pytest.raises(AgentContractError):
        read_blueprint_bundle(duplicate)

    link = zipfile.ZipInfo("assets/" + "a" * 64 + ".png")
    link.create_system = 3
    link.external_attr = 0o120777 << 16
    symlink = _malicious_zip([("blueprint.json", b"{}"), (link, b"target")])
    with pytest.raises(AgentContractError):
        read_blueprint_bundle(symlink)


def test_bundle_rejects_decompression_ratio_before_json_parse() -> None:
    info = zipfile.ZipInfo("blueprint.json")
    info.compress_type = zipfile.ZIP_DEFLATED
    bomb = _malicious_zip([(info, b"0" * (1024 * 1024))])
    with pytest.raises(AgentContractError) as error:
        read_blueprint_bundle(bomb)
    assert error.value.code == "resource_limit"


def test_bundle_rejects_asset_hash_and_mime_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    root = _write_supported_fixture(source)
    dumped = dump_document_blueprint(source, path=root)
    asset_path = next(iter(dumped.assets))

    with pytest.raises(AgentContractError):
        build_blueprint_bundle(dumped.manifest, {asset_path: b"not the declared bytes"})

    wrong_mime = deepcopy(dumped.manifest)
    wrong_mime["resources"][0]["mediaType"] = "image/jpeg"
    wrong_mime = with_blueprint_hash(wrong_mime)
    with pytest.raises(AgentContractError):
        build_blueprint_bundle(wrong_mime, dumped.assets)


def test_manifest_rejects_depth_reference_orphans_cycles_and_private_fields(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    root = _write_supported_fixture(source)
    base = dump_document_blueprint(source, path=root).manifest

    orphan = deepcopy(base)
    orphan["nodes"][0]["styleRefs"] = ["style:" + "0" * 64]
    with pytest.raises(AgentContractError):
        validate_blueprint_manifest(with_blueprint_hash(orphan))

    private = deepcopy(base)
    private["nodes"][0]["properties"]["packagePath"] = "Contents/section0.xml"
    with pytest.raises(AgentContractError):
        validate_blueprint_manifest(with_blueprint_hash(private))

    skew = deepcopy(base)
    skew["catalogVersion"] = "hwpx.agent-catalog/v999"
    with pytest.raises(AgentContractError):
        validate_blueprint_manifest(with_blueprint_hash(skew))

    cycle = deepcopy(base)
    first_id = cycle["nodes"][0]["blueprintId"]
    second_id = cycle["nodes"][1]["blueprintId"]
    cycle["nodes"][0]["references"] = ["next"]
    cycle["nodes"][1]["references"] = ["previous"]
    cycle["references"] = [
        {"from": first_id, "field": "next", "to": second_id, "required": True},
        {"from": second_id, "field": "previous", "to": first_id, "required": True},
    ]
    with pytest.raises(AgentContractError):
        validate_blueprint_manifest(with_blueprint_hash(cycle))

    deep = deepcopy(base)
    deep["nodes"] = []
    for index in range(34):
        node_id = f"n{index + 1:06d}"
        child_id = f"n{index + 2:06d}" if index < 33 else None
        deep["nodes"].append(
            {
                "blueprintId": node_id,
                "kind": "paragraph",
                "properties": {"text": str(index)},
                "children": [child_id] if child_id else [],
                "styleRefs": [],
                "numberingRefs": [],
                "resourceRefs": [],
                "references": [],
                "sourceHint": {"nativeId": None, "path": f"/paragraph[{index + 1}]"},
                "support": {"replayable": True, "fidelity": "exact"},
            }
        )
    deep["root"] = {
        "blueprintId": "n000001",
        "kind": "paragraph",
        "sourcePath": "/paragraph[1]",
        "sourceStability": "positional",
    }
    deep["styles"] = []
    deep["resources"] = []
    deep["capabilities"]["kinds"] = ["paragraph"]
    with pytest.raises(AgentContractError) as error:
        validate_blueprint_manifest(with_blueprint_hash(deep))
    assert error.value.code == "resource_limit"


def test_hostile_matrix_has_an_enforced_p2_disposition() -> None:
    matrix = json.loads(
        (Path(__file__).parent / "fixtures/agent_blueprint_hostile_cases.json").read_text(encoding="utf-8")
    )["cases"]
    p2_enforced = {
        "duplicate-blueprint-json",
        "absolute-entry-path",
        "parent-traversal-entry",
        "symlink-entry",
        "nested-archive-entry",
        "xml-entry",
        "unknown-entry",
        "asset-hash-mismatch",
        "asset-mime-mismatch",
        "decompression-ratio-limit",
        "manifest-size-limit",
        "asset-count-limit",
        "asset-size-limit",
        "total-asset-size-limit",
        "node-depth-limit",
        "duplicate-logical-id",
        "missing-child",
        "reference-cycle",
        "orphan-reference",
        "private-coordinate-leak",
        "catalog-version-skew",
    }
    assert set(matrix) - p2_enforced == {"required-oracle-unavailable"}
