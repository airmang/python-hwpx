# M2 form-fill-integrity corpus — vendored real-world HWPX documents

These `.hwpx` files are **sample data vendored for testing** under the project's
clean-room policy (Constitution VIII: "Sample data may be vendored with NOTICE
attribution; ideas may be absorbed. Oracles and references are consulted, not
cloned."). No source **code** is copied — only public document files are vendored
as oracle/regression inputs for form-fill-integrity verification (M2).

Downloaded 2026-06-25 from public GitHub repositories. Each remains under its
upstream license; see the source repo. If any rights holder objects, the file
will be removed.

| Local file | Source repo | Upstream path |
|---|---|---|
| `irb_form_blank.hwpx` | [nathankim0/easy-hwp](https://github.com/nathankim0/easy-hwp) | `IRB서식_샘플.hwpx` |
| `irb_form_filled.hwpx` | [nathankim0/easy-hwp](https://github.com/nathankim0/easy-hwp) | `IRB서식_완성.hwpx` |
| `gov_donation_report_form.hwpx` | [edwardkim/rhwp](https://github.com/edwardkim/rhwp) | `samples/2025년 기부·답례품 실적 지자체 보고서_양식.hwpx` |
| `form_002.hwpx` | [edwardkim/rhwp](https://github.com/edwardkim/rhwp) | `rhwp-studio/public/samples/form-002.hwpx` |
| `public_official_table.hwpx` | [reallygood83/master-of-hwp](https://github.com/reallygood83/master-of-hwp) | `samples/public-official/table-vpos-01.hwpx` |

These are **real Korean documents with tables / 누름틀** (not synthetic), used to
verify that filling them leaves the document intact (overflow 0, no 글자겹침,
layout stable) against the Mac Hancom render oracle. The deterministic
방송신청서-style 글자겹침 regression fixture is built separately (controlled, not
vendored).
