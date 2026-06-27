# M3 document-authoring — 공문 gold corpus (vendored real-world HWPX)

These `.hwpx` files are **sample data vendored for testing** under the project's
clean-room policy (Constitution VIII: "Sample data may be vendored with NOTICE
attribution; ideas may be absorbed. Oracles and references are consulted, not
cloned."). No source **code** is copied — only **publicly disclosed** Korean
government / public-institution documents are vendored as authoring oracle /
regression references for M3 (S-057). Each remains under its upstream terms; see
the source page. If any rights holder objects, the file will be removed.

All files are valid ZIP HWPX (PK magic), open in python-hwpx, and **render
opens-clean in real Hancom** (entry bar for a gold member; verdicts in
`specs/004-document-authoring/evidence/p0-web-sources-verdict.json` and
`p0-profile-render-verdicts.json`).

| Local file | Source | Class | Document | sha256 |
|---|---|---|---|---|
| `seoul_sihaengmun.hwpx` | 서울특별시 전략주택공급과 — [정보소통광장 결재문서](https://opengov.seoul.go.kr/sanction/34593549) (2025-10-24) | **시행문 (full spine)** | 소규모주택정비사업 추진실적 제출('25.3분기). 두문(서울특별시·수신 국토교통부장관·경유)→본문→붙임→끝.→결문(발신명의 서울특별시장·시행 전략주택공급과-13666·접수·공개구분) | 27d2cacc5facf6210512d76730eb81072fea812796c1546d8df33264f82d7d1e |
| `mpm_recruitment_notice.hwpx` | 인사혁신처 — [국민참여정책단 모집공고](https://www.mpm.go.kr/mpm/comm/noti/newsNoitice/index.jsp?boardId=bbs_0000000000000020&cntId=1669) | 공고문 | 제6기 국민참여정책단 모집공고문 (발신명의 인사혁신처장) | c5bfd5e6c71c2f01ec53cb3133930f1f95e1e9a3e4f71db4bd77395e7c0235bd |
| `mfds_admin_notice.hwpx` | 식품의약품안전처 — [행정예고](https://www.mfds.go.kr/brd/m_209/view.do?seq=44182) | 고시(안)/공고 | 생산·수입 중단 보고대상 의료기기 일부개정고시(안) 행정예고 (발신명의 식약처장) | ce87713ce4c9eeca4ec297bbae23d970af0f23b810088edb9d1ca1450c1fa772 |

## 핵심: 진짜 시행문 확보 (2026-06-27)

`seoul_sihaengmun.hwpx` 는 **두문(수신·경유)→본문→붙임→끝.→결문(발신명의·시행·시행일자·접수·공개구분)** 척추를 완비한 **진짜 시행문**(외부기관 수신 + 기관장 발신명의)이다. 이로써 M3 v1 공문 hard-gate를 **공고문 수준이 아닌 전체 시행문 작성규정** 수준으로 설계·회귀검증할 수 있다(오너 "시행문 받으면 전체 승격" 결정 충족). 공고문 2건은 발신명의-only 변형(보조 회귀).

## home_notice (가정통신문) 프로파일 출처

`src/hwpx/design/profiles/home_notice/` 는 아래 실제 가정통신문에서 **harvest**(본문 제거 skeleton + 이미지/메타 strip; `skeleton_open_safe=true`)한 것이다. 원본 전체 파일은 **vendoring하지 않음**(본문 제거 스켈레톤만 커밋 — 개인정보 비노출). 출처:

- 강화여자고등학교 — [학생부 기재요령 가정통신문](https://ganghwagirls.icehs.kr/boardCnts/updateCnt.do?action=view&boardID=36106&boardSeq=33108680&m=0302) "2025학년도 학교생활기록부 기재요령 주요사항 안내" (발신 강화여자고등학교장, 2025. 9. 4.). 원본 sha256 `545b9f4a93c797765520334f25ba38a109e2a1054c64e0e8524ec27689e9666d`.
