# M3 document-authoring — 공문 gold corpus (vendored real-world HWPX)

These `.hwpx` files are **sample data vendored for testing** under the project's
clean-room policy (Constitution VIII: "Sample data may be vendored with NOTICE
attribution; ideas may be absorbed. Oracles and references are consulted, not
cloned."). No source **code** is copied — only public government documents are
vendored as authoring oracle/regression references for M3 (S-057).

Downloaded 2026-06-25 (M2 corpus harvest) from public Korean government sites;
selected for M3 on 2026-06-27 as the **공문성 exemplars** in that corpus. Each
remains under its upstream terms; see the source page. If any rights holder
objects, the file will be removed.

| Local file | Agency | Kind | Upstream document | sha256 (orig) |
|---|---|---|---|---|
| `mpm_recruitment_notice.hwpx` | 인사혁신처 (Ministry of Personnel Management) | public-participation-notice (모집공고문) | 제6기 국민참여정책단 모집공고문 — https://www.mpm.go.kr/mpm/comm/noti/newsNoitice/index.jsp?boardId=bbs_0000000000000020&cntId=1669 | c5bfd5e6c71c2f01ec53cb3133930f1f95e1e9a3e4f71db4bd77395e7c0235bd |
| `mfds_admin_notice.hwpx` | 식품의약품안전처 (MFDS) | administrative-notice (행정예고 고시안) | 생산·수입 중단 보고대상 의료기기 및 보고 방법 일부개정고시(안) 행정예고 — https://www.mfds.go.kr/brd/m_209/view.do?seq=44182 | ce87713ce4c9eeca4ec297bbae23d970af0f23b810088edb9d1ca1450c1fa772 |

## Why these two (triage finding 2026-06-27)

The 24-doc M2 corpus (`python-hwpx/work/public-document-corpus/`, gitignored
scratch) contains **no true 시행문** (outgoing official document with a filled-in
두문[수신·경유] → 본문 → 결문[발신명의·시행일·생산등록번호] spine). These two
**공고문/고시(안)** are the only authored official documents with a genuine
**발신명의 결문** (공고번호 + 날짜 + 기관장 명의) and valid body — not blank forms.
They anchor the M3 v1 공문 hard-gate at **공고문 level** (공고번호·날짜·발신명의·
끝.·순서 = ERROR; 수신/경유/생산등록번호/시행 = WARNING until a real 시행문 is
sourced). Both `open_safety_ok = true`. See
`specs/004-document-authoring/evidence/p0-corpus-triage.md`.
