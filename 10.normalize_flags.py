"""
10.normalize_flags.py

점수 CSV의 플래그 값을 07.scoring.py가 사용하는 형식으로 통일한다.

07.scoring.py의 플래그 형식:
    해당 있음  -> "Y"
    해당 없음  -> ""

과거 점수 CSV에는 일부 플래그가 1/0, true/false 등의 형식으로
저장되어 있을 수 있다. 이 스크립트는 그런 값을 Y/빈칸으로 변환한다.

현재 scores_v3.csv는 07.scoring.py가 직접 생성하므로
정상적으로 생성된 경우 별도의 변환이 필요하지 않다.

기본 대상:
    scores_v3.csv

다른 점수 파일을 변환하려면 --scores로 지정한다.


사용법

현재 점수 파일 확인:

    python .\\10.normalize_flags.py

실제 변환:

    python .\\10.normalize_flags.py --apply


과거 점수 파일 확인:

    python .\\10.normalize_flags.py --scores scores_v2_t1.csv

과거 점수 파일 실제 변환:

    python .\\10.normalize_flags.py ^
        --scores scores_v2_t1.csv ^
        --apply


변환 규칙:

    1, true, yes, y  -> Y

    0, false, no, n  -> 빈칸

    Y                -> Y

    빈칸             -> 빈칸


알 수 없는 값이 하나라도 있으면 파일을 변경하지 않고 중단한다.

--apply를 사용하면 원본 파일을 먼저 백업한 뒤 변환한다.
"""

import argparse
import csv
import shutil
import sys

from collections import Counter
from datetime import datetime
from pathlib import Path


# ─────────────────────────────────────────────────────────────
# 기본 설정
# ─────────────────────────────────────────────────────────────

BASE = Path(__file__).resolve().parent

DEFAULT_SCORES = "scores_v3.csv"


FLAG_COLS = [
    "risky_flag",
    "over_limit",
    "repeat_flag",
    "excluded_flag",
    "contradicted_flag",
    "facts_flag",
]


# 소문자로 변환한 뒤 비교한다.
TO_Y = {
    "1",
    "true",
    "yes",
    "y",
}


TO_BLANK = {
    "0",
    "false",
    "no",
    "n",
    "",
}


# ─────────────────────────────────────────────────────────────
# 경로 처리
# ─────────────────────────────────────────────────────────────

def resolve_scores_path(value):

    path = Path(value)

    if not path.is_absolute():
        path = BASE / path

    return path


# ─────────────────────────────────────────────────────────────
# CSV 읽기
# ─────────────────────────────────────────────────────────────

def read_scores(path):

    if not path.exists():
        sys.exit(
            f"[중단] 점수 파일을 찾지 못했습니다:\n"
            f"  {path}"
        )

    if path.stat().st_size == 0:
        sys.exit(
            f"[중단] 점수 파일이 비어 있습니다:\n"
            f"  {path}"
        )

    with path.open(
        encoding="utf-8-sig",
        newline="",
    ) as f:

        reader = csv.DictReader(f)

        header = reader.fieldnames or []
        rows = list(reader)

    return header, rows


# ─────────────────────────────────────────────────────────────
# 플래그 열 확인
# ─────────────────────────────────────────────────────────────

def find_flag_columns(header):

    return [
        col
        for col in FLAG_COLS
        if col in header
    ]


# ─────────────────────────────────────────────────────────────
# 값 검증
# ─────────────────────────────────────────────────────────────

def check_unknown_values(
    rows,
    cols,
):

    before = {
        col: Counter(
            row.get(col, "")
            for row in rows
        )
        for col in cols
    }

    odd = {}

    allowed = (
        TO_Y
        | TO_BLANK
    )

    for col in cols:

        unknown = []

        for value in before[col]:

            normalized = (
                value
                or ""
            ).strip().lower()

            if normalized not in allowed:
                unknown.append(value)

        if unknown:
            odd[col] = unknown

    return before, odd


# ─────────────────────────────────────────────────────────────
# 변환
# ─────────────────────────────────────────────────────────────

def normalize_rows(
    rows,
    cols,
):

    changed = 0

    for row in rows:

        for col in cols:

            original = (
                row.get(col, "")
                or ""
            )

            value = (
                original
                .strip()
                .lower()
            )

            new = (
                "Y"
                if value in TO_Y
                else ""
            )

            if original != new:

                row[col] = new
                changed += 1

    return changed


# ─────────────────────────────────────────────────────────────
# 통계 출력
# ─────────────────────────────────────────────────────────────

