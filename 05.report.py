import csv
from collections import defaultdict
from pathlib import Path


# ============================================================
# 기본 설정
# ============================================================

BASE = Path(__file__).resolve().parent

LOCAL_CSV = BASE / "benchmark_local_v3.csv"
LUNA_CSV = BASE / "benchmark_luna_v2.csv"
GEMINI_CSV = BASE / "benchmark_gemini.csv"

SUMMARY_CSV = BASE / "summary.csv"

CHAR_LIMIT = 3000

COMMON_QIDS = {
    "q03",
    "q06",
    "q07",
    "q09",
    "q10",
}


# ============================================================
# 공통 유틸
# ============================================================

def clean(value):
    if value is None:
        return ""
    return str(value).strip()


def to_float(value):
    value = clean(value)

    if not value:
        return None

    try:
        return float(value.replace(",", ""))
    except (TypeError, ValueError):
        return None


def to_int(value):
    number = to_float(value)

    if number is None:
        return None

    return int(number)


def mean(values):
    values = [
        value
        for value in values
        if value is not None
    ]

    if not values:
        return None, 0

    return sum(values) / len(values), len(values)


def fmt_num(value, digits=2):
    if value is None:
        return "-"

    return f"{value:.{digits}f}"


def fmt_pct(value):
    if value is None:
        return "-"

    return f"{value:.1f}%"


def is_success(row):
    status = clean(
        row.get("상태")
    ).lower()

    return status in {
        "정상",
        "ok",
        "success",
    }


def is_token_limit(row):
    reason = clean(
        row.get("종료사유")
    ).lower()

    return (
        "토큰한도" in reason
        or "max_token" in reason
        or "max token" in reason
        or "length" == reason
    )


def is_over_limit(row):
    flag = clean(
        row.get("제약초과")
    ).upper()

    if flag == "Y":
        return True

    chars = to_int(
        row.get("응답글자수")
    )

    return (
        chars is not None
        and chars > CHAR_LIMIT
    )


def model_name(row):
    """
    보고서에 표시할 모델 이름.

    Local:
        모델태그 -> 모델

    Luna/Gemini:
        모델ID -> 모델
    """

    for key in (
        "모델ID",
        "모델태그",
        "모델",
    ):
        value = clean(
            row.get(key)
        )

        if value:
            return value

    return "unknown"


# ============================================================
# CSV 읽기
# ============================================================

def read_csv(path):
    if not path.exists():
        print(
            f"[없음] {path.name}"
        )
        return []

    with path.open(
        encoding="utf-8-sig",
        newline="",
    ) as f:
        rows = list(
            csv.DictReader(f)
        )

    return rows


def latest_session_rows(rows):
    """
    CSV의 가장 마지막 유효 세션만 선택한다.

    CSV는 실행 순서대로 append된다는 전제에서
    마지막 행의 세션을 현재 본 실험 세션으로 본다.
    """

    sessions = [
        clean(row.get("세션"))
        for row in rows
        if clean(row.get("세션"))
    ]

    if not sessions:
        return rows, "-"

    latest = sessions[-1]

    selected = [
        row
        for row in rows
        if clean(row.get("세션")) == latest
    ]

    return selected, latest


# ============================================================
# 모델별 통계
# ============================================================

