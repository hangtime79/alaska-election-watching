# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2"]
# ///
"""Same-ballot tests on the November 2024 general (test plan step 1: B3 and C3). No lean or beta needed.

Ballots in clean (one D, one R) state legislative contests, joined on RCTab CVR Id to the House final round
(Peltola - Begich) and the presidential final round (Harris - Trump), both under Alaska's ranked-choice
rules (ballot_2024.final). The legislative first choice sorts voters into Republican-legislator and
Democratic-legislator voters.

B3  Among R-legislator voters: Peltola's share against Harris's. Among D-legislator voters: Begich's share
    against Trump's. On ballots with a two-way vote in all three races, the premium splits exactly into
      D part == 2 x (R-legislator voters choosing Peltola - R-legislator voters choosing Harris) / ballots
      R part == -2 x (D-legislator voters choosing Begich - D-legislator voters choosing Trump) / ballots
    A crossover is credited to the candidate who receives it (the rule used in ballot_2024.py). The D part
    is Peltola's pull over Harris; the R part is Trump's pull over Begich.

C3  Trump-voter loyalty: among Trump voters, the share choosing Begich against the share choosing the
    Republican legislator (with the Harris-voter mirror: Peltola against the Democratic legislator).

Writes tests_2024.json. Caches the 2024 legislative first choices to legislative_2024.csv (gitignored).
Usage: uv run tests_2024.py
"""
import os
import json
from pathlib import Path

import pandas as pd

from ballot_2024 import DONE, ELIM_H, HOUSE, PRES, final
from legislative import leg_first

HERE = Path(__file__).parent
DL = Path(os.environ.get("AK_DATA_DIR", "data"))
HOUSE_SIDE = {"Peltola": "D", "Begich": "R"}
PRES_SIDE = {"Harris": "D", "Trump": "R"}


def two_way(s: pd.Series) -> tuple[float, int, int]:
    n = s.value_counts()
    d, r = int(n.get("D", 0)), int(n.get("R", 0))
    return (d - r) / (d + r) * 100, d, r


def legislative() -> pd.DataFrame:
    cache = HERE / "legislative_2024.csv"
    if not cache.exists():
        leg_first(DL / "alaska-2024").to_csv(cache, index=False)
    return pd.read_csv(cache, dtype={"RCTab CVR Id": str, "leg_first": str})


