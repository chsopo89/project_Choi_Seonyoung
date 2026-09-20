import csv
import statistics
import sys


try:
    sys.stdout.reconfigure(
        encoding="utf-8",
        line_buffering=True,
    )
except Exception:
    pass


def out(msg=""):
    print(msg, flush=True)


# ── 입력 파일 ────────────────────────────────────────────

CSV_PATH = "benchmark_luna_v2.csv"


# ── GPT-5.6 Luna 표준 API 단가 ───────────────────────────
#
# USD / 1M tokens
#
# 일반 입력 : $0.20
# 캐시 입력 : $0.02
# 출력      : $1.20
#

PRICE_IN = 0.20 / 1_000_000
PRICE_CACHED_IN = 0.02 / 1_000_000
PRICE_OUT = 1.20 / 1_000_000


def load(path):
    with open(
        path,
        newline="",
        encoding="utf-8-sig",
    ) as f:
        return list(csv.DictReader(f))


def num(rows, key, cast=float):
    vals = []

    for r in rows or []:
        v = r.get(key, "")

        if v not in ("", None):
            try:
                vals.append(cast(v))
            except (ValueError, TypeError):
                pass

    return vals


def stdev(vals):
    """1건이면 편차를 계산할 수 없으므로 None."""
    return (
        statistics.stdev(vals)
        if len(vals) > 1
        else None
    )


def run_key(r):
    v = str(r.get("회차", ""))

    return (
        int(v)
        if v.isdigit()
        else 0
    )


out("Luna v2 리포트")


# ── CSV 로드 ─────────────────────────────────────────────

try:
    rows = load(CSV_PATH)

except FileNotFoundError:
    out(f"{CSV_PATH} 파일이 없습니다.")
    raise SystemExit(1)


if not rows:
    out(f"{CSV_PATH}에 기록이 없습니다.")
    raise SystemExit(1)


# ── 세션 선택 ───────────────────────────────────────────
#
# python 06.report.luna.py
#   → 가장 마지막 세션
#
# python 06.report.luna.py all
#   → 전체 세션
#
# python 06.report.luna.py 0915-1423
#   → 특정 세션
#

sessions = []

for r in rows:
    s = (r.get("세션") or "").strip()

    if s and s not in sessions:
        sessions.append(s)


arg = (
    sys.argv[1].strip()
    if len(sys.argv) > 1
    else ""
)


if arg.lower() == "all":

    target = None

elif arg:

    if arg not in sessions:

        out(
            f"세션 '{arg}'을(를) "
            f"찾을 수 없습니다."
        )

        out(
            "기록된 세션: "
            f"{', '.join(sessions) or '없음'}"
        )

        raise SystemExit(1)

    target = arg

else:

    target = (
        sessions[-1]
        if sessions
        else None
    )


if target:

    rows = [
        r
        for r in rows
        if (r.get("세션") or "").strip()
        == target
    ]

    out(
        f"세션 {target} "
        f"(전체 {len(sessions)}개 중 1개)"
    )

else:

    out(
        f"전체 세션 "
        f"{len(sessions)}개 합산"
    )


if len(sessions) > 1 and target:

    others = [
        s
        for s in sessions
        if s != target
    ]

    out(
        "제외한 세션: "
        + ", ".join(others)
    )


# ── 정상/제외 분류 ──────────────────────────────────────

ok = []
bad = []


for r in rows:

    tok_val = str(
        r.get("출력토큰", "")
    ).strip()

    try:
        tok_num = int(tok_val)
    except (ValueError, TypeError):
        tok_num = 0

    if (
        r.get("상태") == "정상"
        and tok_num > 0
    ):
        ok.append(r)

    else:
        bad.append(r)


out(
    f"정상 {len(ok)}건 / "
    f"제외 {len(bad)}건"
)


if not ok:
    out("집계할 정상 기록이 없습니다.")
    raise SystemExit(1)


bar = "-" * 68


# ── 기본 값 ──────────────────────────────────────────────

