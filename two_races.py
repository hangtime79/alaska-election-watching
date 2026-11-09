# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2"]
# ///
"""Project the House and Senate final rounds side by side from crossover_2026.csv + report_projection.json.

Scenarios for the uncounted early/absentee ballots: vote like their type so far; shift like 2024's late
ballots (-6.63 pts in the Republican's final-round share); shift like the post-CVR House batch
(38.8% vs 53.98% => -15.18 pts, applied to both races - the Senate batch rate is NOT measured).
Questioned ballots vote like all counted ballots. Run crossover.py and report_projection.py first.
"""
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
x = pd.read_csv(HERE / "crossover_2026.csv")
R = json.loads((HERE / "report_projection.json").read_text())
SHIFT = {"type": None, "2024 late shift": -0.0663, "post-CVR batch shift": R["late_batch_final"] - 0.5398}
for race, col, rep, dem in [("House", "HF", "Begich", "Hill"), ("Senate", "SF", "Sullivan", "Peltola")]:
    rate = {vt: ((g[col] == rep).mean(), (g[col] == dem).mean()) for vt, g in list(x.groupby("vt")) + [("All", x)]}
    r0, d0 = (x[col] == rep).sum(), (x[col] == dem).sum()
    now, per = r0 / (r0 + d0), (r0 + d0) / len(x)
    print(f"== {race}: {rep} {r0:,} vs {dem} {d0:,}  {rep} {now*100:.2f}%  margin {r0-d0:,}")
    for name, sh in SHIFT.items():
        cells = []
        for u in (0, 0.4, 1.0):
            rv, dv = float(r0), float(d0)
            for vt, n in [("Early Voting", R["early_rem"]), ("Absentee", R["abs_rem"]), ("Absentee", R["unreturned"] * u)]:
                a, b = rate[vt] if sh is None else (per * (now + sh), per * (1 - now - sh))
                rv, dv = rv + n * a, dv + n * b
            a, b = rate["All"]
            rv, dv = rv + R["questioned_assumed"] * a, dv + R["questioned_assumed"] * b
            cells.append(f"unreturned {int(u*100)}%: {rep} {rv/(rv+dv)*100:.2f}% margin {rv-dv:,.0f}")
        print(f"   {name:22s} " + " | ".join(cells))
