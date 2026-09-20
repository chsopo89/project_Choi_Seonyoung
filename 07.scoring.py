"""
07.scoring.py — 모델 응답 채점 보조 (LLM 미사용)

answer_keys.py v2.2 기준.
- 자동 표시는 채점 후보를 보여줄 뿐 최종 점수를 자동 결정하지 않는다.
- 점수는 사람이 입력한다.
- A축은 검증 가능한 주장이 없을 때 N/A를 허용한다.
- --redo는 SCORE_UNIQUE_KEY 기준으로 기존 행을 실제 교체(upsert)한다.

현재 평가 입력(정리 전 기존 결과를 읽기 위해 유지)
  Ollama : benchmark_local_v3.csv  / responses_v3/
  Luna   : benchmark_luna_v2.csv   / responses_luna_v2/
  Gemini : benchmark_gemini_v2.csv / responses_gemini_v2/

현재 통합 점수 파일
  scores.csv
"""

import argparse
import csv
import json
import random
import re
import sys
import unicodedata
import zlib
from collections import Counter
from datetime import datetime
from pathlib import Path

from answer_keys import (
    ANSWER_KEYS,
    RUBRIC,
    RUBRIC_VERSION,
    A_NO_VERIFIABLE_CLAIMS,
    CHAR_LIMIT,
    VENDOR_NAMES,
    SCORE_UNIQUE_KEY,
    ANSWER_UNIQUE_KEY,
    PRIMARY_METRICS,
)

BASE = Path(__file__).resolve().parent

RESP_DIRS = {
    BASE / "responses_v3": None,
    BASE / "responses_luna_v2": "luna",
    BASE / "responses_gemini_v2": "gemini",
}

VERIFIED = BASE / "verified_commands.json"
SCORES = BASE / "scores.csv"
AXES = ["A", "B", "C", "D", "E"]
ASK_COMMANDS = False

MODELS = [
    "llama3.1:8b",
    "qwen3:8b",
    "gemma3:12b",
    "gemma3:4b",
    "luna",
    "gemini",
]

VERDICT_MARK = {
    "ok": "✔",
    "wrong": "✘",
    "partial": "△",
    "othervendor": "⇄",
    "mixed": "±",
    "unknown": "?",
}

FIELDS = [
    "session", "model", "qid", "run", "axis", "score", "reason",
    "risky_flag", "over_limit", "repeat_flag", "excluded_flag",
    "contradicted_flag", "facts_flag", "unverified_flag",
    "vendor_mix_flag", "confirmed_error_flag",
    "rubric", "scored_at",
]

FLAG_MARKS = [
    ("risky_flag", "R"),
    ("over_limit", "L"),
    ("repeat_flag", "X"),
    ("excluded_flag", "E"),
    ("contradicted_flag", "C"),
    ("facts_flag", "F"),
    ("unverified_flag", "U"),
    ("vendor_mix_flag", "V"),
]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def parse_name(path, default_model=None):
    name = path.stem
    qid = re.search(r"q\d{2}", name)
    session = re.search(r"\d{4}-\d{4}", name)
    run = re.search(r"run[_-]?(\d+)", name)

    model = None
    for m in sorted(MODELS, key=len, reverse=True):
        if norm(m) in norm(name):
            model = m
            break
    model = model or default_model

    if not (qid and model):
        return None

    return {
        "path": path,
        "qid": qid.group(0),
        "model": model,
        "session": session.group(0) if session else "-",
        "run": run.group(1) if run else "1",
    }


def load_allowed(csv_arg):
    if csv_arg.lower() == "none":
        return None

    path = Path(csv_arg)
    if not path.is_absolute():
        path = BASE / path
    if not path.exists():
        sys.exit(f"CSV를 찾지 못함: {path}\n필터 없이 보려면 --csv none")

    allowed = set()
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            rel = (row.get("원문경로") or "").strip()
            if rel and row.get("상태", "정상") == "정상":
                allowed.add((BASE / rel).resolve())

    print(f"[필터] {path.name} 기준 응답 {len(allowed)}건")
    return allowed


def find_responses(questions, sessions, models, allowed=None):
    items = []
    paths = []
    for d, default_model in RESP_DIRS.items():
        if d.exists():
            paths.extend((p, default_model) for p in sorted(d.rglob("*")))

    for p, default_model in paths:
        if not p.is_file() or p.suffix.lower() not in (".txt", ".md"):
            continue
        if allowed is not None and p.resolve() not in allowed:
            continue

        info = parse_name(p, default_model)
        if not info:
            continue
        if questions and info["qid"] not in questions:
            continue
        if sessions and info["session"] not in sessions:
            continue
        if models and info["model"] not in models:
            continue

        info["text"] = p.read_text(encoding="utf-8", errors="replace")
        items.append(info)
    return items


