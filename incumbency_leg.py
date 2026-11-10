# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2", "numpy>=2"]
# ///
"""Incumbency advantage from the state legislative races, on the same ballots as a statewide race (2022-2026).

For every state House and Senate contest with a Democrat and a Republican on the November ballot:
  legislative margin == D first choices - R first choices, as a share of the two (one ballot, one vote)
  baseline margin    == the statewide race's D side - R side on exactly the same ballots
  difference         == legislative margin - baseline margin
The baseline takes out the district's partisanship and the year's environment, so no lean or beta is needed.
  incumbency == the slope of difference on inc, where inc == (D-side incumbents running) - (R-side ones),
                so +1 a Democratic incumbent, -1 a Republican incumbent, 0 an open seat
with a fixed effect per year and baseline. Incumbents are the sitting members of the same chamber
(legislators.csv, from the Wikipedia rosters of the 32nd-34th Legislatures), matched by name to the
November candidates in the Dominion CandidateManifest. Contests whose incumbent ran as neither D nor R are
left out, and so are contests with a member of the other chamber running (reported separately).

Baselines: 2022 governor (Gara + Walker against Dunleavy + Pierce) and US House (Peltola against Palin +
Begich); 2024 president and US House; 2026 governor (Kreiss-Tomkins against the three Republicans) and US
House (Hill + Hafner against Begich). First choices throughout.

Usage: uv run incumbency_leg.py   (needs legislative_YYYY.csv from tests_2022.py, tests_2024.py and
legislative.py). Writes incumbency_leg.json and incumbency_leg_contests.csv.
"""
import os
import json
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

from legislative import party_sides
import cvr2026

HERE = Path(__file__).parent
DL = Path(os.environ.get("AK_DATA_DIR", "data"))
BASE = {
    2022: {"governor": ("2026-11-05_14-33_rctab_cvr-2022-governor.csv", ("Gara", "Walker"), ("Dunleavy", "Pierce")),
           "US House": ("2026-11-05_14-31_rctab_cvr-2022-house.csv", ("Peltola",), ("Palin", "Begich"))},
    2024: {"president": ("2026-11-05_14-34_rctab_cvr-2024-president.csv", ("Harris",), ("Trump",)),
           "US House": ("2026-11-04_23-29_rctab_cvr.csv", ("Peltola",), ("Begich",))},
    2026: {"governor": (cvr2026.GOVERNOR, ("Kreiss-Tomkins",), ("Wilson", "Bronson", "Taylor")),
           "US House": (cvr2026.HOUSE, ("Hill", "Hafner"), ("Begich",))},
}
MIN_BALLOTS = 500


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ,\-]", "", s)


def key_ballot(desc: str) -> tuple[str, str]:
    """'Stedman, Bert K.' -> ('stedman', 'ber')."""
    last, _, first = norm(desc).partition(",")
    return last.strip(), first.strip()[:3]


def key_roster(name: str) -> tuple[str, str]:
    parts = norm(name).replace(" jr", "").split()
    return parts[-1], parts[0][:3]


def contest_table(year: int, roster: pd.DataFrame) -> pd.DataFrame:
    src = DL / f"alaska-{year}"
    contests = {c["Id"]: c["Description"] for c in json.loads((src / "ContestManifest.json").read_text())["List"]}
    leg = {i: d for i, d in contests.items() if d.startswith(("House District", "Senate District"))}
    side = party_sides(src)
    cands = [c for c in json.loads((src / "CandidateManifest.json").read_text())["List"]
             if c["ContestId"] in leg and c.get("Type", "Regular") == "Regular"]
    rows = []
    for cid, cname in leg.items():
        chamber = "House" if cname.startswith("House") else "Senate"
        same = roster[(roster.election_year == year) & (roster.chamber == chamber)]
        other = roster[(roster.election_year == year) & (roster.chamber != chamber)]
        inc_d = inc_r = inc_other = cross = 0
        names = []
        for c in (c for c in cands if c["ContestId"] == cid):
            k = key_ballot(c["Description"])
            hit = same[same.key == k]
            aff = [side.get(a, "other") for a in c.get("Affiliations", [])]
            if not hit.empty:
                p = aff[0] if aff else {"Dem": "D", "Rep": "R"}.get(hit.party.iloc[0], "other")
                inc_d += p == "D"; inc_r += p == "R"; inc_other += p == "other"
                names.append(f"{c['Description']} (incumbent, {p})")
            elif not other[other.key == k].empty:
                cross += 1
                names.append(f"{c['Description']} (other chamber)")
        rows.append({"year": year, "contest": cid, "contest_name": cname, "inc_d": inc_d, "inc_r": inc_r,
                     "inc_other": inc_other, "other_chamber": cross, "incumbents": "; ".join(names)})
    return pd.DataFrame(rows)


