# SPDX-License-Identifier: Apache-2.0
"""공개 표면 잠금 — 설치본의 공개 표면이 ``tests/data/public_surface.json`` 과 하나도 다르지 않다.

잠금은 최상위 ``hwpx.__all__``, 루트 ``HwpxDocument``, 묶음 11개, ``hwpx.model`` 의 계약 멤버와
계약 밖 이름, ``hwpx.objects`` 값 형식(필드·멤버·enum 값), 모듈 경로로 가져오는 stable 이름을
한 파일에 적는다. 늘어도 줄어도 실패한다. 의도한 변경이면 손으로 고치지 않고 다시 만든다::

    python scripts/public_surface_lock.py check --update --reason "<무엇을 왜>"

바뀐 것마다 ``tests/data/public_surface_changes.jsonl`` 에 한 줄이 남는다. 지우기·이름 바꾸기·서명
바꾸기는 패키지 메이저가 잠금의 메이저보다 클 때만 받는다(다음 메이저를 만드는 동안에는
``--allow-major-break``). git 병합 충돌은 ``rebuild`` 로 다시 만든다.

아래 분류·명령 시험은 실제 이름에 기대지 않는다(이름을 바꾸는 작업이 잠금을 다시 만들어도
그대로 통한다).
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

import public_surface_lock as tool  # scripts/ is on the pytest pythonpath

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "tests" / "data" / "public_surface.json"
LEDGER = ROOT / "tests" / "data" / "public_surface_changes.jsonl"
DOC = ROOT / "docs" / "stable-api.md"


@pytest.fixture(scope="module")
def lock() -> dict[str, Any]:
    return tool.read_lock(LOCK)


@pytest.fixture(scope="module")
def live(lock: dict[str, Any]) -> dict[str, Any]:
    return tool.build_live(tool.contract_of(lock), major=lock["major"])


# --------------------------------------------------------------------------------------------------
# 잠금 = 설치본


def test_public_surface_matches_the_lock(lock: dict[str, Any], live: dict[str, Any]) -> None:
    changes = tool.compare(lock, live)
    assert not changes, tool.explain(
        changes, lock_name="tests/data/public_surface.json", lock_major=lock["major"], major=tool.package_major()
    )


def test_every_layer_of_the_surface_is_in_the_lock(lock: dict[str, Any]) -> None:
    import hwpx
    import hwpx.model as model
    import hwpx.objects as objects
    from hwpx._document.ns import NAMESPACES

    assert set(lock["top"]) == set(hwpx.__all__)
    assert set(lock["namespaces"]) == set(NAMESPACES)
    assert all(lock["namespaces"].values()), "빈 묶음이 있다"
    assert set(lock["model"]) == set(model.__all__)
    assert set(lock["objects"]) == set(objects.__all__)
    assert set(lock["module"]) == set(tool.MODULE_NAMES)


def test_lock_file_is_written_by_the_tool(lock: dict[str, Any]) -> None:
    """손으로 고친 잠금은 다음에 다시 만들 때 조용히 사라진다 — 파일은 도구가 쓴 그대로여야 한다."""

    assert LOCK.read_bytes().decode("utf-8").replace("\r\n", "\n") == tool.dumps(lock), (
        f"잠금 파일이 도구가 쓰는 모양과 다르다. 다시 만든다: python {tool.SCRIPT} check --update --reason ..."
    )


def test_lock_major_is_not_behind_the_package(lock: dict[str, Any]) -> None:
    assert lock["schemaVersion"] == tool.SCHEMA
    assert lock["major"] >= tool.package_major()


def test_stable_api_doc_table_is_the_lock(lock: dict[str, Any]) -> None:
    table = tool.doc_table_in(DOC.read_text(encoding="utf-8"))
    assert table == tool.render_doc_table(lock), (
        f"docs/stable-api.md 의 잠금 표가 잠금과 다르다. 다시 쓴다: python {tool.SCRIPT} check --update"
    )


def test_change_ledger_lines_are_well_formed() -> None:
    lines = [line for line in LEDGER.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines, "장부가 비었다(잠금을 만든 줄이 있어야 한다)"
    for number, line in enumerate(lines, 1):
        assert not line.startswith(("<<<<<<<", "=======", ">>>>>>>")), f"{number}줄: 병합 충돌 표시"
        row = json.loads(line)
        assert set(row) == {"date", "version", "kind", "change", "reason"}, number
        assert row["kind"] in {"created", "breaking", "additive", "other"}, number
        assert row["change"].strip() and row["reason"].strip(), number
    assert json.loads(lines[0])["kind"] == "created"


# --------------------------------------------------------------------------------------------------
# 무엇이 깨짐이고 무엇이 더함인가 (만든 잠금으로)


def _method(*params: list[Any], returns: str | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {"kind": "method", "params": [list(p) for p in params]}
    if returns:
        entry["returns"] = returns
    return entry


def _surface() -> dict[str, Any]:
    return {
        "schemaVersion": tool.SCHEMA,
        "major": 6,
        "top": {"doc_diff": {"kind": "function", "params": [["old", "P", False], ["new", "P", False]]}},
        "root": {"add_section": _method(["after", "K", True], returns="Section")},
        "namespaces": {"tables": {"map": _method(returns="TableMapResult")}},
        "model": {
            "Table": {
                "members": {
                    "cell": _method(["row_index", "P", False], ["col_index", "P", False], returns="TableCell"),
                    "get_cell_map": _method(returns="list[list[GridPosition]]"),
                    "alignment": {"kind": "property", "settable": False, "returns": "str"},
                },
                "internal": ["mark_dirty"],
            },
            "Paragraph": {"members": {"runs": {"kind": "property", "settable": False, "returns": "tuple[Run, ...]"}}, "internal": []},
        },
        "objects": {
            "BorderLine": {"kind": "dataclass", "fields": [["type", "str"], ["width", "str"], ["color", "str"]], "members": {}},
            "Alignment": {"kind": "enum", "values": {"LEFT": "LEFT", "RIGHT": "RIGHT"}},
        },
        "module": {"hwpx.errors": {"HwpxError": {"kind": "class", "bases": ["Exception", "BaseException"], "members": {}}}},
    }


def _changes(edit) -> tool.Changes:
    old = _surface()
    new = copy.deepcopy(old)
    edit(new)
    return tool.compare(old, new)


def test_a_removed_or_renamed_name_is_breaking_and_an_added_one_is_additive() -> None:
    def rename(new: dict[str, Any]) -> None:
        new["namespaces"]["tables"]["table_map"] = new["namespaces"]["tables"].pop("map")
        new["top"].pop("doc_diff")

    changes = _changes(rename)
    assert changes.breaking == ["hwpx.doc_diff: __all__에서 없어짐", "doc.tables.map: 없어짐"]
    assert changes.additive == ["doc.tables.table_map: 생김"]


def test_signature_changes_are_classified() -> None:
    def edit(new: dict[str, Any]) -> None:
        new["model"]["Table"]["members"]["cell"]["params"] = [["row", "P", False], ["col", "P", False], ["fallback", "K", True]]
        new["model"]["Paragraph"]["members"]["runs"]["returns"] = "list[Run]"

    changes = _changes(edit)
    assert "model.Table.cell: 위치 인자 ['row_index', 'col_index'] -> ['row', 'col']" in changes.breaking
    assert "model.Table.cell: 인자 없어짐 row_index" in changes.breaking
    assert "model.Table.cell: 반드시 줘야 하는 인자 생김 row" in changes.breaking
    assert "model.Paragraph.runs: 반환 tuple[Run, ...] -> list[Run]" in changes.breaking
    assert changes.additive == ["model.Table.cell: 인자 생김 fallback"]


def test_optional_keywords_and_new_setters_only_add() -> None:
    def edit(new: dict[str, Any]) -> None:
        new["root"]["add_section"]["params"].append(["copy_page_setup", "K", True])
        new["model"]["Table"]["members"]["alignment"]["settable"] = True
        new["module"]["hwpx.errors"]["HwpxError"]["bases"].insert(0, "ValueError")

    changes = _changes(edit)
    assert changes.breaking == []
    assert changes.additive == [
        "doc.add_section: 인자 생김 copy_page_setup",
        "model.Table.alignment: 쓰기 생김",
        "hwpx.errors.HwpxError: 바탕 클래스 생김 ['ValueError']",
    ]


def test_contract_renames_and_demotions_are_breaking() -> None:
    def edit(new: dict[str, Any]) -> None:
        table = new["model"]["Table"]
        table["members"].pop("get_cell_map")
        table["members"].pop("alignment")
        table["internal"] = ["alignment", "cell_map", "mark_dirty"]

    changes = _changes(edit)
    assert changes.breaking == ["model.Table.get_cell_map: 없어짐", "model.Table.alignment: 계약에서 내림(계약 밖으로)"]
    assert changes.other == ["model.Table.cell_map: 계약 밖 공개 이름 생김 (계약이면 --contract Table.cell_map)"]


def test_value_type_fields_and_enum_values_are_locked() -> None:
    def edit(new: dict[str, Any]) -> None:
        new["objects"]["BorderLine"]["fields"] = [["type", "str"], ["color", "str"], ["width_mm", "float"]]
        new["objects"]["Alignment"]["values"] = {"LEFT": "LEFT", "CENTER": "CENTER"}

    changes = _changes(edit)
    assert changes.breaking == ["objects.Alignment: 값 없어짐 ['RIGHT']", "objects.BorderLine: 필드 없어짐 ['width']"]
    assert changes.additive == ["objects.Alignment: 값 생김 ['CENTER']", "objects.BorderLine: 필드 생김 ['width_mm']"]


def test_a_hand_edit_the_classifier_cannot_name_still_differs() -> None:
    changes = _changes(lambda new: new["top"]["doc_diff"].update(note="hand edit"))
    assert changes.breaking and "다시 만들면" in changes.breaking[0]


# --------------------------------------------------------------------------------------------------
# 명령: 검사 → 고치는 법 → 다시 만들기 → 메이저 문 (저장소 잠금의 사본으로)


_EXTRA = {"kind": "method", "params": [], "returns": "None"}


@pytest.fixture
def sandbox(tmp_path: Path, lock: dict[str, Any], monkeypatch: pytest.MonkeyPatch):
    """잠금·장부·문서의 사본. 설치본 실측은 계약 분류마다 한 번만 한다."""

    built: dict[tuple, dict[str, Any]] = {}
    real = tool.build_live

    def cached(contract, *, major=None):
        key = (tuple(sorted((name, tuple(sorted(members))) for name, members in contract.items())), major)
        if key not in built:
            built[key] = real(contract, major=major)
        return copy.deepcopy(built[key])

    monkeypatch.setattr(tool, "build_live", cached)
    paths = {"lock": tmp_path / "public_surface.json", "ledger": tmp_path / "changes.jsonl", "doc": tmp_path / "stable-api.md"}
    tool.write_lock(lock, paths["lock"])
    paths["ledger"].write_text("", encoding="utf-8")
    paths["doc"].write_bytes(DOC.read_bytes())

    def run(*argv: str) -> int:
        command, *rest = argv
        return tool.main([command, "--lock", str(paths["lock"]), "--doc", str(paths["doc"]), "--ledger", str(paths["ledger"]), *rest])

    def edit_lock(change) -> None:
        current = tool.read_lock(paths["lock"])
        change(current)
        tool.write_lock(current, paths["lock"])

    def ledger() -> list[dict[str, Any]]:
        return [json.loads(line) for line in paths["ledger"].read_text(encoding="utf-8").splitlines() if line]

    return run, edit_lock, ledger, paths


def _some_namespace_member(lock: dict[str, Any]) -> tuple[str, str]:
    namespace = sorted(lock["namespaces"])[0]
    return namespace, sorted(lock["namespaces"][namespace])[-1]


def test_check_passes_on_the_repository_lock(sandbox, capsys) -> None:
    run, *_ = sandbox
    assert run("check") == 0
    assert "공개 표면이 잠금과 같다" in capsys.readouterr().out


def test_check_says_what_differs_and_how_to_fix_it(sandbox, lock, capsys) -> None:
    run, edit_lock, ledger, _ = sandbox
    namespace, member = _some_namespace_member(lock)

    def drift(current: dict[str, Any]) -> None:
        current["namespaces"][namespace]["gone_method"] = _EXTRA
        current["namespaces"][namespace].pop(member)

    edit_lock(drift)
    assert run("check") == 1
    out = capsys.readouterr().out
    assert f"깨짐  doc.{namespace}.gone_method: 없어짐" in out
    assert f"더함  doc.{namespace}.{member}: 생김" in out
    assert 'check --update --reason "<무엇을 왜>"' in out
    assert "--allow-major-break" in out
    assert "rebuild" in out
    assert ledger() == []


def test_update_needs_a_reason(sandbox, lock, capsys) -> None:
    run, edit_lock, ledger, _ = sandbox
    namespace, member = _some_namespace_member(lock)
    edit_lock(lambda current: current["namespaces"][namespace].pop(member))
    assert run("check", "--update") == 2
    assert "--reason" in capsys.readouterr().out
    assert ledger() == []


def test_an_addition_is_taken_with_a_reason_and_logged(sandbox, lock) -> None:
    run, edit_lock, ledger, paths = sandbox
    namespace, member = _some_namespace_member(lock)
    edit_lock(lambda current: current["namespaces"][namespace].pop(member))
    assert run("check", "--update", "--reason", "test: an addition") == 0
    assert tool.read_lock(paths["lock"]) == lock
    rows = ledger()
    assert [(row["kind"], row["change"], row["reason"]) for row in rows] == [
        ("additive", f"doc.{namespace}.{member}: 생김", "test: an addition")
    ]
    assert rows[0]["version"] == tool.package_version()
    assert run("check") == 0


def test_a_break_waits_for_the_next_major(sandbox, lock, capsys) -> None:
    """다음 메이저를 만드는 동안(7.0 개발 중 패키지는 6.x): 깨짐은 --allow-major-break로만 받고,
    잠금의 major는 패키지 메이저 + 1(7)이 된다."""

    run, edit_lock, ledger, paths = sandbox
    major = tool.package_major()
    namespace, _ = _some_namespace_member(lock)

    def breaking(current: dict[str, Any]) -> None:
        current["namespaces"][namespace]["gone_method"] = _EXTRA

    edit_lock(breaking)
    before = paths["lock"].read_bytes()
    if lock["major"] <= major:  # 패키지가 잠금의 메이저를 넘었으면 문은 이미 열려 있다
        assert run("check", "--update", "--reason", "test: remove gone_method") == 1
        assert "--allow-major-break" in capsys.readouterr().out
        assert paths["lock"].read_bytes() == before
        assert ledger() == []

    assert run("check", "--update", "--reason", "test: remove gone_method", "--allow-major-break") == 0
    updated = tool.read_lock(paths["lock"])
    assert updated["major"] == max(lock["major"], major + 1)
    assert tool.compare(lock, updated).breaking == []
    assert [(row["kind"], row["change"]) for row in ledger()] == [("breaking", f"doc.{namespace}.gone_method: 없어짐")]
    assert run("check") == 0

    # 잠금이 다음 메이저를 적은 뒤에도 패키지가 아직 그 메이저가 아니면 깨짐마다 다시 묻는다.
    edit_lock(breaking)
    assert run("check", "--update", "--reason", "test: again") == 1


def test_a_renamed_contract_member_is_put_back_in_the_contract(sandbox, lock) -> None:
    """계약 이름을 바꾸면 새 이름은 계약 밖으로 잡힌다 — --contract 로 올린다. 내리는 것은 깨짐이다."""

    run, _, ledger, paths = sandbox
    cls = next(name for name, entry in sorted(lock["model"].items()) if entry["internal"])
    promoted = lock["model"][cls]["internal"][0]
    spec = f"{cls}.{promoted}"

    assert run("check", "--update", "--reason", f"test: {spec} into the contract", "--contract", spec) == 0
    updated = tool.read_lock(paths["lock"])["model"][cls]
    assert promoted in updated["members"] and promoted not in updated["internal"]
    assert [row["kind"] for row in ledger()] == ["additive"]
    assert run("check") == 0

    if tool.read_lock(paths["lock"])["major"] <= tool.package_major():
        assert run("check", "--update", "--reason", "test: back out", "--internal", spec) == 1
    assert run("check", "--update", "--reason", "test: back out", "--internal", spec, "--allow-major-break") == 0
    assert promoted in tool.read_lock(paths["lock"])["model"][cls]["internal"]


def test_contract_flags_reject_unknown_names(sandbox, lock) -> None:
    run, *_ = sandbox
    cls = sorted(lock["model"])[0]
    with pytest.raises(SystemExit):
        run("check", "--update", "--reason", "x", "--contract", f"{cls}.no_such_member")
    with pytest.raises(SystemExit):
        run("check", "--update", "--reason", "x", "--contract", "NoSuchClass.text")


def test_the_doc_table_is_rewritten_with_the_lock(sandbox, lock, capsys) -> None:
    run, _, _, paths = sandbox
    original = paths["doc"].read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in original else "\n"
    text = original.replace("\r\n", "\n")
    table = tool.doc_table_in(text)
    assert table is not None
    top = tool.counts(lock)["top"]
    broken = text.replace(table, table.replace(f"| {top} |", f"| {top + 1} |", 1))
    assert broken != text
    paths["doc"].write_bytes(broken.replace("\n", newline).encode("utf-8"))
    assert run("check") == 1
    assert "check --update" in capsys.readouterr().out
    assert run("check", "--update") == 0
    assert paths["doc"].read_bytes().decode("utf-8") == original


# --------------------------------------------------------------------------------------------------
# 병합: 손으로 합치지 않고 다시 만든다


def _lock_with(contract: dict[str, list[str]]) -> dict[str, Any]:
    model = {name: {"members": {member: {} for member in members}, "internal": []} for name, members in contract.items()}
    return {"major": 6, "model": model}


def test_merge_keeps_what_both_sides_kept_and_whatever_either_side_promoted() -> None:
    base = _lock_with({"Table": ["cell", "get_cell_map", "alignment"], "Document": ["char_property", "styles"]})
    ours = _lock_with({"Table": ["cell", "get_cell_map", "alignment", "page_split"], "Document": ["char_property", "styles"]})
    # 상대 쪽: get_cell_map → cell_map(이름 바꿈), char_property는 계약에서 내림
    theirs = _lock_with({"Table": ["cell", "cell_map", "alignment"], "Document": ["styles"]})

    merged = tool.merge_contract(base, ours, theirs)
    assert merged["Table"] == {"cell", "cell_map", "alignment", "page_split"}
    assert merged["Document"] == {"styles"}
    # 바탕이 없으면(두 쪽이 처음 만든 잠금) 합집합
    assert tool.merge_contract(None, ours, theirs)["Document"] == {"char_property", "styles"}


def test_rebuild_rewrites_a_conflicted_doc_table_but_not_other_conflicts(tmp_path: Path, lock: dict[str, Any]) -> None:
    rendered = tool.render_doc_table(lock)
    rows = rendered.split("\n")
    conflicted = [*rows[:4], "<<<<<<< HEAD", rows[4], "=======", rows[4] + " (상대)", ">>>>>>> theirs", *rows[5:]]
    doc = tmp_path / "stable-api.md"
    doc.write_text("\n".join(["# 문서", "", *conflicted, "끝", ""]), encoding="utf-8", newline="\n")
    assert tool.sync_doc(lock, doc, resolve_conflicts=True)
    text = doc.read_text(encoding="utf-8")
    assert "<<<<<<<" not in text and tool.doc_table_in(text) == rendered

    outside = "\n".join(["<<<<<<< HEAD", "우리 문장", "=======", "상대 문장", ">>>>>>> theirs", rendered, ""])
    doc.write_text(outside, encoding="utf-8", newline="\n")
    with pytest.raises(tool.DocConflict):
        tool.sync_doc(lock, doc, resolve_conflicts=True)


def test_rebuild_on_a_clean_lock_changes_nothing(sandbox, lock) -> None:
    run, _, ledger, paths = sandbox
    assert run("rebuild") == 0
    assert tool.read_lock(paths["lock"]) == lock
    assert ledger() == []


# 실제 git 병합 — 만든 잠금과, 계약 분류대로 표면을 돌려주는 가짜 실측으로


_TABLE_MEMBERS = {
    "cell": _method(["row", "P", False], ["col", "P", False], returns="TableCell"),
    "get_cell_map": _method(returns="list[list[GridPosition]]"),
    "cell_map": {"kind": "property", "settable": False, "returns": "tuple[tuple[GridPosition, ...], ...]"},
    "alignment": {"kind": "property", "settable": False, "returns": "str"},
    "page_split": {"kind": "property", "settable": True, "returns": "str"},
    "mark_dirty": _method(returns="None"),
}


def _surface_of(
    contract: dict[str, set[str]], *, table: set[str], tables: set[str], major: int | None = None
) -> dict[str, Any]:
    """코드에 ``table`` 의 Table 멤버와 ``tables`` 의 doc.tables 멤버가 있을 때 잠금이 적을 표면."""

    surface = _surface()
    surface["major"] = tool.package_major() if major is None else major
    surface["namespaces"]["tables"] = {name: _method(returns="None") for name in sorted(tables)}
    wanted = contract.get("Table", set())
    surface["model"]["Table"] = {
        "members": {name: _TABLE_MEMBERS[name] for name in sorted(table) if name in wanted},
        "internal": sorted(name for name in table if name not in wanted),
    }
    return surface


class _Repo:
    def __init__(self, root: Path) -> None:
        self.root = root
        (root / "tests" / "data").mkdir(parents=True)
        (root / "docs").mkdir()
        self.git("init", "-q")
        self.git("checkout", "-q", "-b", "main")
        (root / ".gitattributes").write_text("/tests/data/public_surface_changes.jsonl merge=union\n", encoding="utf-8")

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
             "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false", *args],
            capture_output=True, check=False,
        )
        if result.returncode not in (0, 1) or (result.returncode == 1 and args[0] != "merge"):
            raise AssertionError(result.stderr.decode("utf-8", "replace"))
        return result.stdout.decode("utf-8", "replace")

    @property
    def lock(self) -> Path:
        return self.root / "tests" / "data" / "public_surface.json"

    @property
    def ledger(self) -> Path:
        return self.root / "tests" / "data" / "public_surface_changes.jsonl"

    @property
    def doc(self) -> Path:
        return self.root / "docs" / "stable-api.md"

    @property
    def legacy(self) -> Path:
        return self.root / "tests" / "data" / "model_surface.json"

    def put_lock(self, surface: dict[str, Any], ledger_line: str | None = None) -> None:
        tool.write_lock(surface, self.lock)
        self.doc.write_text(f"# 표면\n\n{tool.render_doc_table(surface)}\n\n끝\n", encoding="utf-8", newline="\n")
        if ledger_line is not None:
            row = {"date": "2026-11-16", "version": "6.12.0", "kind": "additive", "change": ledger_line, "reason": "t"}
            with self.ledger.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def commit(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def rebuild(self, *extra: str) -> int:
        return tool.main(["rebuild", "--lock", str(self.lock), "--ledger", str(self.ledger), "--doc", str(self.doc), *extra])


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    if shutil.which("git") is None:
        pytest.skip("git이 없다")
    seen: list[dict[str, set[str]]] = []
    code = {"table": set(), "tables": set()}

    def fake_build_live(contract, *, major=None):
        seen.append({name: set(members) for name, members in contract.items()})
        return _surface_of(contract, table=code["table"], tables=code["tables"], major=major)

    monkeypatch.setattr(tool, "build_live", fake_build_live)
    return _Repo(tmp_path / "repo"), code, seen


@pytest.mark.parametrize("conflict", [True, False], ids=["conflicted", "auto-merged"])
def test_rebuild_after_a_git_merge_takes_both_sides(repo, conflict: bool) -> None:
    git, code, seen = repo
    base_contract = {"Table": {"cell", "get_cell_map", "alignment"}}
    base_table = {"cell", "get_cell_map", "alignment", "mark_dirty"}
    git.put_lock(_surface_of(base_contract, table=base_table, tables={"map"}))
    git.ledger.write_text(json.dumps({"date": "2026-11-16", "version": "6.12.0", "kind": "created", "change": "c", "reason": "t"}) + "\n", encoding="utf-8")
    git.commit("base")

    # 우리 가지: Table.get_cell_map → cell_map(계약 이름 바꿈)과, 충돌을 낼 때는 doc.tables 앞자리에 하나 더
    git.git("checkout", "-q", "-b", "ours")
    ours_contract = {"Table": {"cell", "cell_map", "alignment"}}
    ours_table = {"cell", "cell_map", "alignment", "mark_dirty"}
    ours_tables = {"aaa", "map"} if conflict else {"map"}
    git.put_lock(_surface_of(ours_contract, table=ours_table, tables=ours_tables), "model.Table.get_cell_map: 없어짐")
    git.commit("ours")

    # 상대(main): doc.tables 뒷자리에 하나
    git.git("checkout", "-q", "main")
    git.put_lock(_surface_of(base_contract, table=base_table, tables={"map", "zzz"}), "doc.tables.zzz: 생김")
    git.commit("theirs")

    git.git("checkout", "-q", "ours")
    git.git("merge", "-q", "--no-edit", "main")
    conflicted = bool(git.git("ls-files", "-u").strip())
    assert conflicted is conflict

    code["table"], code["tables"] = ours_table, ours_tables | {"zzz"}
    assert git.rebuild() == 0
    assert seen[-1]["Table"] == {"cell", "cell_map", "alignment"}
    expected = _surface_of(seen[-1], table=ours_table, tables=ours_tables | {"zzz"})
    assert tool.read_lock(git.lock) == expected
    rows = [json.loads(line)["change"] for line in git.ledger.read_text(encoding="utf-8").splitlines()]
    assert rows[0] == "c" and sorted(rows[1:]) == ["doc.tables.zzz: 생김", "model.Table.get_cell_map: 없어짐"]
    assert tool.doc_table_in(git.doc.read_text(encoding="utf-8")) == tool.render_doc_table(expected)


def test_rebuild_refuses_a_change_neither_side_logged(repo) -> None:
    git, code, _ = repo
    contract = {"Table": {"cell"}}
    git.put_lock(_surface_of(contract, table={"cell"}, tables={"map"}))
    git.ledger.write_text("", encoding="utf-8")
    git.commit("base")
    git.git("checkout", "-q", "-b", "ours")
    git.put_lock(_surface_of(contract, table={"cell"}, tables={"map", "aaa"}), "doc.tables.aaa: 생김")
    git.commit("ours")
    git.git("checkout", "-q", "main")
    git.put_lock(_surface_of(contract, table={"cell"}, tables={"map", "zzz"}), "doc.tables.zzz: 생김")
    git.commit("theirs")
    git.git("checkout", "-q", "ours")
    git.git("merge", "-q", "--no-edit", "main")

    # 병합된 코드에 어느 쪽도 적지 않은 이름이 하나 더 있다(잠금을 다시 만들지 않은 커밋).
    code["table"], code["tables"] = {"cell"}, {"map", "aaa", "zzz", "unlogged"}
    before = git.lock.read_bytes()
    assert git.rebuild() == 1
    assert git.lock.read_bytes() == before
    assert git.rebuild("--reason", "ours: unlogged") == 0
    rows = [json.loads(line) for line in git.ledger.read_text(encoding="utf-8").splitlines()]
    assert (rows[-1]["change"], rows[-1]["reason"]) == ("doc.tables.unlogged: 생김", "ours: unlogged")


def test_rebuild_carries_an_old_branch_model_surface_contract(repo) -> None:
    """이 잠금 전에 갈라진 가지: 그 가지가 model_surface.json에서 계약에 올리고 내린 것을 옮겨 온다."""

    git, code, seen = repo

    def legacy(stable: list[str]) -> str:
        return json.dumps({"classes": {"Table": {"implementation": "x", "internalCount": 0, "stable": stable}}})

    git.legacy.write_text(legacy(["alignment", "cell", "get_cell_map"]), encoding="utf-8")
    git.doc.write_text("# 표면\n", encoding="utf-8")
    git.commit("base: the old model lock")

    git.git("checkout", "-q", "-b", "old")  # 옛 잠금 위에서: page_split을 계약에 올리고 alignment를 내렸다
    git.legacy.write_text(legacy(["cell", "get_cell_map", "page_split"]), encoding="utf-8")
    git.commit("old branch")

    git.git("checkout", "-q", "main")  # main은 새 잠금으로 바꿨다
    git.legacy.unlink()
    table = {"cell", "get_cell_map", "alignment", "mark_dirty"}
    git.put_lock(_surface_of({"Table": {"cell", "get_cell_map", "alignment"}}, table=table, tables={"map"}))
    git.ledger.write_text(json.dumps({"date": "2026-11-16", "version": "6.12.0", "kind": "created", "change": "c", "reason": "t"}) + "\n", encoding="utf-8")
    git.commit("new lock")

    git.git("checkout", "-q", "old")
    git.git("merge", "-q", "--no-edit", "main")  # model_surface.json: 고침/지움 충돌
    git.git("rm", "-q", "tests/data/model_surface.json")

    code["table"], code["tables"] = table | {"page_split"}, {"map"}
    assert git.rebuild() == 1  # 옛 가지의 변경은 장부에 없다
    assert seen[-1]["Table"] == {"cell", "get_cell_map", "page_split"}
    assert git.rebuild("--reason", "old: page_split") == 1  # alignment를 내린 것은 깨짐
    assert git.rebuild("--reason", "old: page_split", "--allow-major-break") == 0
    merged = tool.read_lock(git.lock)
    assert sorted(merged["model"]["Table"]["members"]) == ["cell", "get_cell_map", "page_split"]
    assert merged["major"] == tool.package_major() + 1
    changes = {json.loads(line)["change"] for line in git.ledger.read_text(encoding="utf-8").splitlines()}
    assert {"model.Table.alignment: 계약에서 내림(계약 밖으로)", "model.Table.page_split: 계약에 생김"} <= changes