def aggregate(rows):
    attempts = len(rows)

    success_rows = [
        row
        for row in rows
        if is_success(row)
    ]

    success = len(
        success_rows
    )

    failure = (
        attempts
        - success
    )

    success_rate = (
        success / attempts * 100
        if attempts
        else None
    )

    token_limit = sum(
        1
        for row in rows
        if is_token_limit(row)
    )

    over_limit = sum(
        1
        for row in success_rows
        if is_over_limit(row)
    )

    latency_mean, latency_n = mean([
        to_float(
            row.get("응답초")
        )
        for row in success_rows
    ])

    output_mean, output_n = mean([
        to_float(
            row.get("출력토큰")
        )
        for row in success_rows
    ])

    input_mean, input_n = mean([
        to_float(
            row.get("입력토큰")
        )
        for row in success_rows
    ])

    chars_mean, chars_n = mean([
        to_float(
            row.get("응답글자수")
        )
        for row in success_rows
    ])

    speed_mean, speed_n = mean([
        to_float(
            row.get("초당토큰")
        )
        for row in success_rows
    ])

    vram_mean, vram_n = mean([
        to_float(
            row.get("VRAM_MiB")
        )
        for row in success_rows
    ])

    reasoning_mean, reasoning_n = mean([
        to_float(
            row.get("추론토큰")
        )
        for row in success_rows
        if clean(
            row.get("추론토큰")
        ) != ""
    ])

    cached_mean, cached_n = mean([
        to_float(
            row.get("캐시입력토큰")
        )
        for row in success_rows
        if clean(
            row.get("캐시입력토큰")
        ) != ""
    ])

    return {
        "attempts": attempts,

        "success": success,
        "failure": failure,
        "success_rate": success_rate,

        "token_limit": token_limit,
        "over_limit": over_limit,

        "latency_mean": latency_mean,
        "latency_n": latency_n,

        "input_mean": input_mean,
        "input_n": input_n,

        "output_mean": output_mean,
        "output_n": output_n,

        "chars_mean": chars_mean,
        "chars_n": chars_n,

        "speed_mean": speed_mean,
        "speed_n": speed_n,

        "vram_mean": vram_mean,
        "vram_n": vram_n,

        "reasoning_mean": reasoning_mean,
        "reasoning_n": reasoning_n,

        "cached_mean": cached_mean,
        "cached_n": cached_n,
    }


# ============================================================
# 모델 그룹화
# ============================================================

def group_models(rows):
    groups = defaultdict(list)

    for row in rows:
        groups[
            model_name(row)
        ].append(row)

    return dict(groups)


# ============================================================
# 출력
# ============================================================

def print_section(
    title,
    groups,
    role,
    session,
):
    print()
    print(
        "=" * 100
    )
    print(title)
    print(
        "=" * 100
    )

    print(
        f"세션: {session}"
    )

    print(
        f"구분: {role}"
    )

    print()

    header = (
        f"{'모델':<22}"
        f"{'시도':>6}"
        f"{'성공':>6}"
        f"{'성공률':>9}"
        f"{'토큰한도':>10}"
        f"{'>3000자':>9}"
        f"{'응답초':>11}"
        f"{'출력tok':>11}"
        f"{'글자수':>11}"
        f"{'tok/s':>10}"
    )

    print(header)
    print("-" * 100)

    summaries = []

    for model in sorted(
        groups
    ):
        stats = aggregate(
            groups[model]
        )

        print(
            f"{model:<22}"
            f"{stats['attempts']:>6}"
            f"{stats['success']:>6}"
            f"{fmt_pct(stats['success_rate']):>9}"
            f"{stats['token_limit']:>10}"
            f"{stats['over_limit']:>9}"
            f"{fmt_num(stats['latency_mean']):>11}"
            f"{fmt_num(stats['output_mean'], 1):>11}"
            f"{fmt_num(stats['chars_mean'], 1):>11}"
            f"{fmt_num(stats['speed_mean'], 1):>10}"
        )

        summaries.append(
            (
                model,
                stats,
            )
        )

    print()
    print("[지표별 n]")

    for model, stats in summaries:
        print(
            f"  {model}: "
            f"응답초 n={stats['latency_n']}, "
            f"출력토큰 n={stats['output_n']}, "
            f"글자수 n={stats['chars_n']}, "
            f"tok/s n={stats['speed_n']}"
        )

    return summaries


# ============================================================
# 추가 상세 출력
# ============================================================

