# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2"]
# ///
"""Project the final result by vote type, using 2024's final vote-type mix.

Method (scenario A):
  1. Election Day, Early Voting and judicial-split ballots stay at what has been counted so far.
  2. Absentee + Question + Overseas make up the same share of the final total as in 2024 final.
  3. Ballots still to come in each type vote like that type has voted so far.
     Question ballots have none counted yet, so they vote like all ballots counted so far
     (in 2024 their round-1 Begich share was close to the overall share).
Scenario B also grows Election Day, Early Voting and judicial-split counts
by 2024's growth from the 10 Nov snapshot to final.

Backtest: runs the same method on the 10 Nov 2024 snapshot and compares with the 2024 final.

Usage: uv run project.py [CVR_2026] [MULTI_2024] [OUT_JSON]
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

import rcv

HERE = Path(__file__).parent
F2026 = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "2026-11-04_23-33_rctab_cvr.csv"
MULTI = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "2026-11-04_23-57_rctab_cvr.csv"
OUT = Path(sys.argv[3]) if len(sys.argv) > 3 else HERE / "projection.json"
ABS_LIKE = ["Absentee", "Question", "Overseas"]
FIXED = ["Election Day", "Early Voting", "Judicial-split"]


def vote_type(loc: str) -> str:
    loc = re.sub(r"\s+", " ", loc).strip()
    if re.match(r"^\d+-\d+ ", loc):
        return "Election Day"
    if "Judicial District" in loc:
        return "Judicial-split"
    if "Overseas" in loc:
        return "Overseas"
    return loc.split(" - ")[-1]


def tally(path: Path, snapshot: str | None) -> dict:
    """Per vote type: ballots, round-1 Begich/active, final-round Begich/opponent."""
    df = pd.read_csv(path, usecols=["Source Filepath", "Precinct Portion", *rcv.RANKS], dtype=str, keep_default_na=False)
    if snapshot:
        df = df[df["Source Filepath"].str.contains(snapshot, regex=False)]
    groups = defaultdict(Counter)
    norm = lambda r: rcv.SKIP if r == "undervote" else (rcv.OVER if "\n" in r else r)
    for loc, *ranks in df[["Precinct Portion", *rcv.RANKS]].itertuples(index=False):
        groups[vote_type(loc)][tuple(norm(r) for r in ranks)] += 1

    allb = Counter()
    for c in groups.values():
        allb.update(c)
    elim: list[str] = []
    while True:
        t = Counter()
        for b, n in allb.items():
            t[rcv.assign(b, set(elim))] += n
        active = {k: v for k, v in t.items() if not k.startswith("inactive")}
        if len(active) <= 2:
            break
        elim.append(min(active, key=active.get))
    opp = next(k for k in active if not k.startswith("Begich"))

    out = {}
    for vt, c in groups.items():
        r1, fin = Counter(), Counter()
        for b, n in c.items():
            r1[rcv.assign(b, set())] += n
            fin[rcv.assign(b, set(elim))] += n
        out[vt] = {
            "ballots": sum(c.values()),
            "r1_begich": r1["Begich, Nick"],
            "r1_active": sum(v for k, v in r1.items() if not k.startswith("inactive")),
            "fin_begich": fin["Begich, Nick"],
            "fin_opp": fin[opp],
        }
    return {"types": out, "opponent": opp.split(",")[0]}


def rate(d: dict, num: str, den: str) -> float:
    return d[num] / d[den] if d[den] else 0.0


def project(now: dict, mix24: dict, growth: dict | None) -> dict:
    T = now["types"]
    blank = {"ballots": 0, "r1_begich": 0, "r1_active": 0, "fin_begich": 0, "fin_opp": 0}
    cur = lambda vt: T.get(vt, blank)
    total = lambda d, k: sum(v[k] for v in d.values())
    overall = {k: total(T, k) for k in blank}

    fixed_now = {vt: cur(vt)["ballots"] for vt in FIXED}
    fixed_final = {vt: round(fixed_now[vt] * (growth[vt] if growth else 1)) for vt in FIXED}
    n_fixed = sum(fixed_final.values())
    tot24 = sum(mix24.values())
    abs_share = sum(mix24[vt] for vt in ABS_LIKE) / tot24
    final_total = n_fixed / (1 - abs_share)
    abs_total = final_total - n_fixed
    abs_final = {vt: abs_total * mix24[vt] / sum(mix24[x] for x in ABS_LIKE) for vt in ABS_LIKE}

    rows, sums = [], Counter()
    for vt in FIXED + ABS_LIKE:
        counted = cur(vt)["ballots"]
        final_n = fixed_final[vt] if vt in FIXED else max(abs_final[vt], counted)
        remaining = final_n - counted
        src = cur(vt) if cur(vt)["ballots"] else overall  # Question: no ballots yet -> overall rates
        r = {
            "r1_active_per_ballot": rate(src, "r1_active", "ballots"),
            "r1_begich": rate(src, "r1_begich", "r1_active"),
            "fin_begich_per_ballot": rate(src, "fin_begich", "ballots"),
            "fin_opp_per_ballot": rate(src, "fin_opp", "ballots"),
        }
        add = {
            "r1_active": remaining * r["r1_active_per_ballot"],
            "r1_begich": remaining * r["r1_active_per_ballot"] * r["r1_begich"],
            "fin_begich": remaining * r["fin_begich_per_ballot"],
            "fin_opp": remaining * r["fin_opp_per_ballot"],
        }
        for k in ["r1_begich", "r1_active", "fin_begich", "fin_opp"]:
            sums[k] += cur(vt)[k] + add[k]
        sums["ballots"] += final_n
        rows.append({
            "type": vt, "counted": counted, "final": round(final_n), "remaining": round(remaining),
            "rates_from": vt if cur(vt)["ballots"] else "all counted so far",
            "begich_r1_pct": round(r["r1_begich"] * 100, 1),
            "begich_final_pct": round(r["fin_begich_per_ballot"] / (r["fin_begich_per_ballot"] + r["fin_opp_per_ballot"]) * 100, 1) if r["fin_begich_per_ballot"] else 0,
        })
    return {
        "abs_share_2024": round(abs_share * 100, 2),
        "final_total": round(final_total),
        "rows": rows,
        "r1_pct": round(sums["r1_begich"] / sums["r1_active"] * 100, 2),
        "final_pct": round(sums["fin_begich"] / (sums["fin_begich"] + sums["fin_opp"]) * 100, 2),
        "final_margin": round(sums["fin_begich"] - sums["fin_opp"]),
        "now_r1_pct": round(overall["r1_begich"] / overall["r1_active"] * 100, 2),
        "now_final_pct": round(overall["fin_begich"] / (overall["fin_begich"] + overall["fin_opp"]) * 100, 2),
    }


def main() -> None:
    fin24 = tally(MULTI, "alaska-2024")
    nov10 = tally(MULTI, "20241110")
    now26 = tally(F2026, None)
    mix24 = {vt: fin24["types"].get(vt, {"ballots": 0})["ballots"] for vt in FIXED + ABS_LIKE}
    growth = {vt: fin24["types"][vt]["ballots"] / nov10["types"][vt]["ballots"] for vt in FIXED}
    actual24 = project(fin24, mix24, None)  # projecting the final onto itself = the actual result

    res = {
        "mix24": mix24,
        "growth24": {k: round(v, 3) for k, v in growth.items()},
        "backtest": {"A": project(nov10, mix24, None), "B": project(nov10, mix24, growth),
                     "actual_r1_pct": actual24["now_r1_pct"], "actual_final_pct": actual24["now_final_pct"]},
        "y2026": {"A": project(now26, mix24, None), "B": project(now26, mix24, growth), "opponent": now26["opponent"]},
    }
    OUT.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items()}, indent=1))


if __name__ == "__main__":
    main()
