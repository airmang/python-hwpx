# License Alignment Audit

Date: 2026-03-10

## Files inspected

- `LICENSE`
- `README.md`
- `pyproject.toml`
- `docs/conf.py`
- `CONTRIBUTING.md`
- `.github/workflows/release.yml`
- `.github/workflows/tests.yml`
- `scripts/build-and-publish.sh`
- `tests/test_packaging_py_typed.py`
- Repo-wide searches across `docs/`, `.github/`, `DevDoc/`, `CHANGELOG.md`, and the repository root for license-related metadata and MIT references

## Contradictions found before this change

- `LICENSE` defined a custom non-commercial license and named `python-hwpx Maintainers` as the copyright holder.
- `README.md` showed an MIT badge and an MIT license section, which contradicted the actual license text.
- `README.md` attributed the license line to `고규현 (Kyuhyun Koh)`, while the `LICENSE` file and package metadata used `python-hwpx Maintainers`.
- `pyproject.toml` used the legacy `license = { file = "LICENSE" }` form and also published the classifier `License :: OSI Approved :: MIT License`, which falsely represented the distribution as MIT-licensed.

## Source of truth

- The repository root `LICENSE` file is the source of truth for license terms.
- This audit treats the project as remaining under its existing custom non-commercial license. No evidence of an intentional relicensing to MIT was found elsewhere in the repository.

## Decision summary

- Preserve the current non-commercial custom license.
- Align public-facing metadata and README wording to that license.
- Use modern packaging metadata that points built distributions back to the root `LICENSE` file without inventing an OSI identifier.
- Remove conflicting MIT wording and the MIT trove classifier rather than replacing it with another potentially ambiguous license classifier.

## Notes on surfaces inspected

- `docs/conf.py` already used `python-hwpx Maintainers` and did not restate MIT licensing.
- No GitHub Pages or docs markdown pages were found to restate the project license.
- The release workflow already builds distributions and runs `twine check`, so it was left in place and used for verification after the metadata update.