def print_local_detail(
    groups,
):
    print()
    print(
        "=" * 100
    )
    print(
        "[LOCAL 성능 상세]"
    )
    print(
        "=" * 100
    )

    for model in sorted(
        groups
    ):
        stats = aggregate(
            groups[model]
        )

        print()
        print(
            f"[{model}]"
        )

        print(
            f"  평균 입력 토큰 : "
            f"{fmt_num(stats['input_mean'], 1)} "
            f"(n={stats['input_n']})"
        )

        print(
            f"  평균 출력 토큰 : "
            f"{fmt_num(stats['output_mean'], 1)} "
            f"(n={stats['output_n']})"
        )

        print(
            f"  평균 응답 시간 : "
            f"{fmt_num(stats['latency_mean'])}초 "
            f"(n={stats['latency_n']})"
        )

        print(
            f"  평균 생성 속도 : "
            f"{fmt_num(stats['speed_mean'], 1)} tok/s "
            f"(n={stats['speed_n']})"
        )

        print(
            f"  평균 VRAM      : "
            f"{fmt_num(stats['vram_mean'], 1)} MiB "
            f"(n={stats['vram_n']})"
        )

        print(
            f"  평균 응답 길이 : "
            f"{fmt_num(stats['chars_mean'], 1)}자 "
            f"(n={stats['chars_n']})"
        )

        print(
            f"  3000자 초과    : "
            f"{stats['over_limit']}건"
        )

        print(
            f"  토큰한도 종료  : "
            f"{stats['token_limit']}건"
        )


def print_cloud_detail(
    title,
    rows,
):
    print()
    print(
        "=" * 100
    )
    print(title)
    print(
        "=" * 100
    )

    groups = group_models(
        rows
    )

    for model in sorted(
        groups
    ):
        stats = aggregate(
            groups[model]
        )

        print()
        print(
            f"[{model}]"
        )

        print(
            f"  성공           : "
            f"{stats['success']} / "
            f"{stats['attempts']} "
            f"({fmt_pct(stats['success_rate'])})"
        )

        print(
            f"  평균 응답 시간 : "
            f"{fmt_num(stats['latency_mean'])}초 "
            f"(n={stats['latency_n']})"
        )

        print(
            f"  평균 입력 토큰 : "
            f"{fmt_num(stats['input_mean'], 1)} "
            f"(n={stats['input_n']})"
        )

        print(
            f"  평균 출력 토큰 : "
            f"{fmt_num(stats['output_mean'], 1)} "
            f"(n={stats['output_n']})"
        )

        print(
            f"  평균 응답 길이 : "
            f"{fmt_num(stats['chars_mean'], 1)}자 "
            f"(n={stats['chars_n']})"
        )

        print(
            f"  평균 추론 토큰 : "
            f"{fmt_num(stats['reasoning_mean'], 1)} "
            f"(n={stats['reasoning_n']})"
        )

        print(
            f"  평균 캐시 입력 : "
            f"{fmt_num(stats['cached_mean'], 1)} "
            f"(n={stats['cached_n']})"
        )

        print(
            f"  3000자 초과    : "
            f"{stats['over_limit']}건"
        )

        print(
            f"  토큰한도 종료  : "
            f"{stats['token_limit']}건"
        )


# ============================================================
# Cloud 설정 이상 관측
# ============================================================

def find_output_limit_anomalies(
    provider,
    rows,
):
    anomalies = []

    for row in rows:
        output_tokens = to_int(
            row.get("출력토큰")
        )

        max_tokens = to_int(
            row.get("max_output_tokens")
        )

        if (
            output_tokens is not None
            and max_tokens is not None
            and output_tokens > max_tokens
        ):
            anomalies.append({
                "provider": provider,
                "session": clean(
                    row.get("세션")
                ),
                "qid": clean(
                    row.get("문제")
                ),
                "model": model_name(
                    row
                ),
                "output_tokens": output_tokens,
                "max_output_tokens": max_tokens,
            })

    return anomalies


# ============================================================
# summary.csv
# ============================================================

SUMMARY_FIELDS = [
    "범위",
    "구분",
    "세션",
    "모델",

    "시도수",
    "성공수",
    "실패수",
    "성공률_pct",

    "토큰한도수",
    "3000자초과수",

    "평균응답초",
    "응답초_n",

    "평균입력토큰",
    "입력토큰_n",

    "평균출력토큰",
    "출력토큰_n",

    "평균응답글자수",
    "글자수_n",

    "평균초당토큰",
    "초당토큰_n",

    "평균VRAM_MiB",
    "VRAM_n",

    "평균추론토큰",
    "추론토큰_n",

    "평균캐시입력토큰",
    "캐시입력토큰_n",
]


