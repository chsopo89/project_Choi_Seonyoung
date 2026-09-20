import csv
import os
import re
import time
from datetime import datetime

from google import genai
from google.genai import types


# ─────────────────────────────────────────────────────────────
# 환경 변수
# ─────────────────────────────────────────────────────────────

assert os.getenv(
    "GOOGLE_API_KEY"
), "GOOGLE_API_KEY가 설정되지 않았습니다."


MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.6-flash",
)


# ─────────────────────────────────────────────────────────────
# 시스템 프롬프트
#
# 04.ollama_test.py와 동일한 비교 조건
# ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "당신은 네트워크 엔지니어입니다. "
    "질문에 대해 3000자 이내로 답변하세요. "
    "확인할 항목과 점검 순서를 중심으로 서술하세요. "
    "명령어는 해당 장비와 OS에서 실제 존재한다고 확신하는 경우에만 제시하세요. "
    "명령어의 정확한 문법을 확신하지 못하면 명령어를 만들어내지 말고 "
    "'정확한 명령어 확인이 필요합니다'라고 답하세요. "
    "장비 모델이나 OS 버전 정보가 부족하여 답이 달라질 수 있다면 그 사실을 명시하세요."
)


# ─────────────────────────────────────────────────────────────
# Cloud 공통 비교 문항
#
# Local의 q03 / q06 / q07 / q09 / q10과 동일
# ─────────────────────────────────────────────────────────────

QUESTIONS = {
    "q03": (
        "FortiGate에서 로그가 쌓이지 않고 로그 서버로도 전송되지 않는다. "
        "로그 서버는 정상 동작 중이고 설정과 정책에도 문제가 없으며 ping도 정상이다. "
        "로그가 생성되는 단계, FortiGate 내부 저장소 또는 메모리에 기록되는 단계, "
        "외부 로그 서버로 전송을 시도하는 단계, 실제 패킷이 송신되는 단계, "
        "로그 서버가 수신하는 단계를 구분해서 원인을 좁혀라. "
        "문제가 로그 생성, 로컬 저장, 전송, 수신 중 어디에 있는지 확인하는 순서로 설명하라. "
        "명령어를 제시한다면 FortiOS 7.6에서 실제 존재한다고 확신하는 명령어만 사용하라. "
        "원인이 확인되기 전에는 재부팅, 초기화, 로그 삭제 같은 조치를 우선하지 마라."
    ),

    "q06": (
        "Cisco Catalyst 스위치(IOS XE)에 NTP를 정상적으로 설정했는데, "
        "다음 유지보수 때 확인해 보니 시간이 어긋나 있다. "
        "NTP 서버는 정상이고 유독 한 대만 틀어져 있다. "
        "스위치가 실제로 어떤 NTP 서버를 동기화 대상으로 사용하고 있는지, "
        "현재 동기화 상태와 peer 상태, 로컬 시간 관련 설정을 확인하는 순서로 설명하라. "
        "NTP 서버까지의 네트워크 도달성과 NTP 동기화 자체를 구분해서 판단하라. "
        "현재 설정과 상태를 확인하기 전에 NTP 서버 주소를 변경하는 접근이 적절한지도 설명하라. "
        "명령어는 Cisco Catalyst IOS XE에서 실제 존재한다고 확신하는 경우에만 제시하라."
    ),

    "q07": (
        "HA로 구성된 Cisco 스위치와 Juniper 스위치가 서로 연결돼 있다. "
        "Juniper는 HA가 정상적으로 넘어가는데, Cisco는 넘어가지 않고 "
        "Active 스위치만 off 되는 현상이 발생한다. "
        "로그에도 Active 스위치가 꺼졌다는 기록만 남아 있다. "
        "먼저 장애 범위를 Cisco 측과 Juniper 측 중 어디로 좁힐지 설명하고, "
        "Cisco 측 HA 상태와 구성, 두 장비 사이의 물리 링크 및 프로토콜 상태를 "
        "어떤 순서로 확인할지 설명하라. "
        "단순 링크 장애와 HA 전환 실패를 구분해서 판단하라. "
        "설정을 변경하기 전에 어떤 증거를 확보해야 하는지도 설명하라. "
        "Cisco와 Juniper의 명령어를 혼용하지 말고, "
        "각 장비에서 실제 존재한다고 확신하는 명령어만 제시하라."
    ),

    "q09": (
        "Cisco 스위치에 광 SFP 모듈을 연결했으나 인식되지 않는다. "
        "확인 결과 Cisco 정품 모듈이 맞다. "
        "SFP 자체 인식 여부, 포트 상태, 트랜시버 정보와 DOM 정보를 "
        "어떤 순서로 확인할지 설명하라. "
        "SFP 불량, 포트 문제, 장비와 SFP의 호환성 문제를 구분해서 판단하라. "
        "Cisco 정품이라는 사실과 해당 스위치 모델 및 소프트웨어에서 "
        "지원되는 조합이라는 사실이 같은 의미인지도 설명하라. "
        "Cisco 정품 모듈과 서드파티 모듈을 사용할 때 "
        "기술지원 또는 보증 처리에서 확인해야 할 차이도 설명하라. "
        "명령어는 Cisco 장비에서 실제 존재한다고 확신하는 경우에만 제시하라."
    ),

    "q10": (
        "기존 Cisco 스위치에서 Juniper 스위치로 장비를 이전하는 중이다. "
        "전환 기간이라 두 장비가 동시에 물려 있고, "
        "트렁크 구간은 802.1Q로 양쪽 모두 설정했으며 VLAN ID도 동일하게 맞췄다. "
        "링크는 up 되고 LLDP로 서로 인식된다. "
        "그런데 일부 VLAN만 통신이 되지 않고, "
        "포트를 올린 뒤부터 간헐적으로 루프성 트래픽이 관측된다. "
        "각 스위치 내부에서는 단말 간 통신에 문제가 없다. "
        "Cisco와 Juniper 양쪽에서 트렁크의 allowed/member VLAN, "
        "tagging 방식, STP 상태, MAC 학습 상태를 확인하여 "
        "링크/LLDP 정상과 VLAN forwarding 정상을 구분해서 판단하라. "
        "명령어를 제시한다면 Cisco와 Juniper 명령어를 구분하고 "
        "각 장비에서 실제 존재한다고 확신하는 명령어만 사용하라. "
        "현재 설정과 상태를 백업 또는 기록한 뒤, "
        "VLAN 단위로 단계적으로 이전하고 검증하는 순서와 "
        "문제가 발생했을 때의 롤백 기준도 설명하라."
    ),
}


