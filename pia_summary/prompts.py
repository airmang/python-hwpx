"""
report-summary VLM 서버용 프롬프트 빌더.

본 모듈은 외부 의존성을 0으로 유지한다(stdlib `typing`만 사용).
백엔드 팀이 자기 폴링 코드에 그대로 import해서 쓸 수 있도록 의도된
경량 헬퍼 모음이다.

외부에 노출되는 함수는 두 개:

    get_report_prompt(event_metadata, max_words=40) -> str
        썸네일과 함께 VLM에 보낼 텍스트 프롬프트를 만든다.

    build_chat_payload(thumbnail_b64, event_metadata, *, model, ...) -> dict
        vLLM(OpenAI 호환) /v1/chat/completions 엔드포인트에 그대로
        POST 가능한 request body 통째를 만든다.

`event_metadata`는 임의의 dict를 그대로 받는다. 백엔드가 DB 컬럼을
자유롭게 추가/삭제/리네임해도 코드 변경 없이 동작한다. None / 빈 문자열
값은 자동으로 걸러져 프롬프트가 길어지지 않는다.

프롬프트 자체는 PROMPT_TEMPLATE 문자열에 정의되어 있다. 출력 톤/형식/
길이/언어를 바꾸고 싶으면 이 상수만 수정하면 된다.
"""

from typing import Any

# ---------------------------------------------------------------------------
# 프롬프트 템플릿
# ---------------------------------------------------------------------------
# VLM에 전달할 지시문 본문.
# 두 자리표시자(<<METADATA_BLOCK>>, <<MAX_WORDS>>)를 get_report_prompt가
# 런타임에 치환한다. str.format을 쓰지 않는 이유 = 본 템플릿이 JSON 예시를
# 포함하므로 `{`, `}` 와 충돌하기 때문.
#
# 메타데이터 입력 예시 / 응답 예시는 모델에게 입력 형태를 hint하기 위한
# few-shot 보조다. 백엔드가 어떤 키를 보내든 PROMPT는 그대로 동작한다.
PROMPT_TEMPLATE = """\
You are a VLM assistant generating a single-sentence event report for a
CCTV-based AI surveillance system.

For each request you receive:
  (a) one thumbnail image captured at the moment an alarm was raised, and
  (b) an event metadata dict describing that alarm.

The metadata is shaped roughly like the following example, but the keys
present in any given request may differ — the backend may add, remove,
or rename fields depending on what is available in the source DB. Treat
the example below only as a hint; rely on the actual fields provided in
the current request (shown further down).

Example metadata input (illustrative only, do NOT assume these exact
keys are always present). Backend is expected to send English values
for fields that will appear in the output (camera_name, zone_name,
detected_category, event_status, etc.) so the single-sentence summary
stays consistent and quotable:
{
  "report_type": "single_event_detail",
  "event_metadata": {
    "event_id": "EVT-20250201-00037",
    "camera_id": "CAM-03",
    "channel_id": "CH-3",
    "camera_name": "Server Room Entrance",
    "zone_name": "Server Room Corridor",
    "detected_category": "fall_down",
    "event_start_time": "2025-02-01 14:23:11",
    "event_end_time": "2025-02-01 14:23:19",
    "event_duration_sec": 8,
    "event_status": "pending_review"
  }
}

Example response (for the example input above, illustrative only):
At 2025-02-01 14:23, camera "Server Room Entrance" (CAM-03) raised a
fall_down event in the Server Room Corridor zone, with a person on
screen appearing to lie low, warranting operator review.

Metadata for the current request:
<<METADATA_BLOCK>>

Your task: combine what you actually see in the thumbnail with the
metadata above to produce a single-sentence English summary that a
control-room operator can read at a glance.

Rules:
1. Base visual claims ONLY on what is visible in the thumbnail; do not
   invent details that are not in the image.
2. Whenever camera_name (or equivalent location/zone field) is present,
   include it explicitly in the sentence so operators can identify the
   source camera at a glance.
3. You may quote times, IDs, locations, and categories from the metadata
   verbatim; prefer reusing the provided English strings rather than
   paraphrasing.
4. Output a SINGLE plain-text sentence in English. No JSON, no
   markdown, no code blocks, no quotes around the whole sentence, no
   bullets.
5. Keep the sentence under <<MAX_WORDS>> words.
6. Trust the provided detected category if present; do not re-judge it.
7. If a metadata value happens to be in Korean, translate it to natural
   English in the sentence (backend should send English values to begin
   with).
"""


def _format_metadata_block(event_metadata: dict) -> str:
    """이벤트 메타데이터 dict를 프롬프트 본문에 들어갈 bullet list 문자열로 변환.

    동작:
      - 비어있는 dict / None / 빈 문자열 값은 모두 자동 필터링
      - 남은 항목 각각을 ``- key: value`` 한 줄로 펼침
      - 모든 항목이 비어있으면 ``- (no metadata provided)`` 단일 줄 반환

    Args:
        event_metadata: 임의 dict. 키 이름/개수/타입은 자유.

    Returns:
        프롬프트 안에 그대로 삽입될 여러 줄 문자열.

    Examples:
        >>> _format_metadata_block({"event_id": "EVT-001", "zone_name": ""})
        '- event_id: EVT-001'
        >>> _format_metadata_block({})
        '- (no metadata provided)'
    """
    if not event_metadata:
        return "- (no metadata provided)"
    lines = [
        f"- {key}: {value}"
        for key, value in event_metadata.items()
        if value not in (None, "")
    ]
    return "\n".join(lines) if lines else "- (no metadata provided)"