def main() -> None:
    pd.set_option("display.width", 200)
    L = legislative()
    clean = L[L.clean.astype(str) == "True"]
    print(f"Clean 2024 legislative contests: {sorted(clean.contest_name.unique())}")
    h = pd.read_csv(HOUSE, dtype=str, keep_default_na=False)
    p = pd.read_csv(PRES, dtype=str, keep_default_na=False)
    pres_all = {v for c in p.columns if c.startswith("Rank ") for v in p[c].unique()} - {"undervote", "Harris/Walz", "Trump/Vance"}
    h["HF"] = final(h, ELIM_H)
    p["PF"] = final(p, {v for v in pres_all if "\n" not in v})
    m = clean.merge(h[["RCTab CVR Id", "HF"]], on="RCTab CVR Id").merge(p[["RCTab CVR Id", "PF"]], on="RCTab CVR Id")
    m["H"] = m.HF.map(HOUSE_SIDE).fillna("x")
    m["P"] = m.PF.map(PRES_SIDE).fillna("x")
    print(f"Clean-contest ballots matched to House and president: {len(m):,}")

    # ---- B3
    b = m[m.leg_first.isin(["D", "R"]) & m.H.isin(["D", "R"]) & m.P.isin(["D", "R"])]
    n = len(b)
    c = lambda leg, col, side: int(((b.leg_first == leg) & (b[col] == side)).sum())
    lm, ld, lr = two_way(b.leg_first)
    hm, _, _ = two_way(b.H)
    pm, _, _ = two_way(b.P)
    r_pel, r_har = c("R", "H", "D"), c("R", "P", "D")
    d_beg, d_tru = c("D", "H", "R"), c("D", "P", "R")
    d_part = 2 * (r_pel - r_har) / n * 100
    r_part = -2 * (d_beg - d_tru) / n * 100
    b3 = {"ballots": n, "legislative_margin": round(lm, 2), "house_margin": round(hm, 2), "president_margin": round(pm, 2),
          "premium": round(hm - pm, 2), "r_leg": lr, "r_leg_peltola": r_pel, "r_leg_harris": r_har,
          "d_leg": ld, "d_leg_begich": d_beg, "d_leg_trump": d_tru, "d_part": round(d_part, 2), "r_part": round(r_part, 2)}
    print(f"\n== B3: {n:,} ballots with a two-way vote in the legislative race, House and president")
    print(f"  legislative {lm:+.2f}  House {hm:+.2f}  president {pm:+.2f}  premium {hm:+.2f} - ({pm:+.2f}) == {hm - pm:+.2f}")
    print(f"  R-legislator voters {lr:,}: Peltola {r_pel:,} ({r_pel / lr * 100:.1f}%), Harris {r_har:,} ({r_har / lr * 100:.1f}%)")
    print(f"     D part == 2 x ({r_pel:,} - {r_har:,}) / {n:,} x 100 == {d_part:+.2f}")
    print(f"  D-legislator voters {ld:,}: Begich {d_beg:,} ({d_beg / ld * 100:.1f}%), Trump {d_tru:,} ({d_tru / ld * 100:.1f}%)")
    print(f"     R part == -2 x ({d_beg:,} - {d_tru:,}) / {n:,} x 100 == {r_part:+.2f}")
    print(f"  check {d_part:+.2f} + ({r_part:+.2f}) == {d_part + r_part:+.2f}")
    # the cross-cell: R-legislator voters who chose both Peltola and Trump, etc.
    print("\n  R-legislator voters, House x president:\n", pd.crosstab(b[b.leg_first == "R"].HF, b[b.leg_first == "R"].PF).to_string())
    print("\n  D-legislator voters, House x president:\n", pd.crosstab(b[b.leg_first == "D"].HF, b[b.leg_first == "D"].PF).to_string())

    # ---- C3: all clean-contest ballots of Trump (and Harris) voters, no-vote outcomes kept
    c3 = {}
    print("\n== C3: loyalty, all clean-contest ballots")
    for who, house_same, house_other, leg_same, leg_other in [("Trump", "Begich", "Peltola", "R", "D"), ("Harris", "Peltola", "Begich", "D", "R")]:
        v = m[m.PF == who]
        k = len(v)
        hs, ho, hn = (v.HF == house_same).sum(), (v.HF == house_other).sum(), (v.HF == DONE).sum()
        ls, lo = (v.leg_first == leg_same).sum(), (v.leg_first == leg_other).sum()
        ln = k - ls - lo
        both = v[v.HF.isin(["Peltola", "Begich"]) & v.leg_first.isin(["D", "R"])]
        hs2, ls2 = (both.HF == house_same).sum() / len(both) * 100, (both.leg_first == leg_same).sum() / len(both) * 100
        c3[who] = {"voters": k, f"house_{house_same}": int(hs), f"house_{house_other}": int(ho), "house_no_vote": int(hn),
                   "leg_same": int(ls), "leg_other": int(lo), "leg_blank_other": int(ln),
                   "two_way_ballots": len(both), "house_same_pct": round(hs2, 2), "leg_same_pct": round(ls2, 2)}
        print(f"  {who} voters {k:,}")
        print(f"    House: {house_same} {hs:,} ({hs / k * 100:.1f}%), {house_other} {ho:,} ({ho / k * 100:.1f}%), no final-round vote {hn:,} ({hn / k * 100:.1f}%)")
        print(f"    Legislature: same party {ls:,} ({ls / k * 100:.1f}%), other party {lo:,} ({lo / k * 100:.1f}%), blank/other {ln:,} ({ln / k * 100:.1f}%)")
        print(f"    Two-way in both ({len(both):,}): {house_same} {hs2:.2f}%, same-party legislator {ls2:.2f}%, gap {hs2:.2f} - {ls2:.2f} == {hs2 - ls2:+.2f}")
    (HERE / "tests_2024.json").write_text(json.dumps({"b3": b3, "c3": c3}, indent=1, default=int))


if __name__ == "__main__":
    main()
