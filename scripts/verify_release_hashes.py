"""Verify one published release against its single-build hash manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import time
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from urllib.error import HTTPError, URLError

PROJECT = "python-hwpx"
VERSION = "5.0.0"
PYPI_URL = f"https://pypi.org/pypi/{PROJECT}/{VERSION}/json"
HASH_LINE = re.compile(r"^(?P<digest>[0-9a-f]{64})  (?P<filename>[^/\\\\]+)$")


def read_manifest(path: Path) -> dict[str, str]:
    """Read the exact wheel/sdist manifest and reject ambiguous filenames."""

    expected: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = HASH_LINE.fullmatch(line)
        if match is None:
            raise ValueError(f"invalid SHA256SUMS line: {line!r}")
        filename = match.group("filename")
        if filename in expected:
            raise ValueError(f"duplicate SHA256SUMS filename: {filename}")
        expected[filename] = match.group("digest")
    wheels = [name for name in expected if name.endswith(".whl")]
    sdists = [name for name in expected if name.endswith(".tar.gz")]
    if len(expected) != 2 or len(wheels) != 1 or len(sdists) != 1:
        raise ValueError("SHA256SUMS must contain exactly one wheel and one sdist")
    return expected


def pypi_hashes(payload: Mapping[str, object]) -> dict[str, str]:
    """Extract the exact filename-to-SHA mapping from a PyPI JSON response."""

    urls = payload.get("urls")
    if not isinstance(urls, list):
        raise TypeError("PyPI response has no urls list")
    observed: dict[str, str] = {}
    for item in urls:
        if not isinstance(item, dict):
            raise TypeError("PyPI response contains a non-object URL entry")
        filename = item.get("filename")
        digests = item.get("digests")
        digest = digests.get("sha256") if isinstance(digests, dict) else None
        if not isinstance(filename, str) or not isinstance(digest, str):
            raise TypeError("PyPI URL entry has no filename/SHA-256")
        if filename in observed:
            raise ValueError(f"duplicate PyPI filename: {filename}")
        observed[filename] = digest
    return observed


def verify_pypi(
    expected: Mapping[str, str],
    *,
    attempts: int = 12,
    retry_seconds: float = 5,
) -> None:
    """Wait for PyPI propagation and require exact published digests."""

    observed: dict[str, str] = {}
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(PYPI_URL, timeout=20) as response:
                payload = json.load(response)
            if not isinstance(payload, dict):
                raise TypeError("PyPI response is not an object")
            observed = pypi_hashes(payload)
            last_error = None
        except (HTTPError, URLError, TimeoutError, TypeError, ValueError) as exc:
            last_error = exc
        else:
            if observed == dict(expected):
                return
        if attempt + 1 < attempts:
            time.sleep(retry_seconds)
    if last_error is not None:
        raise RuntimeError(f"PyPI hash lookup failed: {last_error}") from last_error
    raise RuntimeError(
        f"PyPI hashes differ: expected={dict(expected)!r}, observed={observed!r}"
    )


def download_github_assets(tag: str, asset_dir: Path) -> None:
    """Download only the two distributions and their manifest."""

    asset_dir.mkdir(parents=True, exist_ok=True)
    if any(asset_dir.iterdir()):
        raise ValueError(f"GitHub asset directory must start empty: {asset_dir}")
    subprocess.run(
        [
            "gh",
            "release",
            "download",
            tag,
            "--dir",
            str(asset_dir),
            "--pattern",
            "*.whl",
            "--pattern",
            "*.tar.gz",
            "--pattern",
            "SHA256SUMS",
        ],
        check=True,
    )


def verify_github_release_state(tag: str) -> None:
    """Require the exact tag to be a published, non-prerelease GitHub release."""

    result = subprocess.run(
        [
            "gh",
            "release",
            "view",
            tag,
            "--json",
            "tagName,isDraft,isPrerelease",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    observed = json.loads(result.stdout)
    expected = {
        "tagName": tag,
        "isDraft": False,
        "isPrerelease": False,
    }
    if observed != expected:
        raise RuntimeError(
            f"GitHub release state differs: expected={expected!r}, "
            f"observed={observed!r}"
        )


def verify_github_assets(
    expected: Mapping[str, str],
    *,
    manifest: Path,
    asset_dir: Path,
) -> None:
    """Require the downloaded manifest and files to match the local build."""

    downloaded_manifest = asset_dir / "SHA256SUMS"
    if downloaded_manifest.read_bytes() != manifest.read_bytes():
        raise RuntimeError("GitHub SHA256SUMS differs from the build manifest")
    expected_names = set(expected) | {"SHA256SUMS"}
    observed_names = {path.name for path in asset_dir.iterdir() if path.is_file()}
    if observed_names != expected_names:
        raise RuntimeError(
            "GitHub release asset set differs: "
            f"expected={sorted(expected_names)!r}, "
            f"observed={sorted(observed_names)!r}"
        )
    for filename, digest in expected.items():
        observed = hashlib.sha256((asset_dir / filename).read_bytes()).hexdigest()
        if observed != digest:
            raise RuntimeError(
                f"GitHub hash differs for {filename}: "
                f"expected={digest}, observed={observed}"
            )


def verify_github_release(
    expected: Mapping[str, str],
    *,
    manifest: Path,
    asset_dir: Path,
    tag: str,
    attempts: int = 6,
    retry_seconds: float = 5,
) -> None:
    """Retry transient GitHub readback without reusing partial downloads."""

    if asset_dir.exists():
        raise ValueError(f"GitHub asset target must not exist: {asset_dir}")
    asset_dir.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(attempts):
        attempt_dir = Path(
            tempfile.mkdtemp(
                prefix=f".{asset_dir.name}-attempt-",
                dir=asset_dir.parent,
            )
        )
        try:
            verify_github_release_state(tag)
            download_github_assets(tag, attempt_dir)
            verify_github_assets(
                expected,
                manifest=manifest,
                asset_dir=attempt_dir,
            )
        except (
            OSError,
            RuntimeError,
            ValueError,
            subprocess.CalledProcessError,
        ) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(retry_seconds)
        else:
            attempt_dir.replace(asset_dir)
            return
    raise RuntimeError(f"GitHub release hash lookup failed: {last_error}") from last_error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--asset-dir", required=True, type=Path)
    parser.add_argument("--tag", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    expected = read_manifest(args.manifest)
    verify_pypi(expected)
    verify_github_release(
        expected,
        manifest=args.manifest,
        asset_dir=args.asset_dir,
        tag=args.tag,
    )
    print(f"[OK] PyPI and GitHub hashes: {expected!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
