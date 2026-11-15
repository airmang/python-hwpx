"""Install a built wheel into a fresh venv and import every declared package.

The test suite runs against an editable install, which reads the source tree and
therefore cannot notice a package that ``[tool.setuptools] packages`` forgot:
6.12.0 shipped without ``hwpx.integrations`` that way. This check installs the
real wheel into an empty virtual environment, runs from a directory outside the
checkout so ``src/`` cannot leak onto ``sys.path``, and imports every package the
pyproject list names.

Usage: python scripts/check_wheel_imports.py dist/python_hwpx-*.whl
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import venv
from collections.abc import Sequence
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]

_PROBE = """\
import importlib
import sys
from pathlib import Path

failures = []
for name in sys.argv[1:]:
    try:
        module = importlib.import_module(name)
    except Exception as exc:  # report every package, not only the first
        failures.append(f"{name}: {type(exc).__name__}: {exc}")
        continue
    origin = Path(next(iter(module.__path__)))
    if "site-packages" not in origin.parts:
        failures.append(f"{name}: imported from {origin}, not the installed wheel")
if failures:
    print("\\n".join(failures))
    raise SystemExit(1)
print(f"[OK] imported {len(sys.argv) - 1} packages from the installed wheel")
"""


def declared_packages(pyproject: Path = ROOT / "pyproject.toml") -> list[str]:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    packages = data["tool"]["setuptools"]["packages"]
    if not isinstance(packages, list) or not packages:
        raise ValueError("pyproject.toml has no explicit [tool.setuptools] packages list")
    return sorted(str(name) for name in packages)


def _venv_python(env_dir: Path) -> Path:
    if sys.platform == "win32":
        return env_dir / "Scripts" / "python.exe"
    return env_dir / "bin" / "python"


def check(wheel: Path, packages: Sequence[str]) -> int:
    wheel = wheel.resolve()
    with tempfile.TemporaryDirectory(prefix="hwpx-wheel-imports-") as scratch:
        env_dir = Path(scratch) / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(env_dir)
        python = _venv_python(env_dir)
        subprocess.run(
            [str(python), "-m", "pip", "install", "--quiet", str(wheel)],
            check=True,
        )
        result = subprocess.run(
            [str(python), "-I", "-c", _PROBE, *packages],
            cwd=scratch,
            check=False,
        )
        return result.returncode


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args(argv)
    return check(args.wheel, declared_packages())


if __name__ == "__main__":
    raise SystemExit(main())