CMD_PREFIX = r"(?:show|diagnose|diag|get|execute|config|set|debug|clear)\b"
CMD_RE = re.compile(
    r"`([^`\n]{2,120})`|^\s*(?:[-*]|\d+\.)?\s*(" + CMD_PREFIX + r"[^\n]{0,120})$",
    re.M,
)


def extract_commands(text):
    found = set()
    for a, b in CMD_RE.findall(text):
        c = (a or b).strip().rstrip(".,")
        if a and not re.match(CMD_PREFIX, c):
            if not c[:1].islower():
                continue
            if " " not in c and not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+", c):
                continue
        found.add(c)
    return sorted(found)


def entries_of(value):
    return value if isinstance(value, list) else [value]


def entry_vendor(entry):
    return entry.get("vendor") or "any"


def load_verified():
    if not VERIFIED.exists():
        return {}
    data = json.loads(VERIFIED.read_text(encoding="utf-8"))
    for pat, value in data.items():
        for e in entries_of(value):
            v = entry_vendor(e)
            if v not in VENDOR_NAMES:
                print(f"  ⚠ verified_commands.json '{pat}': 알 수 없는 vendor '{v}'")
    return data


def save_verified(data):
    VERIFIED.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add_entry(verified, pattern, entry):
    cur = verified.get(pattern)
    if cur is None:
        verified[pattern] = entry
        return
    ents = [e for e in entries_of(cur) if entry_vendor(e) != entry_vendor(entry)]
    ents.append(entry)
    verified[pattern] = ents[0] if len(ents) == 1 else ents


def in_scope(entry, vendors):
    v = entry_vendor(entry)
    return v == "any" or not vendors or v in vendors


def classify(cmd, verified, vendors=None):
    other = None
    for pat in sorted(verified, key=len, reverse=True):
        if pat not in cmd:
            continue
        ents = entries_of(verified[pat])
        scoped = [e for e in ents if in_scope(e, vendors)]
        if scoped:
            verdicts = {e["verdict"] for e in scoped}
            verdict = verdicts.pop() if len(verdicts) == 1 else "mixed"
            label = "/".join(sorted({entry_vendor(e) for e in scoped}))
            return verdict, pat, label
        if other is None:
            other = (pat, "/".join(sorted({entry_vendor(e) for e in ents})))
    if other:
        return "othervendor", other[0], other[1]
    return "unknown", None, ""


def foreign_letters(text):
    counts = Counter()
    samples = {}
    for ch in text:
        if not ch.isalpha() or ch.isascii():
            continue
        name = unicodedata.name(ch, "")
        if name.startswith(("HANGUL", "LATIN")):
            continue
        script = "한자" if name.startswith("CJK") else (name.split()[0] if name else "알 수 없음")
        counts[script] += 1
        if len(samples.get(script, "")) < 8 and ch not in samples.get(script, ""):
            samples[script] = samples.get(script, "") + ch
    return {k: (n, samples[k]) for k, n in counts.most_common()}


def keyword_lines(text, groups):
    hits = []
    lines = text.splitlines()
    for g in groups:
        for i, line in enumerate(lines, 1):
            if any(k in line for k in g["keywords"]):
                hits.append((g["id"], i, line.strip()[:120]))
    return hits


def auto_report(item, verified):
    text = item["text"]
    key = ANSWER_KEYS.get(item["qid"], {})
    vendors = key.get("vendors") or []
    cmds = [(c, *classify(c, verified, vendors)) for c in extract_commands(text)]

    lines = [line.strip() for line in text.splitlines() if len(line.strip()) > 10]
    top_line, top_count = ("", 0)
    if lines:
        top_line, top_count = Counter(lines).most_common(1)[0]

    facts = keyword_lines(text, key.get("facts_wrong", []))
    checks = keyword_lines(text, key.get("facts_check", []))
    vendor_mix = any(v in ("othervendor", "mixed") for _, v, _, _ in cmds)
    confirmed_error = bool(facts) or any(v in ("wrong", "partial", "othervendor", "mixed") for _, v, _, _ in cmds)

    return {
        "chars": len(text),
        "over_limit": len(text) > CHAR_LIMIT,
        "vendors": vendors,
        "commands": cmds,
        "excluded": keyword_lines(text, key.get("excluded", [])),
        "contradicted": keyword_lines(text, key.get("contradicted", [])),
        "risky": keyword_lines(text, key.get("risky", [])),
        "facts": facts,
        "check": checks,
        "foreign": foreign_letters(text),
        "repeat": (top_count, top_line[:80]) if top_count >= 5 else None,
        "vendor_mix": vendor_mix,
        "confirmed_error": confirmed_error,
    }


