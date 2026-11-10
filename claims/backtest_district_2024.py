# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2"]
# ///
"""Backtest the district-by-district projection on 2024: run it from the 10 Nov 2024 count.

Run from the repo root: uv run claims/backtest_district_2024.py   (writes backtest_district_2024.json)

The 2024 House race, Peltola against Begich. Ballots counted by the 10 Nov 2024 export give each district's rate
by vote type (final-round net and two-way votes per ballot, Alaska's rules). The ballots counted after 10 Nov, with
2024's final counts per district and type (perfect knowledge of how many arrived, as in project.py's backtest),
take those rates; district_projection.py's borrowing rules fill districts with too few counted ballots of a type.
Election-day ballots counted late (the rural precincts) take the district's own election-day rate, or the
statewide rate where none was counted. Projected against the final CVR, by type: the statewide method (one rate per
type) and the district method. Model B is not tested here: its gaps come from these same 2024 ballots.

Sign convention: D positive (Peltola - Begich).
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, ".")
import district_projection as dp  # noqa: E402
import project  # noqa: E402
import rcv  # noqa: E402

F = Path("2026-11-04_23-57_rctab_cvr.csv")
ELIM = {"Write-in", "Hafner, Eric", "Howe, John Wayne"}
KIND = {"Early Voting": "early", "Absentee": "absentee", "Overseas": "absentee", "Question": "questioned"}


def norm(v):
    return rcv.SKIP if v == "undervote" else (rcv.OVER if "\n" in v else v)


def main():
    df = pd.read_csv(F, usecols=["Source Filepath", "RCTab CVR Id", "Precinct Portion", *rcv.RANKS], dtype=str, keep_default_na=False)
    src = df["Source Filepath"]
    in10 = set(df.loc[src.str.contains("20241110"), "RCTab CVR Id"])
    x = df[src.str.endswith("alaska-2024")].copy()
    fin = [rcv.assign(tuple(norm(v) for v in r), ELIM) for r in x[rcv.RANKS].itertuples(index=False)]
    x["net"] = [1 if f.startswith("Peltola") else -1 if f.startswith("Begich") else 0 for f in fin]
    x["two"] = x.net.abs()
    x["vt"] = x["Precinct Portion"].map(project.vote_type)
    x["dist"] = x["Precinct Portion"].str.extract(r"^(?:House District |District |HD)?(\d+)", expand=False).astype(int)
    x["early"] = x["RCTab CVR Id"].isin(in10)
    a, late = x[x.early], x[~x.early]
    print(f"final {len(x):,}; counted by 10 Nov {len(a):,}; later {len(late):,}; types later {late.vt.value_counts().to_dict()}")
    actual = int(x.net.sum())
    counted = int(a.net.sum())

    # district method
    districts = sorted(x.dist.unique())
    dr = dp.district_rates(a, "net", "two", districts)["rates"]
    edr = a[a.vt == "Election Day"].groupby("dist").agg(n=("net", "size"), net=("net", "mean"), two=("two", "mean"))
    ed_all = (a[a.vt == "Election Day"].net.mean(), a[a.vt == "Election Day"].two.mean())
    allrate = (a.net.mean(), a.two.mean())
    rows = {}
    for (d, vt), g in late.groupby(["dist", "vt"]):
        n = len(g)
        if vt == "Election Day":
            r = (edr.loc[d, "net"], edr.loc[d, "two"]) if d in edr.index and edr.loc[d, "n"] >= dp.MIN else ed_all
        elif vt in KIND:
            r = dr[d][KIND[vt]]
        else:   # judicial-split and anything else: the district's all-ballot rate
            r = dr[d]["questioned"]
        k = vt if vt in ("Election Day", "Early Voting", "Absentee") else "Other"
        rows.setdefault(k, {"n": 0, "district": 0.0, "actual": 0, "statewide": 0.0})
        rows[k]["n"] += n; rows[k]["district"] += n * r[0]; rows[k]["actual"] += int(g.net.sum())
    # statewide method: one rate per type from ballots counted by 10 Nov
    st = {vt: g.net.mean() for vt, g in a.groupby("vt")}
    for (vt), g in late.groupby("vt"):
        k = vt if vt in ("Election Day", "Early Voting", "Absentee") else "Other"
        rows[k]["statewide"] += len(g) * st.get(vt, allrate[0])
    out = {"actual_final": actual, "counted_10nov": counted, "by_type": {}}
    tot_d = tot_s = 0.0
    for k, r in rows.items():
        out["by_type"][k] = {"late_ballots": r["n"], "actual": r["actual"], "district": round(r["district"]), "statewide": round(r["statewide"]),
                             "miss_district": r["actual"] - round(r["district"]), "miss_statewide": r["actual"] - round(r["statewide"])}
        tot_d += r["district"]; tot_s += r["statewide"]
        print(f"{k:13} late {r['n']:6,}  actual {r['actual']:+7,}  district {r['district']:+9,.0f} (miss {r['actual'] - r['district']:+7,.0f})"
              f"  statewide {r['statewide']:+9,.0f} (miss {r['actual'] - r['statewide']:+7,.0f})")
    out["projected_district"] = round(counted + tot_d)
    out["projected_statewide"] = round(counted + tot_s)
    out["miss_district"] = actual - out["projected_district"]
    out["miss_statewide"] = actual - out["projected_statewide"]
    ea = [k for k in ("Early Voting", "Absentee") if k in rows]
    out["miss_early_absentee_district"] = sum(out["by_type"][k]["miss_district"] for k in ea)
    out["miss_early_absentee_statewide"] = sum(out["by_type"][k]["miss_statewide"] for k in ea)
    print(f"counted 10 Nov {counted:+,}; actual {actual:+,}; district {out['projected_district']:+,} (miss {out['miss_district']:+,}); "
          f"statewide {out['projected_statewide']:+,} (miss {out['miss_statewide']:+,})")
    print(f"early + absentee miss: district {out['miss_early_absentee_district']:+,}, statewide {out['miss_early_absentee_statewide']:+,}")
    Path("backtest_district_2024.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