tok_out = num(
    ok,
    "출력토큰",
    int,
)

tok_in = num(
    ok,
    "입력토큰",
    int,
)

reasoning = num(
    ok,
    "추론토큰",
    int,
)

cached_in = num(
    ok,
    "캐시입력토큰",
    int,
)

chars = num(
    ok,
    "응답글자수",
    int,
)

sec = num(
    ok,
    "응답초",
)

tps = num(
    ok,
    "초당토큰",
)


over_rows = [
    r
    for r in ok
    if r.get("제약초과") == "Y"
]


# ── 요약 ────────────────────────────────────────────────

out("")
out("요약")
out(bar)

out(
    f"{'측정 건수':<16}"
    f"{len(ok):>12}"
)

out(
    f"{'평균 출력토큰':<16}"
    f"{statistics.mean(tok_out):>12.0f}"
)

out(
    f"{'출력 최소-최대':<16}"
    f"{f'{min(tok_out)}-{max(tok_out)}':>12}"
)


sd = stdev(tok_out)

if sd is not None:
    out(
        f"{'출력 편차':<16}"
        f"{sd:>12.0f}"
    )


out(
    f"{'평균 글자수':<16}"
    f"{statistics.mean(chars):>12.0f}"
)

out(
    f"{'글자수 최소-최대':<16}"
    f"{f'{min(chars)}-{max(chars)}':>12}"
)

out(
    f"{'제약 초과':<16}"
    f"{f'{len(over_rows)}/{len(ok)}':>12}"
)

out(
    f"{'평균 응답초':<16}"
    f"{statistics.mean(sec):>12.1f}"
)

out(
    f"{'최장 응답초':<16}"
    f"{max(sec):>12.1f}"
)

out(
    f"{'평균 tok/s':<16}"
    f"{statistics.mean(tps):>12.1f}"
)

out(
    f"{'총 입력토큰':<16}"
    f"{sum(tok_in):>12,}"
)

out(
    f"{'총 출력토큰':<16}"
    f"{sum(tok_out):>12,}"
)


if reasoning:

    out(
        f"{'총 추론토큰':<16}"
        f"{sum(reasoning):>12,}"
    )

    out(
        f"{'평균 추론토큰':<16}"
        f"{statistics.mean(reasoning):>12.0f}"
    )


if cached_in:

    out(
        f"{'캐시 입력토큰':<16}"
        f"{sum(cached_in):>12,}"
    )


# ── 비용 ────────────────────────────────────────────────
#
# 입력토큰에는 cached input도 포함된다.
# 따라서:
#
# 일반 입력 = 전체 입력 - 캐시 입력
#

total_in = sum(tok_in)

total_cached = (
    sum(cached_in)
    if cached_in
    else 0
)

normal_in = max(
    total_in - total_cached,
    0,
)


cost_normal_in = (
    normal_in
    * PRICE_IN
)

cost_cached_in = (
    total_cached
    * PRICE_CACHED_IN
)

cost_out = (
    sum(tok_out)
    * PRICE_OUT
)

cost_total = (
    cost_normal_in
    + cost_cached_in
    + cost_out
)


out("")
out("비용 (USD)")
out(bar)

out(
    f"{'일반 입력':<16}"
    f"${cost_normal_in:>13.6f}"
    f"  "
    f"({normal_in:,} 토큰 "
    f"x $0.20/1M)"
)


if total_cached:

    out(
        f"{'캐시 입력':<16}"
        f"${cost_cached_in:>13.6f}"
        f"  "
        f"({total_cached:,} 토큰 "
        f"x $0.02/1M)"
    )


out(
    f"{'출력':<16}"
    f"${cost_out:>13.6f}"
    f"  "
    f"({sum(tok_out):,} 토큰 "
    f"x $1.20/1M)"
)

out(
    f"{'합계':<16}"
    f"${cost_total:>13.6f}"
)

out(
    f"{'호출당 평균':<16}"
    f"${cost_total / len(ok):>13.6f}"
)