def summary_row(
    scope,
    role,
    session,
    model,
    stats,
):
    return {
        "범위": scope,
        "구분": role,
        "세션": session,
        "모델": model,

        "시도수": stats["attempts"],
        "성공수": stats["success"],
        "실패수": stats["failure"],

        "성공률_pct": (
            round(
                stats["success_rate"],
                2,
            )
            if stats["success_rate"] is not None
            else ""
        ),

        "토큰한도수": stats["token_limit"],
        "3000자초과수": stats["over_limit"],

        "평균응답초": (
            round(
                stats["latency_mean"],
                3,
            )
            if stats["latency_mean"] is not None
            else ""
        ),

        "응답초_n": stats["latency_n"],

        "평균입력토큰": (
            round(
                stats["input_mean"],
                2,
            )
            if stats["input_mean"] is not None
            else ""
        ),

        "입력토큰_n": stats["input_n"],

        "평균출력토큰": (
            round(
                stats["output_mean"],
                2,
            )
            if stats["output_mean"] is not None
            else ""
        ),

        "출력토큰_n": stats["output_n"],

        "평균응답글자수": (
            round(
                stats["chars_mean"],
                2,
            )
            if stats["chars_mean"] is not None
            else ""
        ),

        "글자수_n": stats["chars_n"],

        "평균초당토큰": (
            round(
                stats["speed_mean"],
                2,
            )
            if stats["speed_mean"] is not None
            else ""
        ),

        "초당토큰_n": stats["speed_n"],

        "평균VRAM_MiB": (
            round(
                stats["vram_mean"],
                2,
            )
            if stats["vram_mean"] is not None
            else ""
        ),

        "VRAM_n": stats["vram_n"],

        "평균추론토큰": (
            round(
                stats["reasoning_mean"],
                2,
            )
            if stats["reasoning_mean"] is not None
            else ""
        ),

        "추론토큰_n": stats["reasoning_n"],

        "평균캐시입력토큰": (
            round(
                stats["cached_mean"],
                2,
            )
            if stats["cached_mean"] is not None
            else ""
        ),

        "캐시입력토큰_n": stats["cached_n"],
    }


def write_summary(
    local_all,
    local_common,
    luna_rows,
    gemini_rows,
    local_session,
    luna_session,
    gemini_session,
):
    output = []

    for model, rows in sorted(
        group_models(
            local_all
        ).items()
    ):
        output.append(
            summary_row(
                "Local 전체 10문항",
                "핵심",
                local_session,
                model,
                aggregate(rows),
            )
        )

    for model, rows in sorted(
        group_models(
            local_common
        ).items()
    ):
        output.append(
            summary_row(
                "공통 5문항",
                "핵심",
                local_session,
                model,
                aggregate(rows),
            )
        )

    for model, rows in sorted(
        group_models(
            luna_rows
        ).items()
    ):
        output.append(
            summary_row(
                "공통 5문항",
                "핵심",
                luna_session,
                model,
                aggregate(rows),
            )
        )

    for model, rows in sorted(
        group_models(
            gemini_rows
        ).items()
    ):
        output.append(
            summary_row(
                "공통 5문항",
                "참고",
                gemini_session,
                model,
                aggregate(rows),
            )
        )

    with SUMMARY_CSV.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=SUMMARY_FIELDS,
        )

        writer.writeheader()
        writer.writerows(
            output
        )

    print()
    print(
        f"[저장] {SUMMARY_CSV.name}"
    )


# ============================================================
# main
# ============================================================

