# /// script
# dependencies = ["pandas"]
# ///
"""Peltola's urban ceiling: Peltola against non-Peltola Democrats, 2022-2026.

Election-day precinct ballots only (labels like "35-582 Chena"), in the precincts
present in every file, split urban/other (HD1-36) and rural (HD37-40).
First choices. For each race: D bloc, R bloc, other (minor, write-in, blank,
overvote) and total ballots; the two-bloc margin (D - R) / (D + R); district margins.
Then the 2026 Senate x governor crosstab on the same ballots (RCTab CVR Id).

Writes ceiling.json.
"""
import json
import pandas as pd
import cvr2026

RACES = [
    ("2022", "House", "Peltola", "2026-11-05_14-31_rctab_cvr-2022-house.csv", ["Peltola, Mary S."], ["Palin, Sarah", "Begich, Nick"]),
    ("2022", "Governor", "Gara + Walker", "2026-11-05_14-33_rctab_cvr-2022-governor.csv", ["Gara/Cook", "Walker/Drygas"], ["Dunleavy/Dahlstrom", "Pierce/Grunwald"]),
    ("2024", "House", "Peltola", "2026-11-04_23-29_rctab_cvr.csv", ["Peltola, Mary S."], ["Begich, Nick"]),
    ("2024", "President", "Harris", "2026-11-05_14-34_rctab_cvr-2024-president.csv", ["Harris/Walz"], ["Trump/Vance"]),
    ("2026", "Senate", "Peltola", cvr2026.SENATE, ["Peltola, Mary"], ["Sullivan, Dan S."]),
    ("2026", "Governor", "Kreiss-Tomkins", cvr2026.GOVERNOR, ["Kreiss-Tomkins/Johnson"], ["Wilson/Shower", "Bronson/Church", "Taylor/English"]),
    ("2026", "House", "Hill + Hafner", cvr2026.HOUSE, ["Hill, Bill", "Hafner, Eric"], ["Begich, Nick"]),
]
PAT = r"^(\d+)-\d+ "


def load(f, extra=()):
    d = pd.read_csv(f, usecols=["Precinct Portion", "Rank 1", *extra], dtype=str)
    d["loc"] = d["Precinct Portion"].str.replace(r"\s+", " ", regex=True).str.strip()
    m = d["loc"].str.extract(PAT)[0]
    keep = m.notna()
    return d[keep].assign(dist=m[keep].astype(int))


def main():
    tabs, frames = {}, {}
    for yr, off, dname, f, D, R in RACES:
        d = load(f, ["RCTab CVR Id"] if yr == "2026" else [])
        d["side"] = d["Rank 1"].map(lambda v: "D" if v in D else ("R" if v in R else "other"))
        tabs[(yr, off)] = (dname, d.groupby(["loc", "dist", "side"]).size().unstack(fill_value=0))
        frames[(yr, off)] = d
    common = sorted(set.intersection(*[set(t.index) for _, t in tabs.values()]))
    locs = {l for l, _ in common}

    totals, dist = [], {}
    for (yr, off), (dname, t) in tabs.items():
        t = t.loc[common]
        for grp, sel in [("urban", t.index.get_level_values("dist") < 37), ("rural", t.index.get_level_values("dist") >= 37)]:
            s = t[sel].sum()
            D, R, O = int(s["D"]), int(s["R"]), int(s["other"])
            T = D + R + O
            totals.append(dict(year=yr, office=off, dem=dname, group=grp, precincts=int(sel.sum()), D=D, R=R, other=O, total=T,
                               d_share=round(100 * D / T, 2), r_share=round(100 * R / T, 2), margin=round(100 * (D - R) / (D + R), 2)))
        g = t.groupby(level="dist").sum()
        dist[f"{yr} {off}"] = (100 * (g["D"] - g["R"]) / (g["D"] + g["R"])).round(2)
    tot = pd.DataFrame(totals)
    print(tot.to_string(index=False))

    dm = pd.DataFrame(dist)
    dm = dm[dm.index < 37]
    dm["gap22"] = dm["2022 House"] - dm["2022 Governor"]
    dm["gap24"] = dm["2024 House"] - dm["2024 President"]
    dm["gap26"] = dm["2026 Senate"] - dm["2026 Governor"]
    dm["pel26_minus_pel24"] = dm["2026 Senate"] - dm["2024 House"]
    dm["kt26_minus_pel24"] = dm["2026 Governor"] - dm["2024 House"]
    print(dm[["gap22", "gap24", "gap26", "pel26_minus_pel24", "kt26_minus_pel24"]].describe().round(2).to_string())

    # 2026 Senate x governor on the same ballots, urban common precincts
    s = frames[("2026", "Senate")]
    g = frames[("2026", "Governor")]
    m = s.merge(g[["RCTab CVR Id", "Rank 1"]], on="RCTab CVR Id", suffixes=("_sen", "_gov"))
    m = m[m["loc"].isin(locs) & (m["dist"] < 37)]
    sen = {"Peltola, Mary": "Peltola", "Sullivan, Dan S.": "Sullivan", "Heikes, Gerald L.": "Heikes", "Sullivan, Daniel J. Jr.": "Sullivan Jr."}
    gov = {"Kreiss-Tomkins/Johnson": "Kreiss-Tomkins", "Wilson/Shower": "Republican", "Bronson/Church": "Republican", "Taylor/English": "Republican"}
    m["S"] = m["Rank 1_sen"].map(sen).fillna("blank/write-in/overvote")
    m["G"] = m["Rank 1_gov"].map(gov).fillna("blank/write-in/overvote")
    ct = pd.crosstab(m["S"], m["G"], margins=True)
    print(ct.to_string())

    json.dump(dict(precincts_common=len(common), totals=totals,
                   districts=dm.round(2).reset_index().to_dict("records"),
                   senate_x_governor_2026_urban=ct.reset_index().to_dict("records")),
              open("ceiling.json", "w"), indent=1)


if __name__ == "__main__":
    main()