def print_stats(
    rows,
    cols,
    before,
    changed,
):

    print(
        f"\n대상 행: {len(rows)}개"
    )

    print(
        f"바뀌는 칸: {changed}개"
    )

    print(
        "\n[플래그별 변환]"
    )

    for col in cols:

        after = Counter(
            row.get(col, "")
            for row in rows
        )

        print(
            f"  {col:18s} "
            f"변환 전 {dict(before[col])}"
        )

        print(
            f"  {'':18s} "
            f"→ 변환 후 "
            f"{{'Y': {after.get('Y', 0)}, "
            f"'': {after.get('', 0)}}}"
        )


# ─────────────────────────────────────────────────────────────
# 모델별 플래그 통계
# ─────────────────────────────────────────────────────────────

def print_model_stats(
    rows,
    cols,
):

    required = {
        "model",
        "qid",
        "run",
    }

    if not rows:
        return

    header = set(
        rows[0].keys()
    )

    if not required.issubset(header):

        print(
            "\n[모델별 통계 생략]"
        )

        print(
            "model / qid / run 열 중 "
            "일부가 없습니다."
        )

        return

    print(
        "\n[모델별 플래그 응답 수]"
    )

    for col in cols:

        hit = {
            (
                row.get("model", ""),
                row.get("qid", ""),
                row.get("run", ""),
            )
            for row in rows
            if row.get(col) == "Y"
        }

        counts = Counter(
            model
            for model, _, _ in hit
        )

        print(
            f"  {col:18s} "
            f"{dict(counts)}"
        )


# ─────────────────────────────────────────────────────────────
# CSV 저장
# ─────────────────────────────────────────────────────────────

def write_scores(
    path,
    header,
    rows,
):

    # 원본 파일의 BOM과 줄바꿈 방식을 유지한다.
    raw = path.read_bytes()

    encoding = (
        "utf-8-sig"
        if raw.startswith(
            b"\xef\xbb\xbf"
        )
        else "utf-8"
    )

    eol = (
        "\r\n"
        if b"\r\n"
        in raw[:4096]
        else "\n"
    )

    backup = path.with_name(
        f"{path.name}.bak_"
        f"{datetime.now():%Y%m%d_%H%M%S}"
    )

    shutil.copy2(
        path,
        backup,
    )

    with path.open(
        "w",
        encoding=encoding,
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=header,
            lineterminator=eol,
        )

        writer.writeheader()

        writer.writerows(
            rows
        )

    return backup


# ─────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────

def main():

    parser = argparse.ArgumentParser(
        description=(
            "점수 CSV의 플래그를 "
            "Y/빈칸 형식으로 통일"
        )
    )

    parser.add_argument(
        "--scores",
        default=DEFAULT_SCORES,
        help=(
            "변환할 점수 CSV "
            f"(기본: {DEFAULT_SCORES})"
        ),
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "백업 후 실제로 파일을 변환"
        ),
    )

    args = parser.parse_args()


    scores = resolve_scores_path(
        args.scores
    )


    print(
        f"[대상] {scores.name}"
    )


    header, rows = read_scores(
        scores
    )


    cols = find_flag_columns(
        header
    )


    if not cols:

        sys.exit(
            "[중단] 플래그 열을 "
            "찾지 못했습니다."
        )


    missing = [
        col
        for col in FLAG_COLS
        if col not in header
    ]


    if missing:

        print(
            "[주의] 없는 플래그 열:",
            ", ".join(missing),
        )


    before, odd = (
        check_unknown_values(
            rows,
            cols,
        )
    )


    if odd:

        print(
            "\n[중단] 알 수 없는 "
            "플래그 값이 있습니다."
        )

        for col, values in odd.items():

            print(
                f"  {col}: {values}"
            )

        print(
            "\n파일은 변경하지 않았습니다."
        )

        sys.exit(1)


    changed = normalize_rows(
        rows,
        cols,
    )


    print_stats(
        rows,
        cols,
        before,
        changed,
    )


    print_model_stats(
        rows,
        cols,
    )


    # 이미 정상 형식이면 파일을 다시 쓸 필요가 없다.
    if changed == 0:

        print(
            "\n변환할 값이 없습니다."
        )

        print(
            "현재 플래그 형식이 이미 "
            "07.scoring.py와 일치합니다."
        )

        return


    if not args.apply:

        print(
            "\n미리보기입니다."
        )

        print(
            "문제없으면 --apply를 붙여 "
            "실행하세요."
        )

        return


    backup = write_scores(
        scores,
        header,
        rows,
    )


    print(
        "\n변환 완료"
    )

    print(
        f"백업: {backup.name}"
    )

    print(
        "\n확인:"
    )

    print(
        "  python .\\07.scoring.py "
        "--summary"
    )


if __name__ == "__main__":
    main()