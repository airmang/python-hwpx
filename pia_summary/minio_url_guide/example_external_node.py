"""
참고용 예제 — vLLM 과 MinIO 가 서로 다른 docker network / 다른 노드 / 다른 클러스터인
경우의 시나리오. example_basic.py 가 같은 network 만 다룸과 대비.

배경:
  - 운영 환경에서는 vLLM Pod 와 MinIO 가 다른 노드/클러스터/사내 IDC 인 경우가 흔함
  - 이때 presigned URL 의 host 가 vLLM 시점에서 도달 가능해야 동작
  - 본 예제는 그 도달성 원칙을 단일 호스트에서 시뮬레이션하여 확인

═══════════════════════════════════════════════════════════════════════
실행 전 사용자 사전 작업 (필수)
═══════════════════════════════════════════════════════════════════════

본 예제는 MinIO 가 vLLM 의 docker network 에서 분리된 상태를 전제로 함.
사전 작업 없이 그대로 실행하면 case A (도달 불가 host) 도 도달 가능해서 200 을
받게 되므로 VERDICT 가 의도와 달리 잘못 출력됨.

  # MinIO 를 vLLM network 에서 disconnect (사전)
  docker network disconnect <vllm-network> <minio-container>
  # 본 환경 예: docker network disconnect pia_summary_default pe-vle-test-minio

  # 본 스크립트 실행
  python3 example_external_node.py

  # 검증 후 원복
  docker network connect <vllm-network> <minio-container>

═══════════════════════════════════════════════════════════════════════

본 스크립트가 하는 일 (사전 작업 후):
  1) presigned URL 의 host 를 도달 불가 값으로 서명 → vLLM 호출 → 실패 기대
  2) host 를 호스트 게이트웨이 IP 로 서명 → vLLM 호출 → 성공 기대
  3) 두 결과 비교로 "presigned URL host = vLLM 시점 도달 가능" 원칙 검증

용도: 자기 환경이 multi-node 일 때 본 패턴을 참고하여 자기 endpoint (사내 도메인,
VPC, K8s Service DNS 등) 에 맞춰 확장. TUTORIAL.md §2.4 의 docker-compose.override.yml
예시와 짝을 이룸.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import boto3
import httpx
from botocore.client import Config

PIA_SUMMARY = Path(__file__).resolve().parent.parent  # packages/pia_summary/
sys.path.insert(0, str(PIA_SUMMARY))
sys.path.insert(0, str(PIA_SUMMARY / "tests"))

from prompts import build_chat_payload  # noqa: E402
from _common import load_or_make_sample_b64, dummy_metadata  # noqa: E402

# =============================================================================
# 사용자 환경에 맞춰 수정 — 본 스크립트 실행 전 자기 환경 값으로 갈아끼우기
# =============================================================================

# vLLM summary 서버 endpoint (호스트 시점)
VLLM_URL = "http://localhost:8000/v1/chat/completions"
MODEL    = "Qwen/Qwen3.5-0.8B"

# MinIO 업로드 endpoint — 본 스크립트가 도는 호스트에서 보이는 주소
MINIO_HOST_ENDPOINT       = "http://localhost:9100"

# vLLM 컨테이너 시점에서 도달 가능한 endpoint — 외부 노드 시뮬레이션 시 호스트
# 게이트웨이 IP 를 사용. 본 예제 환경에서는 172.19.0.1.
#
# 자기 환경의 IP 알아내는 법 — 둘 중 편한 것:
#   1) 호스트에서:
#        docker network inspect <vllm-network> \
#            --format '{{(index .IPAM.Config 0).Gateway}}'
#   2) vLLM 컨테이너 안에서 (ip 명령 없을 때):
#        docker exec <vllm-container> sh -c \
#            "awk '\$2==\"00000000\"{print \$3}' /proc/net/route"
#        → hex 4바이트(예: 010013AC) 가 나옴. 뒤에서 2자씩 거꾸로 읽고 10진 변환:
#          AC=172, 13=19, 00=0, 01=1 → 172.19.0.1
MINIO_FROM_VLLM_ENDPOINT  = "http://172.19.0.1:9100"

# 도달 불가 host (비교 검증용 — 자기 환경의 vLLM 시점 도달 불가 alias 면 됨)
MINIO_UNREACHABLE_ENDPOINT = "http://pe-vle-test-minio:9000"

# MinIO 자격증명
MINIO_AK = "minioadmin"
MINIO_SK = "minioadmin"

# Bucket / Key / 만료
BUCKET         = "pia-summary-example"
KEY            = "external-node-test.jpg"
PRESIGN_EXPIRE = 600


def main() -> int:
    print("=" * 70)
    print("외부 노드 시뮬레이션 — vLLM 과 MinIO 가 서로 다른 docker network")
    print("=" * 70)
    print("[사전 안내] 실행 전 MinIO 를 vLLM network 에서 disconnect 했는지 확인.")
    print("           안 했으면 case A 도 200 받게 되어 VERDICT 가 잘못 출력됨.")
    print("           자세한 사전/원복 명령은 본 파일 docstring 참고.")
    print()

    # 1) sample 준비
    print("\n[1] 샘플 + payload 준비")
    b64 = load_or_make_sample_b64()

    # 2) MinIO 업로드 (호스트 endpoint)
    print("[2] MinIO 업로드 (호스트 endpoint=localhost:9100)")
    upload_s3 = boto3.client(
        "s3",
        endpoint_url=MINIO_HOST_ENDPOINT,
        aws_access_key_id=MINIO_AK,
        aws_secret_access_key=MINIO_SK,
        region_name="us-east-1",
        config=Config(signature_version="s3v4"),
    )
    try:
        upload_s3.head_bucket(Bucket=BUCKET)
    except Exception:
        upload_s3.create_bucket(Bucket=BUCKET)
    sample_path = PIA_SUMMARY / "tests" / "sample.jpg"
    upload_s3.upload_file(str(sample_path), BUCKET, KEY,
                          ExtraArgs={"ContentType": "image/jpeg"})

    # 3) presigned URL 두 종 (host 부분만 다른) 생성
    print("[3] presigned URL 두 종 생성")
    presign_internal = boto3.client(
        "s3",
        endpoint_url=MINIO_UNREACHABLE_ENDPOINT,  # 분리되어 도달 불가
        aws_access_key_id=MINIO_AK,
        aws_secret_access_key=MINIO_SK,
        region_name="us-east-1",
        config=Config(signature_version="s3v4"),
    )
    presign_hostgw = boto3.client(
        "s3",
        endpoint_url=MINIO_FROM_VLLM_ENDPOINT,  # 호스트 게이트웨이 — 도달 가능
        aws_access_key_id=MINIO_AK,
        aws_secret_access_key=MINIO_SK,
        region_name="us-east-1",
        config=Config(signature_version="s3v4"),
    )
    url_internal = presign_internal.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": KEY},
        ExpiresIn=PRESIGN_EXPIRE,
    )
    url_hostgw = presign_hostgw.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": KEY},
        ExpiresIn=PRESIGN_EXPIRE,
    )
    print(f"  case A (잘못된 host, vLLM 에서 도달 불가): {url_internal.split('?')[0]}")
    print(f"  case B (호스트 게이트웨이, vLLM 도달 가능): {url_hostgw.split('?')[0]}")

    # 4) base 페이로드 준비 (b64 자리는 임시 채움 후 url 교체)
    base = build_chat_payload(
        thumbnail_b64=b64,
        event_metadata=dummy_metadata(),
        model=MODEL,
        max_tokens=96,
    )

    def call(url: str, label: str) -> tuple[int, float, str]:
        payload = json.loads(json.dumps(base))
        payload["messages"][0]["content"][0]["image_url"]["url"] = url
        t0 = time.monotonic()
        try:
            r = httpx.post(VLLM_URL, json=payload, timeout=60.0)
            elapsed = time.monotonic() - t0
            if r.status_code == 200:
                return r.status_code, elapsed, r.json()["choices"][0]["message"]["content"].strip()
            return r.status_code, elapsed, r.text[:200]
        except Exception as exc:
            return -1, time.monotonic() - t0, f"EXC: {exc}"

    # 5) 호출 비교
    print("\n[4-A] 잘못된 host 로 호출 — vLLM 이 도달 못해야 정상 (4xx/5xx 기대)")
    sA, tA, rA = call(url_internal, "internal-bad")
    print(f"    status={sA}  elapsed={tA:.2f}s")
    print(f"    body/text  ={rA[:160]}")

    print("\n[4-B] 호스트 게이트웨이 host 로 호출 — 도달 가능해야 정상 (200 기대)")
    sB, tB, rB = call(url_hostgw, "hostgw-good")
    print(f"    status={sB}  elapsed={tB:.2f}s")
    print(f"    body/text  ={rB}")

    # 6) verdict
    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    bad_failed = sA != 200
    good_ok = sB == 200
    print(f"  case A (도달 불가 host) failed as expected : {bad_failed}  (status={sA})")
    print(f"  case B (도달 가능 host) succeeded          : {good_ok}  (status={sB})")
    if bad_failed and good_ok:
        print("  -> 외부 노드 시나리오에서 핵심 원칙 검증 완료.")
        print("     'presigned URL 의 host 가 vLLM 시점 도달 가능' 만족 시 동작.")
    return 0 if (bad_failed and good_ok) else 3


if __name__ == "__main__":
    sys.exit(main())
