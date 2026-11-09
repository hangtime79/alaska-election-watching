# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2"]
# ///
"""Who were the Senate's minor Republican-side voters (Heikes, Sullivan Jr.)? Same-ballot crosstabs, 2026.

For each Senate first-choice group: the next Senate ranking, the Senate final round, House first choice,
governor first choice, legislative first choice (any contested D-and-R legislative contest), vote type and
rural share. A decoy vote (meant Dan Sullivan) should look like Sullivan's voters and rank him next; a
deliberate vote should not. Ballots marking both Sullivans at rank 1 are shown as their own group.

Usage: uv run senate_minor.py   (needs crossover_2026.csv, legislative_2026.csv, the 2026 Senate and
governor CVRs). Writes senate_minor.json.
"""
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
SEN = HERE / "2026-11-05_00-56_rctab_cvr-senate.csv"
GOV = HERE / "2026-11-05_14-36_rctab_cvr-2026-governor.csv"
SHORT = {"Sullivan, Dan S.": "Sullivan", "Peltola, Mary": "Peltola", "Heikes, Gerald L.": "Heikes",
         "Sullivan, Daniel J. Jr.": "Sullivan Jr.", "Write-in": "Write-in"}
RANKS = [f"Rank {i}" for i in range(1, 6)]


def first_and_next(row) -> tuple[str, str]:
    seen = []
    for v in row:
        if v == "undervote":
            continue
        if "\n" in v:
            names = sorted(SHORT.get(n, n) for n in v.split("\n"))
            seen.append("both Sullivans" if names == ["Sullivan", "Sullivan Jr."] else "overvote")
            if len(seen) == 1:
                continue
            break
        n = SHORT.get(v, v)
        if not seen or n != seen[-1]:
            seen.append(n)
        if len(seen) == 2:
            break
    return (seen[0] if seen else "blank", seen[1] if len(seen) > 1 else "none")


def pct(s: pd.Series, order: list[str]) -> dict:
    n = s.value_counts(normalize=True) * 100
    return {k: round(float(n.get(k, 0)), 1) for k in order}


def main() -> None:
    pd.set_option("display.width", 250)
    s = pd.read_csv(SEN, dtype=str, keep_default_na=False)
    fn = [first_and_next(r) for r in s[RANKS].itertuples(index=False)]
    s["first"], s["next"] = [a for a, _ in fn], [b for _, b in fn]
    x = pd.read_csv(HERE / "crossover_2026.csv", dtype=str, keep_default_na=False)
    g = pd.read_csv(GOV, usecols=["RCTab CVR Id", "Rank 1"], dtype=str, keep_default_na=False)
    g["gov"] = g["Rank 1"].map(lambda v: "Kreiss-Tomkins" if v.startswith("Kreiss") else
                               ("Republican" if v.startswith(("Wilson", "Bronson", "Taylor")) else "other/blank"))
    L = pd.read_csv(HERE / "legislative_2026.csv", dtype=str)
    L = L[L.contested == "True"].drop_duplicates("RCTab CVR Id")  # one legislative vote per ballot (House contest first)
    m = s[["RCTab CVR Id", "first", "next"]].merge(x[["RCTab CVR Id", "vt", "dist", "H1", "SF"]], on="RCTab CVR Id") \
        .merge(g[["RCTab CVR Id", "gov"]], on="RCTab CVR Id", how="left").merge(L[["RCTab CVR Id", "leg_first"]], on="RCTab CVR Id", how="left")
    m["H"] = m.H1.where(m.H1.isin(["Begich", "Hill", "Hafner", "McDermott"]), "other/blank")
    m["leg"] = m.leg_first.fillna("not contested").replace({"D": "D", "R": "R"})
    m.loc[~m.leg.isin(["D", "R", "not contested"]), "leg"] = "other/blank"
    m["rural"] = m.dist.astype(float).isin([37, 38, 39, 40])
    m["eday"] = m.vt == "Election Day"
    print(f"Senate ballots {len(s):,}, matched {len(m):,}")

    groups = ["Sullivan", "Peltola", "Heikes", "Sullivan Jr.", "both Sullivans", "Write-in"]
    out = {}
    rows = []
    for gname in groups:
        d = m[m["first"] == gname]
        r = {"group": gname, "ballots": len(d)}
        r |= {f"next {k}": v for k, v in pct(d["next"], ["Sullivan", "Peltola", "Heikes", "Sullivan Jr.", "none"]).items()}
        r |= {f"final {k}": v for k, v in pct(d.SF, ["Sullivan", "Peltola"]).items()}
        r |= {f"House {k}": v for k, v in pct(d.H, ["Begich", "McDermott", "Hill", "Hafner"]).items()}
        r |= {f"gov {k}": v for k, v in pct(d.gov, ["Republican", "Kreiss-Tomkins"]).items()}
        c = d[d.leg.isin(["D", "R"])]
        r["leg ballots"] = len(c)
        r |= {f"leg {k}": v for k, v in pct(c.leg, ["R", "D"]).items()}
        r["election day %"] = round(d.eday.mean() * 100, 1)
        r["rural %"] = round(d.rural.mean() * 100, 1)
        rows.append(r)
    t = pd.DataFrame(rows)
    for cols in (["group", "ballots"] + [c for c in t.columns if c.startswith(("next", "final"))],
                 ["group"] + [c for c in t.columns if c.startswith(("House", "gov"))],
                 ["group", "leg ballots", "leg R", "leg D", "election day %", "rural %"]):
        print("\n" + t[cols].to_string(index=False))
    out["groups"] = rows
    # Sullivan Jr. voters split by what they ranked next
    print("\n== Sullivan Jr. first, by next Senate ranking")
    sub = []
    for nxt, d in m[m["first"] == "Sullivan Jr."].groupby("next"):
        r = {"next": nxt, "ballots": len(d)} | {f"House {k}": v for k, v in pct(d.H, ["Begich", "McDermott", "Hill", "Hafner"]).items()} \
            | {f"gov {k}": v for k, v in pct(d.gov, ["Republican", "Kreiss-Tomkins"]).items()} \
            | {"election day %": round(d.eday.mean() * 100, 1), "rural %": round(d.rural.mean() * 100, 1)}
        sub.append(r)
    print(pd.DataFrame(sub).sort_values("ballots", ascending=False).to_string(index=False))
    out["sullivan_jr_by_next"] = sub
    (HERE / "senate_minor.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