def print_report(r, axis=None):
    show = lambda ax: axis is None or axis == ax
    print(f"  글자수 {r['chars']:,}" + ("  ⚠ 3000자 초과" if r["over_limit"] else ""))

    if show("A"):
        multi = len(r["vendors"]) > 1
        print(f"  명령어 {len(r['commands'])}개  (문항 장비: {'/'.join(r['vendors']) or '미지정'})")
        for c, verdict, pat, vendor in r["commands"]:
            line = f"    {VERDICT_MARK.get(verdict, '?')} {c}"
            if pat and pat != c:
                line += f"   (← {pat})"
            if verdict == "othervendor":
                line += f"   다른 장비 명령 [{vendor}]"
            elif verdict == "mixed":
                line += f"   장비별 판정 다름 [{vendor}]"
            elif multi and vendor:
                line += f"   [{vendor}]"
            print(line)

        for gid, ln, line in r["facts"]:
            print(f"  [틀린 사실:{gid}] {ln}행: {line}")
        for gid, ln, line in r["check"]:
            print(f"  [확인 필요 사실:{gid}] {ln}행: {line}")

        if not r["commands"] and not r["facts"] and not r["check"]:
            if A_NO_VERIFIABLE_CLAIMS is None:
                print("    검증 가능한 주장 후보 없음 → A축 N/A 검토")
            else:
                print(f"    검증 가능한 주장 후보 없음 → 설정값 {A_NO_VERIFIABLE_CLAIMS}")

    if show("D"):
        for title, key in (("배제 조치 언급", "excluded"), ("단서와 안 맞는 원인", "contradicted")):
            for gid, ln, line in r[key]:
                note = "  (상황 설명일 수 있음)" if key == "excluded" and "정상" in line else ""
                print(f"  [{title}:{gid}] {ln}행: {line}{note}")

    for gid, ln, line in r["risky"]:
        print(f"  [위험 조치:{gid}] {ln}행: {line}")

    if show("E") or show("C"):
        for script, (n, sample) in r["foreign"].items():
            print(f"  ⚠ 외국 문자 혼입: {script} {n}자 ({sample})")
        if r["repeat"]:
            print(f"  ⚠ 같은 줄 {r['repeat'][0]}회 반복: {r['repeat'][1]}")


def normalize_row(row):
    return {field: row.get(field, "") for field in FIELDS}


def load_scores():
    if not SCORES.exists() or SCORES.stat().st_size == 0:
        return []
    with SCORES.open(encoding="utf-8-sig", newline="") as f:
        return [normalize_row(r) for r in csv.DictReader(f)]


def score_key(row):
    return tuple(str(row.get(k, "")) for k in SCORE_UNIQUE_KEY)


def answer_key(row):
    return tuple(str(row.get(k, "")) for k in ANSWER_UNIQUE_KEY)


