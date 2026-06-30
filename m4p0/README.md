# M4 P0 — 한컴 redline 수용성 측정 (x64 Windows + 한컴 COM)

Mac 한컴은 변경추적을 **표시**만 하고 수락/거부 UI가 없어, 그 측정은 풀빌드(Windows 한컴 + COM)가 필요합니다.
이 폴더를 x64 Windows에서 받아 스크립트 한 줄만 실행하면 됩니다.

## 측정 대상
- **#1 표시**: 한컴이 합성 변경추적을 인식하는가 (`IsTrackChange`) — Mac에서 이미 통과(빨강 삽입/취소선 삭제 렌더).
- **#2 수락/거부**: accept-all → 마크 사라지고 삽입텍스트 남고 삭제텍스트 제거 / reject-all → 그 반대.
- **#3 accept 후 clean**: 수락 결과 .hwpx 재오픈 정상.
- **#4 코멘트 생존**: 메모 2개가 재직렬화·수락 후에도 보존.

## 실행
```powershell
# 한컴 2024가 설치된 x64 Windows에서, 이 폴더(m4p0)로 이동 후:
powershell -ExecutionPolicy Bypass -File .\p0_com_check.ps1
```
- 한컴 창이 잠깐 떴다 닫힙니다(자동). 1~2분 소요.
- 결과: `p0_com_receipt.json` (콘솔에도 출력) + `com_out\*.hwpx` 산출물.

## 결과 전달 (둘 중 아무거나)
1. `p0_com_receipt.json` 내용을 **붙여넣기** — 핵심 영수증.
2. (선택) `git add m4p0/com_out p0_com_receipt.json && git commit -m "m4 p0 com receipts" && git push` —
   산출 .hwpx까지 보내주면 Mac에서 마크 구조까지 정밀 검증.

## 스크립트가 하는 일
- 정확한 accept/reject 액션 ID를 모를 수 있어, **후보 ID를 sweep**하고 각각 저장본 XML을 읽어
  기대대로 바뀐 것(마크 제거·텍스트 보존/제거)을 **스스로 검증**합니다. 어떤 ID가 동작했는지 영수증에 남습니다.
- 어떤 후보도 안 먹으면 그것도 결과(=COM accept 미노출 → 수락/거부는 GUI 수동 측정으로 fallback).

## 파일
- `redline_synth.hwpx` — 삽입 1 + 삭제 1 (미수정부 byte-identical 보존).
- `redline_with_comments.hwpx` — 위 + 메모 2개(작성자 "AI Agent", 일자).
- `p0_com_check.ps1` — 측정 스크립트.