# ─────────────────────────────────────────────────────────────
# 실험 설정
# ─────────────────────────────────────────────────────────────

LABEL = "gemini"

# 과제 기준:
# Cloud 모델은 공통 5문항을 각각 1회
RUNS = 1

# Gemini 3.x에서는 temperature를 요청하지 않는다.
TEMPERATURE = ""

# gemini-3.6-flash는 minimal thinking 지원
THINKING_LEVEL = "minimal"

MAX_OUTPUT_TOKENS = 1536

CSV_PATH = "benchmark_gemini.csv"
RESP_DIR = "responses_gemini"

CHAR_LIMIT = 3000
PREVIEW_LEN = 60


# ─────────────────────────────────────────────────────────────
# CSV 필드
# ─────────────────────────────────────────────────────────────

FIELDS = [
    "세션",
    "순번",
    "날짜",
    "시각",
    "문제",
    "모델",
    "모델ID",
    "회차",
    "상태",
    "종료사유",

    "입력토큰",
    "캐시입력토큰",
    "출력토큰",
    "추론토큰",

    "응답글자수",
    "제약초과",

    "응답초",
    "초당토큰",

    "temperature",
    "thinking_level",
    "max_output_tokens",

    "미리보기",
    "원문경로",
    "오류",
]


SESSION = datetime.now().strftime("%m%d-%H%M")


# ─────────────────────────────────────────────────────────────
# Gemini Client
# ─────────────────────────────────────────────────────────────

client = genai.Client(
    api_key=os.environ["GOOGLE_API_KEY"]
)


# ─────────────────────────────────────────────────────────────
# 응답 저장
# ─────────────────────────────────────────────────────────────