if cost_total > 0:

    out(
        f"{'출력 비용 비중':<16}"
        f"{cost_out / cost_total * 100:>13.1f}%"
    )


out(
    f"{'1,000회 환산':<16}"
    f"${cost_total / len(ok) * 1000:>13.2f}"
)


# ── 문제별 집계 ─────────────────────────────────────────

by_q = {}

for r in ok:

    qid = r.get(
        "문제",
        "",
    )

    by_q.setdefault(
        qid,
        [],
    ).append(r)


out("")
out("문제별 집계 (회차 평균)")
out(bar)

out(
    f"{'문제':<7}"
    f"{'회차':>5}"
    f"{'토큰평균':>10}"
    f"{'토큰편차':>10}"
    f"{'글자평균':>10}"
    f"{'응답초':>10}"
    f"{'추론':>9}"
    f"{'초과':>7}"
)

out(bar)


for qid in sorted(by_q):

    qrows = by_q[qid]

    q_tok = num(
        qrows,
        "출력토큰",
        int,
    )

    q_chr = num(
        qrows,
        "응답글자수",
        int,
    )

    q_sec = num(
        qrows,
        "응답초",
    )

    q_reason = num(
        qrows,
        "추론토큰",
        int,
    )

    q_over = sum(
        1
        for r in qrows
        if r.get("제약초과") == "Y"
    )

    sd = stdev(q_tok)

    sd_txt = (
        f"{sd:.0f}"
        if sd is not None
        else "-"
    )

    reason_txt = (
        f"{statistics.mean(q_reason):.0f}"
        if q_reason
        else "-"
    )

    out(
        f"{qid:<7}"
        f"{len(qrows):>5}"
        f"{statistics.mean(q_tok):>10.0f}"
        f"{sd_txt:>10}"
        f"{statistics.mean(q_chr):>10.0f}"
        f"{statistics.mean(q_sec):>10.1f}"
        f"{reason_txt:>9}"
        f"{f'{q_over}/{len(qrows)}':>7}"
    )


# ── 회차별 원자료 ───────────────────────────────────────

out("")
out("회차별 원자료")
out(bar)

out(
    f"{'문제':<8}"
    f"{'회차':>5}"
    f"{'출력토큰':>11}"
    f"{'추론':>10}"
    f"{'글자수':>10}"
    f"{'응답초':>10}"
    f"{'tok/s':>10}"
)

out(bar)


for r in sorted(
    ok,
    key=lambda x: (
        x.get("문제", ""),
        run_key(x),
    ),
):

    reason = (
        r.get("추론토큰", "")
        or "-"
    )

    out(
        f"{r['문제']:<8}"
        f"{r.get('회차', ''):>5}"
        f"{r['출력토큰']:>11}"
        f"{reason:>10}"
        f"{r['응답글자수']:>10}"
        f"{r['응답초']:>10}"
        f"{r['초당토큰']:>10}"
    )


# ── 이상 행 ─────────────────────────────────────────────

if bad:

    out("")
    out("확인 필요")
    out(bar)

    for r in bad:

        why = (
            r.get("오류")
            or r.get("상태")
            or ""
        )[:40]

        out(
            f"  "
            f"{r.get('문제') or '-':<6}"
            f"run{r.get('회차') or '-':<4}"
            f"{why}"
        )


# ── 글자수 초과 ─────────────────────────────────────────

if over_rows:

    out("")
    out(
        f"글자수 초과 "
        f"({len(over_rows)}건)"
    )

    out(bar)

    for r in sorted(
        over_rows,
        key=lambda x: (
            x.get("문제", ""),
            run_key(x),
        ),
    ):

        out(
            f"  "
            f"{r['문제']:<6}"
            f"run{r['회차']:<4}"
            f"{r['응답글자수']}자"
        )


out("")
out(
    f"집계 {len(ok)}건 / "
    f"입력 {total_in:,} / "
    f"출력 {sum(tok_out):,} / "
    f"비용 ${cost_total:.6f}"
)
out("")