def main():

    # --------------------------------------------------------
    # 원본 읽기
    # --------------------------------------------------------

    local_raw = read_csv(
        LOCAL_CSV
    )

    luna_raw = read_csv(
        LUNA_CSV
    )

    gemini_raw = read_csv(
        GEMINI_CSV
    )

    # --------------------------------------------------------
    # 최신 세션만 선택
    # --------------------------------------------------------

    local_rows, local_session = latest_session_rows(
        local_raw
    )

    luna_rows, luna_session = latest_session_rows(
        luna_raw
    )

    gemini_rows, gemini_session = latest_session_rows(
        gemini_raw
    )

    # --------------------------------------------------------
    # Local 공통 5문항
    # --------------------------------------------------------

    local_common = [
        row
        for row in local_rows
        if clean(
            row.get("문제")
        ) in COMMON_QIDS
    ]

    # --------------------------------------------------------
    # 기본 데이터 확인
    # --------------------------------------------------------

    print()
    print(
        "#" * 100
    )
    print(
        "LLM BENCHMARK 정량평가"
    )
    print(
        "#" * 100
    )

    print()
    print(
        "[입력 데이터]"
    )

    print(
        f"  Local  : {LOCAL_CSV.name} "
        f"/ 세션 {local_session} "
        f"/ {len(local_rows)}건"
    )

    print(
        f"  Luna   : {LUNA_CSV.name} "
        f"/ 세션 {luna_session} "
        f"/ {len(luna_rows)}건"
    )

    print(
        f"  Gemini : {GEMINI_CSV.name} "
        f"/ 세션 {gemini_session} "
        f"/ {len(gemini_rows)}건 "
        f"(참고용)"
    )

    # --------------------------------------------------------
    # 1. Local 전체
    # --------------------------------------------------------

    local_groups = group_models(
        local_rows
    )

    print_section(
        "[1] Local 전체 10문항 × 2회",
        local_groups,
        "핵심 Local 비교",
        local_session,
    )

    print_local_detail(
        local_groups
    )

    # --------------------------------------------------------
    # 2. Local 공통 5문항
    # --------------------------------------------------------

    local_common_groups = group_models(
        local_common
    )

    print_section(
        "[2] Local 공통 5문항만 추출",
        local_common_groups,
        "Local–Cloud 비교용",
        local_session,
    )

    # --------------------------------------------------------
    # 3. Luna
    # --------------------------------------------------------

    luna_groups = group_models(
        luna_rows
    )

    print_section(
        "[3] Luna 공통 5문항",
        luna_groups,
        "핵심 Cloud 비교",
        luna_session,
    )

    print_cloud_detail(
        "[LUNA 상세]",
        luna_rows,
    )

    # --------------------------------------------------------
    # 4. Gemini 참고
    # --------------------------------------------------------

    gemini_groups = group_models(
        gemini_rows
    )

    print_section(
        "[4] Gemini 공통 5문항",
        gemini_groups,
        "참고용 Cloud 실험",
        gemini_session,
    )

    print_cloud_detail(
        "[GEMINI 참고 상세]",
        gemini_rows,
    )

    # --------------------------------------------------------
    # 5. Cloud API 이상 관측
    # --------------------------------------------------------

    anomalies = []

    anomalies.extend(
        find_output_limit_anomalies(
            "Luna",
            luna_rows,
        )
    )

    anomalies.extend(
        find_output_limit_anomalies(
            "Gemini",
            gemini_rows,
        )
    )

    print()
    print(
        "=" * 100
    )
    print(
        "[5] 기록 이상/관측 확인"
    )
    print(
        "=" * 100
    )

    if anomalies:
        for item in anomalies:
            print(
                f"  ⚠ {item['provider']} "
                f"{item['model']} "
                f"{item['qid']} / "
                f"출력토큰={item['output_tokens']} > "
                f"max_output_tokens="
                f"{item['max_output_tokens']}"
            )

        print()
        print(
            "  위 값은 CSV를 수정하지 않고 "
            "API가 반환한 실측값 그대로 유지합니다."
        )

    else:
        print(
            "  특이 기록 없음"
        )

    # --------------------------------------------------------
    # 6. summary.csv
    # --------------------------------------------------------

    write_summary(
        local_rows,
        local_common,
        luna_rows,
        gemini_rows,
        local_session,
        luna_session,
        gemini_session,
    )

    print()
    print(
        "=" * 100
    )
    print(
        "정량평가 완료"
    )
    print(
        "=" * 100
    )

    print(
        "핵심 비교: Local 3개 모델 + Luna"
    )

    print(
        "Gemini: 참고 실험으로 별도 해석"
    )

    print(
        "정성 품질 점수는 이 결과와 분리하여 "
        "07.scoring.py에서 평가합니다."
    )


if __name__ == "__main__":
    main()