def save_response(qid, label, run, text):
    os.makedirs(
        RESP_DIR,
        exist_ok=True,
    )

    safe = label.replace(
        ":",
        "_",
    )

    path = os.path.join(
        RESP_DIR,
        f"{SESSION}_{qid}_{safe}_run{run}.md",
    )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:
        f.write(text)

    return path.replace(
        "\\",
        "/",
    )


# ─────────────────────────────────────────────────────────────
# 미리보기
# ─────────────────────────────────────────────────────────────

def preview(text, length=PREVIEW_LEN):
    flat = re.sub(
        r"[\s*#`>\-]+",
        " ",
        text,
    ).strip()

    return (
        flat[:length]
        + (
            "…"
            if len(flat) > length
            else ""
        )
    )


# ─────────────────────────────────────────────────────────────
# CSV 기본 행
# ─────────────────────────────────────────────────────────────

def make_row(
    seq,
    now,
    qid,
    run,
    status,
    **extra,
):
    row = {
        "세션": SESSION,
        "순번": seq,

        "날짜": now.strftime(
            "%Y-%m-%d"
        ),

        "시각": now.strftime(
            "%H:%M:%S"
        ),

        "문제": qid,
        "모델": LABEL,
        "모델ID": MODEL,
        "회차": run,
        "상태": status,

        "종료사유": "",

        "입력토큰": "",
        "캐시입력토큰": "",
        "출력토큰": "",
        "추론토큰": "",

        "응답글자수": "",
        "제약초과": "",

        "응답초": "",
        "초당토큰": "",

        # 실제 API에는 전달하지 않는다.
        "temperature": "",

        "thinking_level": THINKING_LEVEL,
        "max_output_tokens": MAX_OUTPUT_TOKENS,

        "미리보기": "",
        "원문경로": "",
        "오류": "",
    }

    row.update(extra)

    return row


# ─────────────────────────────────────────────────────────────
# 최종 답변 텍스트만 추출
#
# 혹시 응답 parts에 thought가 들어오더라도
# 정성평가용 원문에는 포함하지 않는다.
# ─────────────────────────────────────────────────────────────

def get_response_text(response):
    try:
        text = getattr(
            response,
            "text",
            None,
        )

        if text:
            return str(text).strip()

    except Exception:
        pass

    pieces = []

    try:
        candidates = getattr(
            response,
            "candidates",
            None,
        ) or []

        for candidate in candidates:
            content = getattr(
                candidate,
                "content",
                None,
            )

            parts = getattr(
                content,
                "parts",
                None,
            ) or []

            for part in parts:

                # thought summary는 결과 원문에서 제외
                if getattr(
                    part,
                    "thought",
                    False,
                ):
                    continue

                part_text = getattr(
                    part,
                    "text",
                    None,
                )

                if part_text:
                    pieces.append(
                        str(part_text)
                    )

    except Exception:
        pass

    return "\n".join(
        pieces
    ).strip()


# ─────────────────────────────────────────────────────────────
# 토큰 사용량 추출
# ─────────────────────────────────────────────────────────────

def get_usage(response):
    usage = getattr(
        response,
        "usage_metadata",
        None,
    )

    if not usage:
        return "", "", "", ""

    input_tokens = getattr(
        usage,
        "prompt_token_count",
        "",
    )

    cached_tokens = getattr(
        usage,
        "cached_content_token_count",
        "",
    )

    output_tokens = getattr(
        usage,
        "candidates_token_count",
        "",
    )

    reasoning_tokens = getattr(
        usage,
        "thoughts_token_count",
        "",
    )

    if input_tokens is None:
        input_tokens = ""

    if cached_tokens is None:
        cached_tokens = ""

    if output_tokens is None:
        output_tokens = ""

    if reasoning_tokens is None:
        reasoning_tokens = ""

    return (
        input_tokens,
        cached_tokens,
        output_tokens,
        reasoning_tokens,
    )


# ─────────────────────────────────────────────────────────────
# 종료 사유
# ─────────────────────────────────────────────────────────────

