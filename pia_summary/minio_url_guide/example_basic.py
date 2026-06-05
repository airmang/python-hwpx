"""
참고용 예제 — pia_summary vLLM 서버에 MinIO presigned URL 을 image_url 로 보내는
가장 단순한 형태. base64 모드와 응답이 동일한지 단발 비교.

용도: 자기 환경 도입 시 "내 vLLM ↔ MinIO 도달성 + presigned URL 서명" 이 정상인지
1차로 확인하는 sanity 도구. 실제 백엔드 코드는 본 예제를 참고하여 자기 환경 변수
/ 클라이언트 / 에러 처리에 맞게 커스텀하면 됨.

전제:
  - vLLM 서버가 호스트 :8000 으로 떠 있음
  - MinIO 가 호스트 :9100 에 떠 있고, vLLM 컨테이너에서 도달 가능한 상태
    (자세한 도달성 구성은 TUTORIAL.md §2 참고)

본 예제는 pia_summary 패키지 코드를 수정하지 않음. prompts.build_chat_payload 가
만든 dict 의 image_url.url 만 런타임에 교체하는 비파괴 패턴.
"""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

import boto3
from botocore.client import Config
import httpx

# pia_summary 임포트 경로 — 본 파일이 packages/pia_summary/minio_url_guide/ 아래라는 전제
PIA_SUMMARY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIA_SUMMARY))
sys.path.insert(0, str(PIA_SUMMARY / "tests"))

from prompts import build_chat_payload  # noqa: E402
from _common import load_or_make_sample_b64, dummy_metadata  # noqa: E402

# =============================================================================
# 사용자 환경에 맞춰 수정 — 본 스크립트 실행 전 자기 환경 값으로 갈아끼우기
# =============================================================================

# vLLM summary 서버 endpoint (본 스크립트가 도는 호스트 시점)
VLLM_URL = "http://localhost:8000/v1/chat/completions"
MODEL    = "Qwen/Qwen3.5-0.8B"

# MinIO 업로드 endpoint — 본 스크립트가 도는 호스트에서 보이는 주소
MINIO_HOST_ENDPOINT      = "http://localhost:9100"

# MinIO 서명 endpoint — vLLM 컨테이너에서 보이는 주소 (presigned URL 의 host 가 됨)
#   같은 docker network 면 컨테이너 이름, 다른 노드면 IP / 도메인
MINIO_CONTAINER_ENDPOINT = "http://pe-vle-test-minio:9000"

# MinIO 자격증명
MINIO_AK = "minioadmin"
MINIO_SK = "minioadmin"

# Bucket / 만료
BUCKET         = "pia-summary-example"
PRESIGN_EXPIRE = 600  # 초

# =============================================================================
# 보통 손 댈 필요 없음
# =============================================================================
KEY = f"sample-{uuid.uuid4().hex[:8]}.jpg"


def make_minio_clients():
    """업로드용(호스트 endpoint), presign 서명용(컨테이너 endpoint) 두 개 생성."""
    common = dict(
        aws_access_key_id=MINIO_AK,
        aws_secret_access_key=MINIO_SK,
        region_name="us-east-1",
        config=Config(signature_version="s3v4"),
    )
    upload = boto3.client("s3", endpoint_url=MINIO_HOST_ENDPOINT, **common)
    presign = boto3.client("s3", endpoint_url=MINIO_CONTAINER_ENDPOINT, **common)
    return upload, presign


def ensure_bucket(s3, bucket: str) -> None:
    try:
        s3.head_bucket(Bucket=bucket)
    except Exception:
        s3.create_bucket(Bucket=bucket)


def call_vllm(payload: dict, timeout: float = 120.0) -> tuple[int, float, str]:
    started = time.monotonic()
    r = httpx.post(VLLM_URL, json=payload, timeout=timeout)
    elapsed = time.monotonic() - started
    if r.status_code != 200:
        return r.status_code, elapsed, r.text[:500]
    return r.status_code, elapsed, r.json()["choices"][0]["message"]["content"].strip()


def main() -> int:
    # 1) 샘플 + payload (base64)
    print("[1] 샘플 준비 + base64 payload 생성")
    b64 = load_or_make_sample_b64()
    metadata = dummy_metadata()
    payload_b64 = build_chat_payload(
        thumbnail_b64=b64,
        event_metadata=metadata,
        model=MODEL,
        max_tokens=96,
    )

    # 2) MinIO 업로드 + presigned URL
    print("[2] MinIO 업로드 + presigned URL 생성")
    upload_s3, presign_s3 = make_minio_clients()
    ensure_bucket(upload_s3, BUCKET)
    sample_path = PIA_SUMMARY / "tests" / "sample.jpg"
    upload_s3.upload_file(str(sample_path), BUCKET, KEY,
                          ExtraArgs={"ContentType": "image/jpeg"})
    presigned_url = presign_s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": KEY},
        ExpiresIn=PRESIGN_EXPIRE,
    )
    print(f"    bucket={BUCKET} key={KEY}")
    print(f"    presigned (host part) = {presigned_url.split('?')[0]}")

    # 3) URL payload — base64 payload 의 image_url.url 만 교체 (비파괴)
    print("[3] URL payload 구성 (image_url.url 만 교체)")
    payload_url = {
        **payload_b64,
        "messages": [
            {
                **payload_b64["messages"][0],
                "content": [
                    {"type": "image_url", "image_url": {"url": presigned_url}},
                    payload_b64["messages"][0]["content"][1],  # text 그대로
                ],
            }
        ],
    }

    # 4) 호출 두 번
    print("[4-A] base64 호출")
    s1, t1, r1 = call_vllm(payload_b64)
    print(f"    status={s1} elapsed={t1:.2f}s")
    print(f"    summary={r1!r}")

    print("[4-B] URL 호출")
    s2, t2, r2 = call_vllm(payload_url)
    print(f"    status={s2} elapsed={t2:.2f}s")
    print(f"    summary={r2!r}")

    # 5) 결과 비교
    print()
    print("=" * 60)
    print("RESULT")
    print("=" * 60)
    ok_b64 = (s1 == 200)
    ok_url = (s2 == 200)
    print(f"  base64 status : {s1} ({'OK' if ok_b64 else 'FAIL'})")
    print(f"  url    status : {s2} ({'OK' if ok_url else 'FAIL'})")
    if ok_b64 and ok_url:
        same = (r1 == r2)
        delta = t2 - t1
        print(f"  same text     : {same}")
        print(f"  latency b64   : {t1:.2f}s")
        print(f"  latency url   : {t2:.2f}s  (delta {delta:+.2f}s)")
    return 0 if (ok_b64 and ok_url) else 3


if __name__ == "__main__":
    sys.exit(main())
