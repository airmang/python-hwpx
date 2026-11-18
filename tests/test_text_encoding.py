"""Nothing in the repository leans on the platform's default text encoding.

On an English Windows the default is cp1252, which cannot hold Korean; a Korean Windows has cp949, and a run
with ``PYTHONUTF8=1`` has UTF-8 -- which is how such calls went unnoticed until the Windows CI job. Every
text-mode file read or write and every text-mode subprocess names its encoding.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SUBPROCESS = {"run", "Popen", "check_output", "check_call", "call"}
_FIXTURE = ROOT / "tests" / "fixtures" / "hancom_saved" / "pages_footnotes_in_table_cells.hwpx"


def _keyword(node: ast.Call, name: str) -> ast.expr | None:
    return next((k.value for k in node.keywords if k.arg == name), None)


def _text_mode(mode: ast.expr | None) -> bool:
    if mode is None:
        return True
    return isinstance(mode, ast.Constant) and isinstance(mode.value, str) and "b" not in mode.value


def _default_encoding_calls(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _keyword(node, "encoding") is not None:
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
        if name == "read_text" and isinstance(func, ast.Attribute) and not node.args:
            found.append(f"{node.lineno} read_text")
        elif name == "write_text" and isinstance(func, ast.Attribute) and len(node.args) == 1:
            found.append(f"{node.lineno} write_text")
        elif name == "open" and isinstance(func, ast.Name):
            if _text_mode(_keyword(node, "mode") or (node.args[1] if len(node.args) > 1 else None)):
                found.append(f"{node.lineno} open")
        elif name == "open" and isinstance(func, ast.Attribute):
            mode = _keyword(node, "mode") or (node.args[0] if node.args else None)
            if (isinstance(mode, ast.Constant) and isinstance(mode.value, str) and "b" not in mode.value
                    and set(mode.value) <= set("rwax+t")):
                found.append(f"{node.lineno} Path.open")
        elif name in _SUBPROCESS and isinstance(func, ast.Attribute) and getattr(func.value, "id", "") == "subprocess":
            text = _keyword(node, "text") or _keyword(node, "universal_newlines")
            if isinstance(text, ast.Constant) and text.value is True:
                found.append(f"{node.lineno} subprocess text")
        elif name == "TextIOWrapper":
            found.append(f"{node.lineno} TextIOWrapper")
    return found


def test_no_text_io_uses_the_platform_default_encoding() -> None:
    offenders = []
    for folder in ("src", "tests", "scripts", "probes"):
        for path in sorted((ROOT / folder).rglob("*.py")):
            offenders += [f"{path.relative_to(ROOT).as_posix()}:{hit}" for hit in _default_encoding_calls(path)]
    assert not offenders, "name the encoding (encoding=\"utf-8\"):\n" + "\n".join(offenders)


def test_text_extract_prints_korean_through_a_stdout_that_cannot_hold_it() -> None:
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}
    completed = subprocess.run(
        [sys.executable, "-m", "hwpx.tools.text_extract_cli", str(_FIXTURE)],
        capture_output=True,
        env=environment,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    assert "줄 0" in completed.stdout.decode("utf-8")
