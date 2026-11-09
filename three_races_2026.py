# /// script
# dependencies = ["pandas"]
# ///
"""Begich, Sullivan and the governor Republicans against the generic Republican legislator, 2026, same ballots.

Ballots: the urban clean legislative contests (one D, one R; legislative_2026.csv), matched across the
House, Senate and governor CVRs on RCTab CVR Id. For each race, two readings:
  - first choice (each side's candidates summed)
  - head to head: the ballot counts for whichever of the two named sides it ranks higher, everyone else
    eliminated (Alaska rules as in rcv.assign: overvote or two skipped ranks ends the ballot)
Measures (Grant's sign convention, D positive):
  - hold == R candidate share of R-legislator voters (two-way, D vs R)
  - pull == R candidate share of D-legislator voters (two-way)
  - pair effect == race margin - legislative margin, same ballots
Writes three_races_2026.json.
Usage: uv run three_races_2026.py
"""
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
FILES = {"House": "2026-11-04_23-33_rctab_cvr.csv", "Senate": "2026-11-05_00-56_rctab_cvr-senate.csv",
         "Governor": "2026-11-05_14-36_rctab_cvr-2026-governor.csv"}
RANKS = [f"Rank {i}" for i in range(1, 6)]
SHORT = {"Begich, Nick": "Begich", "Hill, Bill": "Hill", "Hafner, Eric": "Hafner", 'McDermott, James C. "Jim"': "McDermott",
         "Sullivan, Dan S.": "Sullivan", "Peltola, Mary": "Peltola", "Heikes, Gerald L.": "Heikes",
         "Sullivan, Daniel J. Jr.": "Sullivan Jr.", "Kreiss-Tomkins/Johnson": "Kreiss-Tomkins",
         "Wilson/Shower": "Wilson", "Bronson/Church": "Bronson", "Taylor/English": "Taylor"}
OVER, SKIP = "OVER", "SKIP"

# (race, label, D side, R side)
VERSIONS = [
    ("House", "Begich: first choice (Hill + Hafner against Begich)", ["Hill", "Hafner"], ["Begich"]),
    ("House", "Begich: head to head with Hill", ["Hill", "Hafner"], ["Begich"]),
    ("Senate", "Sullivan: first choice (Peltola against Sullivan)", ["Peltola"], ["Sullivan"]),
    ("Senate", "Sullivan: head to head with Peltola", ["Peltola"], ["Sullivan"]),
    ("Governor", "Wilson: first choice", ["Kreiss-Tomkins"], ["Wilson"]),
    ("Governor", "Wilson: head to head with Kreiss-Tomkins", ["Kreiss-Tomkins"], ["Wilson"]),
    ("Governor", "Governor R side: first choice (Wilson + Bronson + Taylor)", ["Kreiss-Tomkins"], ["Wilson", "Bronson", "Taylor"]),
    ("Governor", "Governor R side: head to head (any R against Kreiss-Tomkins)", ["Kreiss-Tomkins"], ["Wilson", "Bronson", "Taylor"]),
]


def parse(v: str):
    if v == "undervote":
        return SKIP
    if "\n" in v:
        return OVER
    return SHORT.get(v, v)


def first(ranks):
    for r in ranks:
        if r is SKIP:
            continue
        return "overvote" if r is OVER else r
    return "blank"


def head_to_head(ranks, keep: set):
    skips = 0
    for r in ranks:
        if r is SKIP:
            skips += 1
            continue
        if skips >= 2 or r is OVER:
            return "inactive"
        skips = 0
        if r in keep:
            return r
    return "inactive"


def load(race):
    df = pd.read_csv(HERE / FILES[race], usecols=["RCTab CVR Id"] + RANKS, dtype=str, keep_default_na=False)
    if race == "House":  # the 23:33 file is House only
        pass
    ranks = [tuple(parse(v) for v in row) for row in df[RANKS].itertuples(index=False)]
    return df["RCTab CVR Id"], ranks


def main():
    L = pd.read_csv(HERE / "legislative_2026.csv", dtype=str)
    L = L[(L.clean == "True") & L.leg_first.isin(["D", "R"])][["RCTab CVR Id", "leg_first"]]
    data = {}
    for race in FILES:
        ids, ranks = load(race)
        data[race] = pd.DataFrame({"RCTab CVR Id": ids, f"{race}_ranks": ranks})
    m = L
    for race in FILES:
        m = m.merge(data[race], on="RCTab CVR Id")
    print(f"clean-contest ballots matched in all three races: {len(m):,}")
    nD, nR = (m.leg_first == "D").sum(), (m.leg_first == "R").sum()
    leg_margin = (nD - nR) / (nD + nR) * 100
    print(f"legislative first choices: D {nD:,}  R {nR:,}  margin ({nD:,} - {nR:,}) / {nD + nR:,} x 100 == {leg_margin:+.2f}\n")

    out = []
    for race, label, D, R in VERSIONS:
        col = m[f"{race}_ranks"]
        if "head to head" in label:
            pick = col.map(lambda rk: head_to_head(rk, set(D + R)))
        else:
            pick = col.map(first)
        side = pick.map(lambda c: "D" if c in D else ("R" if c in R else "none"))
        row = {"race": race, "version": label}
        for leg in ["R", "D"]:
            s = side[m.leg_first == leg]
            row[f"{leg}leg_n"] = int(len(s))
            row[f"{leg}leg_R"] = int((s == "R").sum())
            row[f"{leg}leg_D"] = int((s == "D").sum())
            row[f"{leg}leg_none"] = int((s == "none").sum())
        row["hold"] = round(row["Rleg_R"] / (row["Rleg_R"] + row["Rleg_D"]) * 100, 2)
        row["pull"] = round(row["Dleg_R"] / (row["Dleg_R"] + row["Dleg_D"]) * 100, 2)
        # pair effect on ballots with a D or R vote in this race, legislative margin over those same ballots
        two = side != "none"
        d, r = (side[two] == "D").sum(), (side[two] == "R").sum()
        ld, lr = (m.leg_first[two] == "D").sum(), (m.leg_first[two] == "R").sum()
        row["race_margin"] = round((d - r) / (d + r) * 100, 2)
        row["leg_margin_same"] = round((ld - lr) / (ld + lr) * 100, 2)
        row["pair_effect"] = round(row["race_margin"] - row["leg_margin_same"], 2)
        row["ballots_two_way"] = int(two.sum())
        out.append(row)
        print(f"{label}")
        print(f"   R-leg voters {row['Rleg_n']:,}: R {row['Rleg_R']:,}  D {row['Rleg_D']:,}  none {row['Rleg_none']:,}  hold {row['hold']:.2f}%")
        print(f"   D-leg voters {row['Dleg_n']:,}: R {row['Dleg_R']:,}  D {row['Dleg_D']:,}  none {row['Dleg_none']:,}  pull {row['pull']:.2f}%")
        print(f"   pair {row['race_margin']:+.2f} - ({row['leg_margin_same']:+.2f}) == {row['pair_effect']:+.2f}  on {row['ballots_two_way']:,} ballots\n")
    (HERE / "three_races_2026.json").write_text(json.dumps({"ballots": len(m), "leg_margin": round(leg_margin, 2), "rows": out}, indent=1))


if __name__ == "__main__":
    main()