def write_scores(rows):
    tmp = SCORES.with_suffix(SCORES.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(normalize_row(r) for r in rows)
    tmp.replace(SCORES)


def upsert_score(row):
    """SCORE_UNIQUE_KEY가 같으면 교체하고, 없으면 추가한다."""
    rows = load_scores()
    key = score_key(row)
    replaced = False
    out = []
    for old in rows:
        if score_key(old) == key:
            if not replaced:
                out.append(normalize_row(row))
                replaced = True
            # 과거 중복 행이 이미 있으면 함께 제거한다.
        else:
            out.append(old)
    if not replaced:
        out.append(normalize_row(row))
    write_scores(out)
    return replaced


def done_keys(rows):
    return {score_key(r) for r in rows if r.get("rubric") == RUBRIC_VERSION}


def safe_input(prompt):
    try:
        return input(prompt)
    except EOFError:
        return "q"


def ask_vendor(vendors):
    if vendors and len(vendors) == 1:
        return vendors[0]
    choices = list(vendors or []) + ["any"]
    while True:
        v = safe_input(f"      장비 [{' / '.join(choices)}]: ").strip().lower()
        if v in choices or (not vendors and v in VENDOR_NAMES):
            return v


def ask_unknown_commands(report, verified):
    changed = False
    for c, verdict, _, _ in report["commands"]:
        if verdict != "unknown":
            continue
        ans = safe_input(
            f"    미등록 명령 '{c}' 판정 [o=ok / x=wrong / p=partial / Enter=건너뜀]: "
        ).strip().lower()
        if ans not in ("o", "x", "p"):
            continue
        pattern = safe_input("      등록할 패턴 (Enter=그대로): ").strip() or c
        vendor = ask_vendor(report["vendors"])
        source = safe_input("      출처 (문서명 > 항목): ").strip()
        add_entry(
            verified,
            pattern,
            {
                "verdict": {"o": "ok", "x": "wrong", "p": "partial"}[ans],
                "vendor": vendor,
                "source": source,
                "checked_at": datetime.now().strftime("%Y-%m-%d"),
            },
        )
        changed = True

    if changed:
        save_verified(verified)
        print("    → verified_commands.json 저장됨")
    return changed


def ask_score(axis):
    while True:
        extra = ", n=N/A" if axis == "A" else ""
        s = safe_input(f"  {axis} 점수 0~3{extra} (s=건너뜀, q=종료): ").strip().lower()
        if s in ("s", "q"):
            return s, ""
        if axis == "A" and s in ("n", "na", "n/a"):
            reason = ""
            while not reason:
                reason = safe_input("  N/A 근거 한 줄: ").strip()
            return "N/A", reason
        if s in ("0", "1", "2", "3"):
            reason = ""
            while not reason:
                reason = safe_input("  근거 한 줄: ").strip()
            return s, reason


def make_score_row(it, axis, score, reason, report):
    return {
        "session": it["session"],
        "model": it["model"],
        "qid": it["qid"],
        "run": it["run"],
        "axis": axis,
        "score": score,
        "reason": reason,
        "risky_flag": "Y" if report["risky"] else "",
        "over_limit": "Y" if report["over_limit"] else "",
        "repeat_flag": "Y" if report["repeat"] else "",
        "excluded_flag": "Y" if report["excluded"] else "",
        "contradicted_flag": "Y" if report["contradicted"] else "",
        "facts_flag": "Y" if report["facts"] else "",
        "unverified_flag": "Y" if report["check"] else "",
        "vendor_mix_flag": "Y" if report["vendor_mix"] else "",
        "confirmed_error_flag": "Y" if report["confirmed_error"] else "",
        "rubric": RUBRIC_VERSION,
        "scored_at": datetime.now().isoformat(timespec="seconds"),
    }


def score_axis(items, axis, seed, redo=False):
    verified = load_verified()
    done = set() if redo else done_keys(load_scores())
    todo = [
        it for it in items
        if (it["session"], it["model"], it["qid"], it["run"], axis) not in done
    ]
    random.Random(seed).shuffle(todo)

    name, guide = RUBRIC[axis]
    print(f"\n=== {axis}축 {name} / 남은 응답 {len(todo)}건 ===\n기준: {guide}\n")

    for n, it in enumerate(todo, 1):
        print("=" * 70)
        anon = zlib.crc32(it["path"].name.encode()) % 1000
        print(f"[{n}/{len(todo)}] {it['qid']} / 응답 #{anon:03d}")
        print("-" * 70)
        print(it["text"])
        print("-" * 70)

        report = auto_report(it, verified)
        print_report(report, axis)

        if axis == "A" and ASK_COMMANDS and ask_unknown_commands(report, verified):
            report = auto_report(it, verified)
            print_report(report, "A")

        s, reason = ask_score(axis)
        if s == "q":
            break
        if s == "s":
            continue

        replaced = upsert_score(make_score_row(it, axis, s, reason, report))
        print("  → 기존 행 교체" if replaced else "  → 새 행 저장")

    print("\n저장 위치:", SCORES)


def parse_numeric_score(value):
    s = str(value).strip()
    if s.upper() in ("N/A", "NA", "N"):
        return None
    try:
        v = int(s)
    except (TypeError, ValueError):
        return None
    return v if 0 <= v <= 3 else None


def latest_rows(sessions=None):
    rows = [r for r in load_scores() if r.get("rubric") == RUBRIC_VERSION]
    if sessions:
        rows = [r for r in rows if r.get("session") in sessions]
    latest = {}
    for r in rows:
        latest[score_key(r)] = r
    return latest


def response_records(latest):
    """축별 행을 응답 단위(session/model/qid/run)로 묶는다."""
    records = {}
    for _, r in latest.items():
        k = answer_key(r)
        rec = records.setdefault(k, {"axes": {}, "flags": set(), "row": r})
        rec["axes"][r["axis"]] = r["score"]
        for col, _ in FLAG_MARKS:
            if r.get(col) == "Y":
                rec["flags"].add(col)
        if r.get("confirmed_error_flag") == "Y":
            rec["flags"].add("confirmed_error_flag")
    return records


def pct(n, d):
    return 100.0 * n / d if d else 0.0


def print_primary_metrics(records):
    print("\n[주 지표 / PRIMARY_METRICS]")
    print("  응답 단위: session + model + qid + run")

    by_model = {}
    for (_, model, _, _), rec in records.items():
        by_model.setdefault(model, []).append(rec)

    requested = list(PRIMARY_METRICS)
    for model in sorted(by_model):
        rs = by_model[model]
        n = len(rs)
        confirmed = sum("confirmed_error_flag" in r["flags"] for r in rs)
        vendor_mix = sum("vendor_mix_flag" in r["flags"] for r in rs)
        unverified = sum("unverified_flag" in r["flags"] for r in rs)

        a_vals = [parse_numeric_score(r["axes"].get("A")) for r in rs]
        a_vals = [v for v in a_vals if v is not None]
        b_vals = [parse_numeric_score(r["axes"].get("B")) for r in rs]
        b_vals = [v for v in b_vals if v is not None]

        values = {
            "confirmed_error_response_rate": f"{pct(confirmed, n):.1f}% ({confirmed}/{n})",
            "vendor_mix_response_rate": f"{pct(vendor_mix, n):.1f}% ({vendor_mix}/{n})",
            "unverified_claim_response_rate": f"{pct(unverified, n):.1f}% ({unverified}/{n})",
            "axis_a_mean": f"{sum(a_vals)/len(a_vals):.2f} (n={len(a_vals)}, N/A 제외)" if a_vals else "-",
            "axis_b_mean": f"{sum(b_vals)/len(b_vals):.2f} (n={len(b_vals)})" if b_vals else "-",
        }

        print(f"\n  {model}")
        for metric in requested:
            print(f"    {metric:<32} {values.get(metric, '미구현 지표명')}")


def summary(sessions=None):
    latest = latest_rows(sessions)
    if not latest:
        print(f"채점 기록 없음 ({SCORES.name})")
        return

    records = response_records(latest)
    print_primary_metrics(records)

    runs = {}
    flags = {}
    for (session, model, qid, run), rec in records.items():
        vals = {}
        for axis, raw in rec["axes"].items():
            vals[axis] = parse_numeric_score(raw)
        runs.setdefault((qid, model), {})[(session, run)] = vals
        flags.setdefault((qid, model), set()).update(rec["flags"])

    qids = sorted({q for q, _ in runs})
    models = sorted({m for _, m in runs})
    W = 22

    print(f"\n[문항별 참고 총점] 채점표 {RUBRIC_VERSION} / {SCORES.name}")
    print("  숫자 A~E 5축이 모두 완료된 회차만 15점 총점을 계산")
    print("  A=N/A 회차는 총점에서 제외하고 주 지표/축별 평균에서 별도 처리")
    print("  표기: 평균(최소~최대)n완료회차 / * 미완료 / ! A=0 / R위험 L길이 X반복 E배제 C모순 F사실 U미확인 V벤더")
    print("문항  " + "".join(f"{m:>{W}}" for m in models))

    model_totals = {m: [] for m in models}
    for q in qids:
        cells = []
        for m in models:
            rr = runs.get((q, m))
            if not rr:
                cells.append(f"{'-':>{W}}")
                continue

            totals = []
            incomplete = False
            a_zero = False
            for v in rr.values():
                if v.get("A") == 0:
                    a_zero = True
                if all(a in v and v[a] is not None for a in AXES):
                    totals.append(sum(v[a] for a in AXES))
                else:
                    incomplete = True

            model_totals[m].extend(totals)
            mark = "*" if incomplete else ""
            if a_zero:
                mark += "!"
            for col, symbol in FLAG_MARKS:
                if col in flags.get((q, m), set()):
                    mark += symbol

            if totals:
                avg = sum(totals) / len(totals)
                cell = f"{avg:.1f}({min(totals)}~{max(totals)})n{len(totals)}{mark}"
            else:
                cell = f"-{mark}"
            cells.append(f"{cell:>{W}}")
        print(f"{q:<6}" + "".join(cells))

    print("\n[모델 전체 참고 평균 총점] (숫자 5축 완료 회차만)")
    for m in models:
        vals = model_totals[m]
        print(f"  {m:<14} " + (f"{sum(vals)/len(vals):.2f}  (n={len(vals)})" if vals else "-"))

    print("\n[축별 평균] (N/A 제외)")
    print("축    " + "".join(f"{m:>{W}}" for m in models))
    for axis in AXES:
        cells = []
        for m in models:
            vals = []
            for (q, mm), rr in runs.items():
                if mm != m:
                    continue
                for v in rr.values():
                    if axis in v and v[axis] is not None:
                        vals.append(v[axis])
            cells.append(f"{sum(vals)/len(vals):>{W}.2f}" if vals else f"{'-':>{W}}")
        print(f"{axis:<6}" + "".join(cells))


def validate_answer_keys_interface():
    """07과 answer_keys.py v2.2의 핵심 인터페이스를 실행 전에 확인한다."""
    if tuple(SCORE_UNIQUE_KEY) != ("session", "model", "qid", "run", "axis"):
        sys.exit(f"예상하지 못한 SCORE_UNIQUE_KEY: {SCORE_UNIQUE_KEY}")
    if tuple(ANSWER_UNIQUE_KEY) != ("session", "model", "qid", "run"):
        sys.exit(f"예상하지 못한 ANSWER_UNIQUE_KEY: {ANSWER_UNIQUE_KEY}")

    for q, key in ANSWER_KEYS.items():
        bad = set(key.get("vendors", [])) - VENDOR_NAMES
        if bad:
            print(f"  ⚠ answer_keys.py {q}: 알 수 없는 vendors {sorted(bad)}")


def main():
    global SCORES, ASK_COMMANDS

    ap = argparse.ArgumentParser()
    ap.add_argument("--axis", choices=AXES)
    ap.add_argument("--questions", nargs="*")
    ap.add_argument("--sessions", nargs="*")
    ap.add_argument("--models", nargs="*")
    ap.add_argument(
        "--csv",
        default="benchmark_local_v3.csv",
        help="이 CSV의 원문경로에 있는 정상 응답만 대상 (none=필터 해제)",
    )
    ap.add_argument("--scores", default="scores.csv", help="통합 점수 저장 파일")
    ap.add_argument("--seed", type=int, default=7, help="응답 순서 섞기용")
    ap.add_argument("--list", action="store_true", help="찾은 응답 파일 목록")
    ap.add_argument("--check", action="store_true", help="자동 표시만 출력")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument(
        "--redo",
        action="store_true",
        help="이미 채점한 항목도 다시 채점하고 SCORE_UNIQUE_KEY 기준으로 기존 행 교체",
    )
    ap.add_argument(
        "--ask-commands",
        action="store_true",
        help="A축 채점 중 미등록 명령어 판정을 물어봄",
    )
    args = ap.parse_args()

    ASK_COMMANDS = args.ask_commands
    SCORES = Path(args.scores)
    if not SCORES.is_absolute():
        SCORES = BASE / SCORES

    validate_answer_keys_interface()

    if args.summary:
        summary(args.sessions)
        return

    allowed = load_allowed(args.csv)
    items = find_responses(args.questions, args.sessions, args.models, allowed)
    if not items:
        print(
            "응답 파일을 찾지 못함: "
            f"{[str(d) for d in RESP_DIRS]}\n"
            "파일명 규칙이 다르면 parse_name()을 확인하세요."
        )
        return

    if args.list:
        for it in items:
            print(
                f"{it['session']:>10}  {it['model']:<14} "
                f"{it['qid']}  run{it['run']}  {it['path'].name}"
            )
        by_model = Counter(it["model"] for it in items)
        print(f"총 {len(items)}건  " + " / ".join(f"{m} {n}" for m, n in sorted(by_model.items())))
        return

    if args.check:
        verified = load_verified()
        for it in items:
            print("=" * 70)
            print(f"{it['session']} / {it['model']} / {it['qid']} / run{it['run']}")
            print_report(auto_report(it, verified))
        return

    if not args.axis:
        ap.error("--axis 를 지정하세요 (또는 --list / --check / --summary)")

    score_axis(items, args.axis, args.seed, args.redo)


if __name__ == "__main__":
    main()