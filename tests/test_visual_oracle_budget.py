# SPDX-License-Identifier: Apache-2.0
"""S-081 oracle budget/reachability contract.

The optional GUI oracle must never out-wait its caller: a TCC-blocked or
GUI-less environment degrades within the probe timeout, an external budget
clamps every subprocess timeout, and structural-only mode provably never
enters GUI automation.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

import hwpx.visual.oracle as oracle_module
from hwpx.visual.oracle import (
    MacHancomOracle,
    NullOracle,
    WindowsComOracle,
    resolve_oracle,
    structural_only,
)


@pytest.fixture(autouse=True)
def _fresh_probe_cache(monkeypatch):
    monkeypatch.setattr(oracle_module, "_MAC_PROBE_CACHE", {})


def _spy_run(calls, *, returncode=0, raise_timeout=False):
    def run(cmd, **kwargs):
        calls.append({"cmd": list(cmd), "kwargs": kwargs})
        if raise_timeout:
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout") or 0)
        return subprocess.CompletedProcess(cmd, returncode, stdout="", stderr="")

    return run


# --- structural-only -------------------------------------------------------


def test_structural_only_env_parsing(monkeypatch) -> None:
    monkeypatch.delenv("HWPX_ORACLE_STRUCTURAL_ONLY", raising=False)
    assert structural_only() is False
    for value in ("1", "true", "YES", " On "):
        monkeypatch.setenv("HWPX_ORACLE_STRUCTURAL_ONLY", value)
        assert structural_only() is True
    monkeypatch.setenv("HWPX_ORACLE_STRUCTURAL_ONLY", "0")
    assert structural_only() is False


def test_structural_only_disables_mac_oracle_even_with_hancom(monkeypatch) -> None:
    monkeypatch.setenv("HWPX_ORACLE_STRUCTURAL_ONLY", "1")
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(MacHancomOracle, "_app_path", lambda self: "/Applications/Fake.app")
    calls: list[dict] = []
    monkeypatch.setattr(subprocess, "run", _spy_run(calls))
    assert MacHancomOracle().available() is False
    assert calls == []  # not even the probe runs


def test_structural_only_resolves_to_null_oracle(monkeypatch) -> None:
    monkeypatch.setenv("HWPX_ORACLE_STRUCTURAL_ONLY", "1")
    monkeypatch.setattr(WindowsComOracle, "available", lambda self: True)
    monkeypatch.setattr(MacHancomOracle, "available", lambda self: True)
    assert isinstance(resolve_oracle(), NullOracle)


def test_structural_only_never_enters_gui_render(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HWPX_ORACLE_STRUCTURAL_ONLY", "1")
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(MacHancomOracle, "_app_path", lambda self: "/Applications/Fake.app")
    calls: list[dict] = []
    monkeypatch.setattr(subprocess, "run", _spy_run(calls))
    src = tmp_path / "in.hwpx"
    src.write_bytes(b"x")
    oracle = MacHancomOracle()
    assert oracle.render_pdf(str(src), str(tmp_path / "out.pdf")) is None
    assert oracle.refresh_document(str(src)) is False
    assert calls == []  # zero GUI automation entries


# --- reachability probe ----------------------------------------------------


def _darwin_with_app(monkeypatch) -> None:
    monkeypatch.delenv("HWPX_ORACLE_STRUCTURAL_ONLY", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(MacHancomOracle, "_app_path", lambda self: "/Applications/Fake.app")


def test_probe_failure_degrades_available(monkeypatch) -> None:
    _darwin_with_app(monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(subprocess, "run", _spy_run(calls, raise_timeout=True))
    assert MacHancomOracle().available() is False
    assert len(calls) == 1
    assert calls[0]["kwargs"]["timeout"] == oracle_module._MAC_PROBE_TIMEOUT
    assert calls[0]["kwargs"]["timeout"] <= 5.0


def test_probe_denied_tcc_degrades_available(monkeypatch) -> None:
    _darwin_with_app(monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(subprocess, "run", _spy_run(calls, returncode=1))
    assert MacHancomOracle().available() is False


def test_probe_success_enables_available(monkeypatch) -> None:
    _darwin_with_app(monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(subprocess, "run", _spy_run(calls, returncode=0))
    assert MacHancomOracle().available() is True


def test_probe_is_cached_per_process(monkeypatch) -> None:
    _darwin_with_app(monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(subprocess, "run", _spy_run(calls, returncode=0))
    oracle = MacHancomOracle()
    assert oracle.available() is True
    assert oracle.available() is True
    assert MacHancomOracle().available() is True  # new instance, same process
    assert len(calls) == 1


# --- deadline propagation --------------------------------------------------


def test_mac_budget_clamps_subprocess_timeout(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("HWPX_ORACLE_STRUCTURAL_ONLY", raising=False)
    monkeypatch.setattr(MacHancomOracle, "available", lambda self: True)
    calls: list[dict] = []
    monkeypatch.setattr(subprocess, "run", _spy_run(calls))
    src = tmp_path / "in.hwpx"
    src.write_bytes(b"x")
    oracle = MacHancomOracle(budget_seconds=10.0)
    oracle.render_pdf(str(src), str(tmp_path / "out.pdf"))
    assert len(calls) == 1
    assert calls[0]["kwargs"]["timeout"] <= 10.0  # clamped below 300+60
    script_wait = int(calls[0]["cmd"][-1])
    assert script_wait <= 10  # AppleScript internal wait inside the budget


def test_mac_exhausted_budget_never_spawns(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("HWPX_ORACLE_STRUCTURAL_ONLY", raising=False)
    monkeypatch.setattr(MacHancomOracle, "available", lambda self: True)
    calls: list[dict] = []
    monkeypatch.setattr(subprocess, "run", _spy_run(calls))
    src = tmp_path / "in.hwpx"
    src.write_bytes(b"x")
    oracle = MacHancomOracle(budget_seconds=0.0)
    assert oracle.render_pdf(str(src), str(tmp_path / "out.pdf")) is None
    assert oracle.refresh_document(str(src)) is False
    assert calls == []


def test_windows_budget_clamps_and_degrades(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(WindowsComOracle, "available", lambda self: True)
    calls: list[dict] = []
    monkeypatch.setattr(subprocess, "run", _spy_run(calls))
    src = tmp_path / "in.hwpx"
    src.write_bytes(b"x")

    exhausted = WindowsComOracle(budget_seconds=0.0)
    assert exhausted.render_many([(str(src), str(tmp_path / "o.pdf"))]) == {str(src): None}
    entries = exhausted.open_check_many([str(src)])
    assert [e["status"] for e in entries] == ["unverified"]
    assert calls == []

    bounded = WindowsComOracle(budget_seconds=15.0)
    bounded.render_many([(str(src), str(tmp_path / "o.pdf"))])
    assert len(calls) == 1
    assert calls[0]["kwargs"]["timeout"] <= 15.0


def test_resolve_oracle_propagates_budget(monkeypatch) -> None:
    monkeypatch.delenv("HWPX_ORACLE_STRUCTURAL_ONLY", raising=False)
    monkeypatch.setattr(WindowsComOracle, "available", lambda self: False)
    monkeypatch.setattr(MacHancomOracle, "available", lambda self: True)
    backend = resolve_oracle(budget_seconds=42.0)
    assert isinstance(backend, MacHancomOracle)
    assert backend.budget_seconds == 42.0


def test_resolve_oracle_reads_env_budget(monkeypatch) -> None:
    """One externally-declared deadline reaches every resolve_oracle() caller."""

    monkeypatch.delenv("HWPX_ORACLE_STRUCTURAL_ONLY", raising=False)
    monkeypatch.setattr(WindowsComOracle, "available", lambda self: False)
    monkeypatch.setattr(MacHancomOracle, "available", lambda self: True)

    monkeypatch.setenv("HWPX_ORACLE_BUDGET_SECONDS", "75")
    backend = resolve_oracle()
    assert isinstance(backend, MacHancomOracle)
    assert backend.budget_seconds == 75.0

    # Explicit parameter wins over the environment.
    assert resolve_oracle(budget_seconds=10.0).budget_seconds == 10.0

    # Invalid values are ignored; negative values mean exhausted.
    monkeypatch.setenv("HWPX_ORACLE_BUDGET_SECONDS", "abc")
    assert resolve_oracle().budget_seconds is None
    monkeypatch.setenv("HWPX_ORACLE_BUDGET_SECONDS", "-5")
    assert resolve_oracle().budget_seconds == 0.0
