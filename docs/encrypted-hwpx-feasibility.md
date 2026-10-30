# 암호화 HWPX 타당성 조사

확인: 2026-10-30. 이 문서는 #53의 **1단계 조사** 결과다. 암복호화 지원을 추가하거나 현재 지원표를 바꾸지 않는다.

## 판정

한/글을 실행하지 않는 Python API로 구현할 기술적 가능성은 있다. 다만 표준 라이브러리만으로 안전하게 완성하는 경로는 권하지 않는다. SHA-256·PBKDF2·ZIP·deflate는 Python 표준 라이브러리에 있지만 AES는 없다. 검증된 선택 의존성의 암호 구현을 쓰는 것이 현실적이다. Python으로 직접 AES를 새로 구현하거나, 검증되지 않은 순수 Python 암호 코드를 가져오는 것은 조사 결론이 아니다.

이 판정은 알고리즘과 패키지 구조에 근거한 **구현 가능성 추론**이다. 실제 한컴 암호 문서의 복호화·재암호화·재개봉 성공은 아직 검증하지 않았다. 현재 API는 암호 문서를 감지하고 해제 후 재저장을 안내하며, content 파싱을 거부한다.

## 관찰된 HWPX 구조

기존 [#104](https://github.com/airmang/python-hwpx/pull/104)의 한컴오피스 한글 13.0.0.711 관찰을 보존한 [회귀 시험](../tests/test_error_messages.py)은 다음 선언을 기록한다.

| 위치/항목 | 관찰 |
|---|---|
| 컨테이너 | ZIP 안의 `META-INF/manifest.xml`, ODF manifest namespace |
| 파트별 선언 | `file-entry/encryption-data`, 원래 크기·알고리즘·IV·salt·반복 횟수 |
| cipher | AES-256-CBC |
| key derivation | PBKDF2, 1024회, 파생 키 32바이트 |
| start key | SHA-256, 32바이트 |
| checksum | `sha256-1k` |
| 암호문 | header/section/settings/PrvText 등 파트의 내용 |

시험 입력은 선언 모양을 재현한 합성 잡음이다. 실제 암호문 복호화용 known-answer 벡터가 아니다. 모든 한컴 버전·암호 옵션이 같은 파라미터를 쓴다고 일반화하지 않는다. 현재 감지 구현은 [package.py](../src/hwpx/opc/package.py)의 `_declared_encrypted_parts`다.

## 표준과 구현 구성

[ODF 1.3 Packages §3.4, §4.4–4.7, §4.16](https://docs.oasis-open.org/office/OpenDocument/v1.3/OpenDocument-v1.3-part2-packages.html)은 manifest에 파트별 암호 매개변수를 기록한다. 파트는 deflate 후 암호화하고 ZIP에는 STORED로 담는다. `PBKDF2` 이름의 PRF는 HMAC-SHA-1이며, start-key의 SHA-256과 구분해야 한다. `sha256-1k`는 압축된 평문 앞 1024바이트에 적용한다. SHA-256이라는 이름만 보고 PBKDF2 PRF를 SHA-256으로 바꾸면 다른 키가 된다.

[Python hashlib](https://docs.python.org/3/library/hashlib.html#hashlib.pbkdf2_hmac)는 필요한 해시와 PBKDF2를 제공한다. [cryptography Cipher 문서](https://cryptography.io/en/latest/hazmat/primitives/symmetric-encryption/)는 AES-CBC 원시 연산을 제공하지만 자동 패딩이나 패키지 처리를 제공하지 않는다. 이 구성요소의 존재는 한컴 호환성을 증명하지 않는다.

향후 구현에서 확인할 계약은 UTF-8 비밀번호·정규화, start-key 구성, 파트별 salt/IV, XML Encryption CBC 패딩, raw-deflate framing과 최종 크기다. 일반 PKCS7 패딩을 근거 없이 적용하지 않는다. CBC/앞부분 checksum을 전체 내용의 인증 보장으로 표시하지 않는다.

## 구현 착수 전 필요한 검증

1. 개인정보 없는 실제 한컴 저장 문서와 알려진 비밀번호, 대응 평문을 확보한다. ASCII·한글·빈 암호/잘못된 암호, 여러 파트·바이너리를 분리한다.
2. manifest에서 알고리즘·키 길이·반복 횟수·크기를 읽고 미지원 조합을 명시적으로 거부한다. 반복 횟수·압축 해제량·파트 수를 제한하고 중복/경로 탈출 파트를 거부한다.
3. 알려진 벡터로 키·패딩·checksum·압축 단계를 독립 검증한다. 오류에서 평문이나 비밀번호를 기록하지 않고 원본/기존 출력을 보존한다.
4. 복호화 후 XML/패키지 검증과 byte-preservation을 확인한다. 다시 암호화한 파일을 실제 한컴에서 열고 수정·저장한 뒤 재개봉한다.
5. 선택 의존성, 공개 API·typed error·원자적 저장·비밀번호 수명 계약을 별도 명세로 확정한다. 오류 메시지 개선을 암호 지원으로 승격하지 않는다.

최초 이슈의 조사 목표는 이 판정과 구현 전 검증 경계로 완료된다. 실제 암복호화 기능과 공개 일정은 별도 구현 범위다.