def baseline_sides(path: str, d: tuple, r: tuple) -> pd.DataFrame:
    b = pd.read_csv(HERE / path, usecols=["RCTab CVR Id", "Rank 1"], dtype=str, keep_default_na=False)
    b["base"] = b["Rank 1"].map(lambda v: "D" if v.startswith(d) else ("R" if v.startswith(r) else "x"))
    return b[["RCTab CVR Id", "base"]]


def margin(s: pd.Series) -> float:
    n = s.value_counts()
    d, r = n.get("D", 0), n.get("R", 0)
    return (d - r) / (d + r) * 100


def fit(df: pd.DataFrame) -> dict:
    """OLS of difference on inc with a fixed effect for each year x baseline group."""
    groups = sorted(df.group.unique())
    X = np.column_stack([df.inc.values] + [(df.group == g).astype(float).values for g in groups])
    y = df["difference"].values
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    dof = len(y) - X.shape[1]
    se = float(np.sqrt((resid ** 2).sum() / dof * np.linalg.inv(X.T @ X)[0, 0])) if dof > 0 else float("nan")
    return {"incumbency": round(float(coef[0]), 2), "se": round(se, 2), "contests": int(len(df)),
            "resid_sd": round(float(np.sqrt((resid ** 2).sum() / max(dof, 1))), 2)}


def main() -> None:
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500); pd.set_option("display.max_colwidth", 80)
    roster = pd.read_csv(HERE / "legislators.csv")
    roster["key"] = roster.name.map(key_roster)
    out_rows = []
    for year, bases in BASE.items():
        C = contest_table(year, roster)
        L = pd.read_csv(HERE / f"legislative_{year}.csv", dtype={"RCTab CVR Id": str, "leg_first": str})
        L = L[(L.contested.astype(str) == "True") & L.leg_first.isin(["D", "R"])]
        for bname, (path, d, r) in bases.items():
            B = baseline_sides(path, d, r)
            m = L.merge(B, on="RCTab CVR Id")
            m = m[m.base.isin(["D", "R"])]
            for cid, g in m.groupby("contest"):
                if len(g) < MIN_BALLOTS:
                    continue
                c = C[C.contest == cid].iloc[0]
                lm, bm = margin(g.leg_first), margin(g.base)
                out_rows.append({"year": year, "baseline": bname, "group": f"{year} {bname}", "contest_name": c.contest_name,
                                 "clean": bool(g.clean.astype(str).eq("True").all()), "ballots": len(g),
                                 "legislative_margin": round(lm, 2), "baseline_margin": round(bm, 2),
                                 "difference": round(lm - bm, 2), "inc": int(c.inc_d - c.inc_r),
                                 "inc_other": int(c.inc_other), "other_chamber": int(c.other_chamber), "incumbents": c.incumbents})
    T = pd.DataFrame(out_rows)
    T.to_csv(HERE / "incumbency_leg_contests.csv", index=False)
    show = T[T.baseline.isin(["governor", "president"])]
    print(show[["year", "contest_name", "clean", "ballots", "legislative_margin", "baseline_margin", "difference", "inc", "incumbents"]].to_string(index=False))

    use = T[(T.inc_other == 0) & (T.other_chamber == 0)]
    results = {}
    print("\n== Incumbency == slope of (legislative margin - baseline margin) on inc, fixed effect per year x baseline")
    for label, sub in [("top of ticket, all contested", use[use.baseline != "US House"]),
                       ("top of ticket, clean only", use[(use.baseline != "US House") & use.clean]),
                       ("US House baseline, all contested", use[use.baseline == "US House"]),
                       ("both baselines, all contested", use)]:
        f = fit(sub)
        results[label] = f
        print(f"  {label:34} incumbency {f['incumbency']:+.2f} (standard error {f['se']:.2f}), {f['contests']} contest-baselines, residual sd {f['resid_sd']}")
    print("\n== Mean difference by status (top-of-ticket baseline)")
    tt = use[use.baseline != "US House"].copy()
    tt["status"] = tt.inc.map({1: "D incumbent", 0: "open or both", -1: "R incumbent"})
    means = tt.groupby(["year", "status"])["difference"].agg(["count", "mean"]).round(2)
    print(means.to_string())
    allm = tt.groupby("status")["difference"].agg(["count", "mean"]).round(2)
    print(allm.to_string())
    for y in (2022, 2024, 2026):
        f = fit(use[(use.year == y) & (use.baseline != "US House")])
        results[f"{y} top of ticket"] = f
        print(f"  {y}: incumbency {f['incumbency']:+.2f} (se {f['se']:.2f}), {f['contests']} contests")
    print(f"\nLeft out: {int((T.inc_other > 0).sum())} contest-baselines with an incumbent outside D/R, "
          f"{int((T.other_chamber > 0).sum())} with a member of the other chamber running")
    (HERE / "incumbency_leg.json").write_text(json.dumps({"fits": results, "means": allm.reset_index().to_dict(orient="records")}, indent=1))


if __name__ == "__main__":
    main()
