# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2"]
# ///
"""Revised 2026 projection (5 Nov): counted ballots from the official Election Summary Report, plus the
early, absentee and questioned ballots still to count.

Counted == CVR final round + the batch in the Election Summary Report but not in the CVR (rural
election-day precincts, read from each race's own first choices with election-day rates, via
cross_race.py). Remaining ballots vote like counted CVR ballots of the same type (report_projection.json
counts). Sensitivity: the shift in the remaining ballots' two-way margin that would flip each race.

Sign convention: D positive (Hill - Begich, Peltola - Sullivan).

Usage: uv run revised.py [RELEASE_JSON]   (default release_20261104_1309.json). Writes revised_projection.json.
"""
import json
import sys
from pathlib import Path

import pandas as pd

import cross_race as cr

HERE = Path(__file__).parent
REL = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "release_20261104_1309.json"
RACES = {"House": ("house", "HF", "Hill", "Begich"), "Senate": ("senate", "SF", "Peltola", "Sullivan")}


def main() -> None:
    m = cr.load()
    R = json.loads((HERE / "report_projection.json").read_text())
    rel = json.loads(REL.read_text())
    out = {"release": REL.name, "early_rem": R["early_rem"], "abs_rem": R["abs_rem"], "unreturned": R["unreturned"],
           "questioned": R["questioned_assumed"], "races": {}}
    for race, (key, tgt, dem, rep) in RACES.items():
        net0, two0 = int(m[tgt + "_net"].sum()), int(m[tgt + "_two"].sum())
        # batch: release minus CVR first choices, own race, election-day rates
        ed = m[m.vt == "Election Day"]
        totals = rel[key]["Election Day"]
        batch = (pd.Series(totals, dtype=float) - cr.choices(ed, cr.SOURCES[key]).reindex(list(totals)).fillna(0)).clip(lower=0)
        bnet, btwo = cr.predict(batch, cr.rates(ed, cr.SOURCES[key]), tgt)
        cnet, ctwo = net0 + bnet, two0 + btwo
        # remaining ballots, like counted CVR ballots of the same type
        rate = lambda g: (g[tgt + "_net"].mean(), g[tgt + "_two"].mean())
        by = {vt: rate(g) for vt, g in m.groupby("vt")}
        rows = []
        for u in (0, 0.4, 1.0):
            parts = [(R["early_rem"], by["Early Voting"]), (R["abs_rem"], by["Absentee"]), (R["unreturned"] * u, by["Absentee"]),
                     (R["questioned_assumed"], rate(m))]
            rnet = sum(n * a for n, (a, b) in parts)
            rtwo = sum(n * b for n, (a, b) in parts)
            tnet, ttwo = cnet + rnet, ctwo + rtwo
            rows.append({"unreturned_pct": int(u * 100), "remaining_net": round(rnet), "remaining_two": round(rtwo),
                         "remaining_margin_pct": round(rnet / rtwo * 100, 2), "total_net": round(tnet),
                         "total_pct_dem": round((ttwo + tnet) / 2 / ttwo * 100, 2),
                         "flip_shift_pts": round(-tnet / rtwo * 100, 2)})
        out["races"][race] = {"dem": dem, "rep": rep, "cvr_net": net0, "batch_first_choices": int(batch.sum()),
                              "batch_shares": {k: round(v / batch.sum() * 100, 1) for k, v in batch.items()},
                              "batch_net": round(bnet), "batch_margin_pct": round(bnet / btwo * 100, 2),
                              "counted_net": round(cnet), "scenarios": rows}
        print(f"== {race} ({dem} - {rep})  CVR {net0:+,}  batch {bnet:+,.0f} ({bnet/btwo*100:+.2f} on {int(batch.sum()):,} first choices)  counted {cnet:+,.0f}")
        for r in rows:
            print(f"   unreturned {r['unreturned_pct']:>3}%: remaining {r['remaining_net']:+,} ({r['remaining_margin_pct']:+.2f} on {r['remaining_two']:,}) "
                  f"-> total {r['total_net']:+,}, {dem} {r['total_pct_dem']:.2f}%; flips if remaining shift {r['flip_shift_pts']:+.2f} pts")
    (HERE / "revised_projection.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
