# SPDX-License-Identifier: Apache-2.0
"""Roundtrip fidelity diagnostics for the hwpxlib corpus.

Task 1 SPIKE observations:
- `reader_writer__SimpleTable.hwpx`, `reader_writer__SimpleEquation.hwpx`,
  and `reader_writer__SimplePicture.hwpx` all reopen after `open -> to_bytes`
  and preserve identical local-name element counts.
- A corpus-wide probe of 47 samples found no reopen failures and no local-name
  losses. This locks the diagnostic meaning: namespace prefix spelling, ID
  renumbering, and element order changes are outside this loss metric; only a
  before-count greater than the after-count for the same element local-name is
  reported as structural loss.
"""
