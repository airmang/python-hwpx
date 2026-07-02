# m7_toc_gold — 한컴 네이티브 차례/상호참조 gold fixtures

Owner-authored in real Hancom (2026-07-02) for M7/S-062 P0 reverse-engineering.

- `hancom-native-toc-A.hwpx` — 4 outline headings + native 제목차례
  (TABLEOFCONTENTS field, entries fresh: pages 1,2,2,3) + 1 CROSSREF
  (page-of 개요 두 번째, cached 2).
- `hancom-native-toc-B.hwpx` — same doc after growing the first body paragraph
  (no 차례 새로 고침): CROSSREF auto-recomputed to 3, TOC entries stale (still 2)
  — the ground truth for stale-TOC detection.

Contract: specs/009-native-toc-xrefs/evidence/p0-native-toc-xml-contract.md.
