# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2"]
# ///
"""Walk the district projection from one CVR export to the next: what the newly counted ballots did against what the
previous projection expected of them, and how the forecast for the ballots still to count changed.

Run from the repo root: uv run claims/update_walk.py OLD_HOUSE_CVR [REPORT_HTML] [--old-batch HOUSE SENATE] [--out FILE]
  (writes update_walk.json, or FILE)
  --old-batch: the rural election-day batch (official count, not in the CVR) at the old export. Election-day ballots
  that moved from that batch into the CVR are expected to add what the batch shrank by.

The previous projection is rebuilt from the ballots in OLD_HOUSE_CVR (matched by RCTab CVR Id in crossover_2026.csv,
which holds the current export). So both sides use the same report, rules and batch; only the ballots differ.
  previous total  == previous counted + previous remaining
  new ballots     == ballots in the current CVR not in the old one, by district and type
  expected        == each new ballot at the previous projection's rate for its district and type (Model B adds the
                     2024 late gap to new early and absentee ballots); judicial-split ballots at the early rate,
                     as the previous projection took them off early first
  surprise        == what the new ballots did - expected
  re-forecast     == current remaining - (previous remaining - expected)
  current total   == previous total + surprise + re-forecast
Sign convention: D positive (Hill - Begich, Peltola - Sullivan).
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, ".")
import district_projection as dp  # noqa: E402

import argparse
ap = argparse.ArgumentParser()
ap.add_argument("old"); ap.add_argument("report", nargs="?", default="combined-ballot-report-20261109.html")
ap.add_argument("--old-batch", nargs=2, type=int); ap.add_argument("--out", default="update_walk.json")
A = ap.parse_args()
OLD, REPORT = Path(A.old), Path(A.report)
KIND = {"Early Voting": "early", "Judicial-split": "early", "Absentee": "absentee", "Question": "questioned"}
GAP = {"early": dp.GAP_EARLY, "absentee": dp.GAP_ABS, "questioned": 0.0}


def total(x, rep, counted_batch, u, model):
    rem = dp.remaining(rep, x)
    dr = dp.district_rates(x, "net", "two", rem)
    P = dp.parts(rem, dr["rates"])
    return dp.project(P, int(x.net.sum()) + counted_batch, u, model), dr["rates"]


def main():
    _, rep = dp.parse(REPORT)
    x = pd.read_csv("crossover_2026.csv", dtype=str, keep_default_na=False)
    x["dist"] = x["dist"].astype(int)
    old_ids = set(pd.read_csv(OLD, usecols=["RCTab CVR Id"], dtype=str)["RCTab CVR Id"])
    x["old"] = x["RCTab CVR Id"].isin(old_ids)
    rev = json.loads(Path("revised_projection.json").read_text())
    new = x[~x.old]
    out = {"old_cvr": OLD.name, "old_ballots": int(x.old.sum()), "new_ballots": len(new),
           "new_by_type": new.vt.value_counts().to_dict(), "races": {}}
    print(f"old {x.old.sum():,} ballots, new {len(new):,}: {out['new_by_type']}")
    for race, (col, dem, rp) in dp.RACES.items():
        x["net"] = (x[col] == dem).astype(int) - (x[col] == rp).astype(int)
        x["two"] = x[col].isin([dem, rp]).astype(int)
        batch = rev["races"][race]["batch_net"]
        old_batch = A.old_batch[0 if race == "House" else 1] if A.old_batch else batch
        xo, xn = x[x.old].copy(), x[~x.old]
        actual = int(xn.net.sum())
        rows = []
        for model in ("A", "B"):
            for u in (0, 0.4, 1.0):
                p0, rates0 = total(xo, rep, old_batch, u, model)
                p1, _ = total(x.copy(), rep, batch, u, model)
                exp = 0.0
                by = {}
                for (d, vt), g in xn.groupby(["dist", "vt"]):
                    k = KIND.get(vt)
                    if k is None:
                        continue   # election day / overseas: none new in this export (checked below)
                    r = rates0[d][k]
                    e = len(g) * (r[0] + (r[1] * GAP[k] if model == "B" else 0.0))
                    exp += e
                    b = by.setdefault(vt, {"ballots": 0, "actual": 0, "expected": 0.0})
                    b["ballots"] += len(g); b["actual"] += int(g.net.sum()); b["expected"] += e
                ed = xn[xn.vt == "Election Day"]
                if len(ed):   # moved from the rural batch into the CVR: expected == what the batch shrank by
                    e = old_batch - batch
                    exp += e
                    by["Election Day"] = {"ballots": len(ed), "actual": int(ed.net.sum()), "expected": e}
                other = xn[~xn.vt.isin(list(KIND) + ["Election Day"])]
                surprise = actual - exp
                reforecast = p1["remaining_net"] - (p0["remaining_net"] - (exp - (old_batch - batch)))
                rows.append({"model": model, "unreturned_pct": int(u * 100), "previous_total": p0["total_net"],
                             "new_actual": actual, "new_expected": round(exp), "surprise": round(surprise),
                             "reforecast": round(reforecast), "current_total": p1["total_net"],
                             "previous_remaining": p0["remaining_net"], "current_remaining": p1["remaining_net"],
                             "other_new_ballots": len(other),
                             "by_type": {k: {"ballots": v["ballots"], "actual": v["actual"], "expected": round(v["expected"]),
                                             "surprise": round(v["actual"] - v["expected"])} for k, v in by.items()}})
                r_ = rows[-1]
                print(f"{race} {model} {r_['unreturned_pct']:>3}%: previous {r_['previous_total']:+,}  new ballots {actual:+,} vs expected "
                      f"{r_['new_expected']:+,} (surprise {r_['surprise']:+,})  re-forecast {r_['reforecast']:+,}  -> {r_['current_total']:+,}")
        out["races"][race] = rows
        for k, v in rows[1]["by_type"].items():
            print(f"   {k:14} {v['ballots']:6,}  actual {v['actual']:+6,}  expected {v['expected']:+7,}  surprise {v['surprise']:+6,}")
    Path(A.out).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
