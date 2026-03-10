# License Metadata Policy

## Source of truth

- The root `LICENSE` file defines the project's license terms.
- Metadata changes must reflect the current `LICENSE` text. Do not treat README text, badges, or historical PyPI metadata as authoritative.

## Packaging rule

- `pyproject.toml` must represent the current custom license with `project.license = "LicenseRef-python-hwpx-NonCommercial"`.
- `pyproject.toml` must list `project.license-files = ["LICENSE"]` so both `sdist` and `wheel` carry the license file.
- Keep the build backend compatible with that metadata format by requiring `setuptools>=77.0.0`.

## Classifier rule

- Do not add `License ::` trove classifiers for this project unless the `LICENSE` file changes to a classifier-backed license and the classifier is verified to be accurate.
- For the current custom non-commercial license, leaving license classifiers unset is less ambiguous than picking an approximate classifier.

## README rule

- The README badge and license section must describe the project as using a custom non-commercial license and link to `LICENSE`.
- If contact information is updated, keep it distinct from the copyright/licensing line unless the `LICENSE` file is updated too.

## Verification rule

- Before release or after touching license metadata, run `python -m build` and `twine check dist/*`.
- Inspect built `PKG-INFO` and wheel `METADATA` for `License-Expression: LicenseRef-python-hwpx-NonCommercial` and `License-File: LICENSE`.
- Confirm the wheel contains `.dist-info/licenses/LICENSE` and the sdist contains the root `LICENSE` file.