def get_finish_reason(response):
    try:
        candidates = getattr(
            response,
            "candidates",
            None,
        ) or []

        if not candidates:
            return ""

        reason = getattr(
            candidates[0],
            "finish_reason",
            None,
        )

        if reason is None:
            return ""

        # enum인 경우 name 사용
        name = getattr(
            reason,
            "name",
            None,
        )

        reason_text = (
            str(name)
            if name
            else str(reason)
        )

        upper = reason_text.upper()

        if "MAX_TOKENS" in upper:
            return "토큰한도"

        if upper in {
            "STOP",
            "FINISH_REASON_STOP",
        }:
            return "정상종료"

        # SDK enum 문자열이 "FinishReason.STOP"인 경우
        if upper.endswith(".STOP"):
            return "정상종료"

        return reason_text

    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────
# CSV append
# ─────────────────────────────────────────────────────────────

def append_csv(rows):
    if not rows:
        return

    is_new = (
        not os.path.exists(
            CSV_PATH
        )
        or os.path.getsize(
            CSV_PATH
        ) == 0
    )

    with open(
        CSV_PATH,
        "a",
        newline="",
        encoding="utf-8-sig",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=FIELDS,
            extrasaction="ignore",
        )

        if is_new:
            writer.writeheader()

        writer.writerows(
            rows
        )


# ─────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────