def get_report_prompt(event_metadata: dict, max_words: int = 40) -> str:
    """VLM에 보낼 텍스트 프롬프트를 만들어 반환한다.

    내부적으로 PROMPT_TEMPLATE의 ``<<METADATA_BLOCK>>`` 자리에는
    ``_format_metadata_block(event_metadata)`` 결과를, ``<<MAX_WORDS>>``
    자리에는 ``str(max_words)``를 삽입한다.

    백엔드가 직접 OpenAI SDK로 호출할 때처럼 ``messages`` 구조를 본인이
    조립하고 텍스트 프롬프트만 끼워 넣는 패턴에서 사용한다.

    Args:
        event_metadata:
            DB에서 긁어온 알람 한 건의 메타데이터 dict.
            키/개수/타입 자유. 빈 값(None, "")은 자동 제외.
            예) ``{"event_id": "EVT-001", "camera_name": "전산실 입구",
            "detected_category": "쓰러짐"}``
        max_words:
            응답 한 문장의 단어 상한. 기본 40. 더 짧은 응답을 원하면
            낮추고, 더 자세한 응답을 원하면 올린다. 모델이 강제로 지키는
            값은 아니므로 너무 낮으면 가독성이 떨어질 수 있다.

    Returns:
        VLM에 그대로 보낼 수 있는 멀티라인 텍스트 프롬프트.

    Examples:
        OpenAI SDK 사용 시 ``messages`` 안에 끼워 넣는다::

            from openai import OpenAI
            from prompts import get_report_prompt

            client = OpenAI(base_url="http://localhost:8000/v1",
                            api_key="EMPTY")
            resp = client.chat.completions.create(
                model="Qwen/Qwen3.5-0.8B",
                max_tokens=96,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        {"type": "text",
                         "text": get_report_prompt(metadata)},
                    ],
                }],
            )
    """
    return (
        PROMPT_TEMPLATE
        .replace("<<METADATA_BLOCK>>", _format_metadata_block(event_metadata))
        .replace("<<MAX_WORDS>>", str(max_words))
    )


def build_chat_payload(
    thumbnail_b64: str,
    event_metadata: dict,
    *,
    model: str,
    max_tokens: int = 96,
    temperature: float = 0.0,
    max_words: int = 40,
) -> dict[str, Any]:
    """vLLM /v1/chat/completions 엔드포인트에 그대로 POST할 수 있는 request body를 만든다.

    내부적으로 ``get_report_prompt``를 호출해 텍스트 프롬프트를 만든 뒤,
    base64 썸네일과 합쳐 OpenAI Chat Completions 멀티모달 messages 구조의
    dict를 반환한다. 백엔드가 OpenAI 메시지 스키마를 손으로 짜는 보일러
    플레이트를 줄이기 위해 제공.

    반환되는 dict 구조::

        {
          "model": <model>,
          "messages": [
            {
              "role": "user",
              "content": [
                {"type": "image_url",
                 "image_url": {"url": "data:image/jpeg;base64,<thumbnail_b64>"}},
                {"type": "text", "text": "<get_report_prompt(...) 결과>"},
              ],
            }
          ],
          "max_tokens": <max_tokens>,
          "temperature": <temperature>,
        }

    Args:
        thumbnail_b64:
            JPEG 바이트를 base64로 인코딩한 ASCII 문자열. ``data:image/jpeg;base64,``
            prefix 없이 인코딩된 본문만 전달.
        event_metadata:
            ``get_report_prompt``와 동일. 임의 dict.
        model:
            vLLM이 띄운 모델 이름 (HF path). docker-compose의
            ``VLLM_MODEL`` 값과 일치해야 함. 예) ``"Qwen/Qwen3.5-0.8B"``.
        max_tokens:
            모델이 생성할 최대 토큰 수. 한 문장 응답에는 96 정도면 충분.
            너무 작으면 문장이 잘리고, 너무 크면 응답이 늘어지며 latency↑.
            ``tests/benchmark_max_tokens.py``로 적정값 측정 가능.
        temperature:
            샘플링 온도. 0.0이면 결정적(같은 입력→같은 출력). 본 서비스는
            관제용이라 일관성 우선 → 기본 0.0 권장.
        max_words:
            응답 한 문장의 단어 상한. ``get_report_prompt``의 ``max_words``로
            그대로 전달.

    Returns:
        ``httpx.post(url, json=...)`` 또는 ``json.dumps(...)``에 그대로
        넘길 수 있는 dict.

    Examples:
        직접 httpx로 호출하는 가장 짧은 형태::

            import httpx
            from prompts import build_chat_payload

            body = build_chat_payload(
                thumbnail_b64=row.thumbnail_b64,
                event_metadata=row.metadata_dict(),
                model="Qwen/Qwen3.5-0.8B",
                max_tokens=96,
            )
            r = httpx.post(
                "http://localhost:8000/v1/chat/completions",
                json=body,
                timeout=120,
            )
            r.raise_for_status()
            summary = r.json()["choices"][0]["message"]["content"].strip()

        비동기 버전(``httpx.AsyncClient`` + ``asyncio.gather``)도 동일한
        body를 그대로 사용할 수 있다.
    """
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{thumbnail_b64}"
                        },
                    },
                    {
                        "type": "text",
                        "text": get_report_prompt(event_metadata, max_words=max_words),
                    },
                ],
            }
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