def main():
    print(
        f"모델: {MODEL} / "
        f"문제 {len(QUESTIONS)}개 x "
        f"{RUNS}회"
    )

    print(
        "생성 설정: "
        "temperature=미설정 / "
        f"thinking_level={THINKING_LEVEL} / "
        f"max_output_tokens={MAX_OUTPUT_TOKENS}"
    )

    print(
        f"CSV: {CSV_PATH}"
    )

    print(
        f"응답: {RESP_DIR}/"
    )

    results = []
    seq = 0

    for qid, question in QUESTIONS.items():

        for run in range(
            1,
            RUNS + 1,
        ):
            seq += 1

            print(
                f"\n{'=' * 60}"
                f"\n[{LABEL}] "
                f"{qid} / run {run}"
                f"\n{'=' * 60}"
            )

            now = datetime.now()

            started = time.perf_counter()

            try:
                response = client.models.generate_content(
                    model=MODEL,
                    contents=question,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,

                        # Gemini 3.x에서는 temperature를
                        # 명시적으로 전달하지 않는다.

                        max_output_tokens=MAX_OUTPUT_TOKENS,

                        thinking_config=types.ThinkingConfig(
                            thinking_level=THINKING_LEVEL,

                            # 사고 요약을 최종 응답에 포함하지 않음
                            include_thoughts=False,
                        ),
                    ),
                )

            except Exception as error:
                elapsed = (
                    time.perf_counter()
                    - started
                )

                error_text = (
                    f"{type(error).__name__}: "
                    f"{error}"
                )

                print(
                    f"실패: {error}"
                )

                results.append(
                    make_row(
                        seq,
                        now,
                        qid,
                        run,
                        "실패",

                        응답초=round(
                            elapsed,
                            2,
                        ),

                        오류=error_text[:1000],
                    )
                )

                # 과제 기준:
                # 실패를 성공 응답으로 자동 대체하지 않음
                continue

            elapsed = (
                time.perf_counter()
                - started
            )

            # ── 최종 답변 ────────────────────────────────

            content = get_response_text(
                response
            )

            chars = len(
                content
            )

            # ── 토큰 ─────────────────────────────────────

            (
                input_tokens,
                cached_tokens,
                output_tokens,
                reasoning_tokens,
            ) = get_usage(
                response
            )

            # ── 종료 사유 ────────────────────────────────

            finish = get_finish_reason(
                response
            )

            status = (
                "정상"
                if content
                else "실패"
            )

            # ── 원문 저장 ────────────────────────────────

            path = (
                save_response(
                    qid,
                    LABEL,
                    run,
                    content,
                )
                if content
                else ""
            )

            # ── 생성 속도 ────────────────────────────────
            #
            # Gemini의 candidates_token_count,
            # 즉 최종 출력 토큰 기준으로 계산
            # ─────────────────────────────────────────────

            if (
                isinstance(
                    output_tokens,
                    (int, float),
                )
                and output_tokens > 0
                and elapsed > 0
            ):
                speed = (
                    output_tokens
                    / elapsed
                )

            else:
                speed = 0

            # ── 콘솔 출력 ────────────────────────────────

            if content:
                print(
                    content[:500]
                    + (
                        "..."
                        if len(content) > 500
                        else ""
                    )
                )
            else:
                print(
                    "(빈 응답)"
                )

            token_text = (
                str(output_tokens)
                if output_tokens != ""
                else "-"
            )

            print(
                f"\n  {elapsed:.2f}초 / "
                f"{speed:.1f} tok/s / "
                f"출력 {token_text}토큰 / "
                f"{chars:,}자"
            )

            if reasoning_tokens != "":
                print(
                    f"  추론토큰: "
                    f"{reasoning_tokens}"
                )

            if cached_tokens not in (
                "",
                0,
            ):
                print(
                    f"  캐시입력토큰: "
                    f"{cached_tokens}"
                )

            if finish:
                print(
                    f"  종료사유: "
                    f"{finish}"
                )

            if chars > CHAR_LIMIT:
                print(
                    f"  주의: 글자수 제약 "
                    f"{CHAR_LIMIT}자를 넘었습니다."
                )

            error_text = ""

            if not content:
                error_text = "빈 응답"

                if finish:
                    error_text += (
                        f" / 종료사유={finish}"
                    )

            # ── CSV row ──────────────────────────────────

            results.append(
                make_row(
                    seq,
                    now,
                    qid,
                    run,
                    status,

                    종료사유=finish,

                    입력토큰=input_tokens,
                    캐시입력토큰=cached_tokens,
                    출력토큰=output_tokens,
                    추론토큰=reasoning_tokens,

                    응답글자수=chars,

                    제약초과=(
                        "Y"
                        if chars > CHAR_LIMIT
                        else ""
                    ),

                    응답초=round(
                        elapsed,
                        2,
                    ),

                    초당토큰=round(
                        speed,
                        1,
                    ),

                    미리보기=preview(
                        content
                    ),

                    원문경로=path,

                    오류=error_text,
                )
            )

    # ─────────────────────────────────────────────────────
    # CSV 저장
    # ─────────────────────────────────────────────────────

    append_csv(
        results
    )

    # ─────────────────────────────────────────────────────
    # 요약
    # ─────────────────────────────────────────────────────

    ok = [
        row
        for row in results
        if row["상태"] == "정상"
    ]

    errors = (
        len(results)
        - len(ok)
    )

    over = sum(
        1
        for row in ok
        if row["제약초과"] == "Y"
    )

    cut = sum(
        1
        for row in ok
        if row["종료사유"] == "토큰한도"
    )

    input_sum = sum(
        row["입력토큰"]
        for row in ok
        if isinstance(
            row["입력토큰"],
            (int, float),
        )
    )

    cached_sum = sum(
        row["캐시입력토큰"]
        for row in ok
        if isinstance(
            row["캐시입력토큰"],
            (int, float),
        )
    )

    output_sum = sum(
        row["출력토큰"]
        for row in ok
        if isinstance(
            row["출력토큰"],
            (int, float),
        )
    )

    reasoning_sum = sum(
        row["추론토큰"]
        for row in ok
        if isinstance(
            row["추론토큰"],
            (int, float),
        )
    )

    print(
        f"\n{'=' * 60}"
        f"\n[요약] "
        f"세션 {SESSION} / "
        f"{MODEL}"
        f"\n{'=' * 60}"
    )

    print(
        f"성공 {len(ok)} / "
        f"실패 {errors} / "
        f"글자수 초과 {over} / "
        f"토큰한도 {cut}"
    )

    print(
        f"토큰 합계: "
        f"입력 {input_sum:,} / "
        f"출력 {output_sum:,}"
    )

    if cached_sum:
        print(
            f"캐시 입력 토큰: "
            f"{cached_sum:,}"
        )

    print(
        f"추론 토큰: "
        f"{reasoning_sum:,}"
    )

    print(
        f"응답 원문: "
        f"{RESP_DIR}/"
    )

    print(
        f"기록: "
        f"{CSV_PATH}"
    )


if __name__ == "__main__":
    main()