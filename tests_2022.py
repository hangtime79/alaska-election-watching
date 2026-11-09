# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2"]
# ///
"""Same-ballot tests on the November 2022 general (test plan step 1: B1 and C4). No lean or beta needed.

B1  Peltola against Gara + Walker. On every ballot, the House side (Peltola against Palin + Begich) and the
    governor side (Gara + Walker against Dunleavy + Pierce). A side is the bloc the ballot ranks higher under
    Alaska's rules (rcv.assign with everyone else eliminated), so a Bye or Write-in first choice still counts
    if it ranks a bloc candidate later. Premium == House two-way margin - governor two-way margin (D positive),
    by House district, rural (HD37-40) against everywhere else. First-choice blocs are printed as a check.

C4  Begich against Dunleavy, relative to the legislative line, net of Peltola. On ballots in clean (one D,
    one R) state legislative contests: House head to head Peltola - Begich, governor Gara + Walker - Dunleavy
    (Pierce eliminated), legislative first choice. The gap between the two race margins splits exactly into
      D part == 2 x (R-legislator voters choosing Peltola - R-legislator voters choosing Gara + Walker) / ballots
      R part == -2 x (D-legislator voters choosing Begich - D-legislator voters choosing Dunleavy) / ballots
    Attribution rule (the same as ballot_2024.py): a crossover is credited to the candidate who receives it.
    The D part is Peltola's effect over Gara + Walker (B1's effect on these ballots); the R part is
    Begich's effect relative to Dunleavy. Both include incumbency (Peltola and Dunleavy were incumbents).

Writes tests_2022.json. Caches the 2022 legislative first choices to legislative_2022.csv (gitignored).
Usage: uv run tests_2022.py
"""
import os
import json
from pathlib import Path

import pandas as pd

from legislative import leg_first
from pair_effects import sides

HERE = Path(__file__).parent
DL = Path(os.environ.get("AK_DATA_DIR", "data"))
HOUSE = HERE / "2026-11-05_14-31_rctab_cvr-2022-house.csv"
GOV = HERE / "2026-11-05_14-33_rctab_cvr-2022-governor.csv"
RURAL = {37, 38, 39, 40}


def two_way(s: pd.Series) -> tuple[float, int, int]:
    n = s.value_counts()
    d, r = int(n.get("D", 0)), int(n.get("R", 0))
    return (d - r) / (d + r) * 100, d, r


def legislative() -> pd.DataFrame:
    cache = HERE / "legislative_2022.csv"
    if not cache.exists():
        leg_first(DL / "alaska-2022").to_csv(cache, index=False)
    L = pd.read_csv(cache, dtype={"RCTab CVR Id": str, "leg_first": str})
    return L


def first_choice_bloc(path: Path, d: tuple, r: tuple) -> pd.Series:
    r1 = pd.read_csv(path, usecols=["Rank 1"], dtype=str, keep_default_na=False)["Rank 1"]
    return r1.map(lambda v: "D" if v.startswith(d) else ("R" if v.startswith(r) else "x"))


def b1() -> dict:
    H = sides(HOUSE, ("Peltola",), ("Palin", "Begich"), "two").rename(columns={"race": "H"})
    G = sides(GOV, ("Gara", "Walker"), ("Dunleavy", "Pierce"), "two").rename(columns={"race": "G"})
    H["H1"] = first_choice_bloc(HOUSE, ("Peltola",), ("Palin", "Begich")).values
    G["G1"] = first_choice_bloc(GOV, ("Gara", "Walker"), ("Dunleavy", "Pierce")).values
    m = H.merge(G[["RCTab CVR Id", "G", "G1"]], on="RCTab CVR Id")
    print(f"B1  House {len(H):,}  governor {len(G):,}  matched {len(m):,}")
    m["dist"] = m["loc"].str.extract(r"^(?:House District |District |HD)?(\d+)", expand=False).astype(int)
    m["region"] = m.dist.map(lambda x: "Rural HD37-40" if x in RURAL else "Everywhere else")

    def row(key, d, hc="H", gc="G"):
        both = d[d[hc].isin(["D", "R"]) & d[gc].isin(["D", "R"])]
        hm, hd, hr = two_way(both[hc])
        gm, gd, gr = two_way(both[gc])
        return {"group": key, "ballots": len(both), "peltola": hd, "palin_begich": hr, "gara_walker": gd,
                "dunleavy_pierce": gr, "house_margin": round(hm, 2), "governor_margin": round(gm, 2),
                "premium": round(hm - gm, 2)}

    out = {"ranked_bloc": [row("Statewide", m)] + [row(k, d) for k, d in m.groupby("region")],
           "first_choice": [row("Statewide", m, "H1", "G1")] + [row(k, d, "H1", "G1") for k, d in m.groupby("region")],
           "by_district": [row(int(k), d) for k, d in m.groupby("dist")]}
    for k in ("ranked_bloc", "first_choice"):
        print(f"\n== B1, {k}: premium == House margin - governor margin")
        for r in out[k]:
            print(f"  {r['group']:16} ballots {r['ballots']:>7,}  house {r['house_margin']:+7.2f}  governor {r['governor_margin']:+7.2f}"
                  f"  premium {r['house_margin']:+.2f} - ({r['governor_margin']:+.2f}) == {r['premium']:+.2f}")
    t = pd.DataFrame(out["by_district"])
    print("\n== B1 by House district (ranked bloc)\n", t.to_string(index=False))
    other = t[~t.group.isin(RURAL)]
    print(f"\nOther districts: premium median {other.premium.median():+.2f}, min {other.premium.min():+.2f}, max {other.premium.max():+.2f};"
          f" correlation with governor margin {other[['premium', 'governor_margin']].corr().iloc[0, 1]:.2f}")
    return out, m


def split(m: pd.DataFrame, hc: str, gc: str) -> dict:
    """Exact split of House margin - governor margin by the voter's legislative side."""
    n = len(m)
    c = lambda leg, col, side: int(((m.leg_first == leg) & (m[col] == side)).sum())
    lm, ld, lr = two_way(m.leg_first)
    hm, _, _ = two_way(m[hc])
    gm, _, _ = two_way(m[gc])
    r_leg = {"n": lr, "to_house_D": c("R", hc, "D"), "to_gov_D": c("R", gc, "D")}
    d_leg = {"n": ld, "to_house_R": c("D", hc, "R"), "to_gov_R": c("D", gc, "R")}
    d_part = 2 * (r_leg["to_house_D"] - r_leg["to_gov_D"]) / n * 100
    r_part = -2 * (d_leg["to_house_R"] - d_leg["to_gov_R"]) / n * 100
    return {"ballots": n, "legislative_margin": round(lm, 2), "house_margin": round(hm, 2), "governor_margin": round(gm, 2),
            "gap": round(hm - gm, 2), "house_pair": round(hm - lm, 2), "governor_pair": round(gm - lm, 2),
            "r_leg": r_leg, "d_leg": d_leg, "d_part": round(d_part, 2), "r_part": round(r_part, 2)}


def c4(L: pd.DataFrame) -> dict:
    H = sides(HOUSE, ("Peltola",), ("Begich",), "two").rename(columns={"race": "Hh"})
    G = sides(GOV, ("Gara", "Walker"), ("Dunleavy",), "two").rename(columns={"race": "Gh"})
    Hb = sides(HOUSE, ("Peltola",), ("Palin", "Begich"), "two").rename(columns={"race": "Hb"})
    Gb = sides(GOV, ("Gara", "Walker"), ("Dunleavy", "Pierce"), "two").rename(columns={"race": "Gb"})
    clean = L[(L.clean.astype(str) == "True") & L.leg_first.isin(["D", "R"])]
    print(f"\nClean 2022 legislative contests: {sorted(clean.contest_name.unique())}")
    m = clean.merge(H[["RCTab CVR Id", "Hh"]], on="RCTab CVR Id").merge(G[["RCTab CVR Id", "Gh"]], on="RCTab CVR Id") \
             .merge(Hb[["RCTab CVR Id", "Hb"]], on="RCTab CVR Id").merge(Gb[["RCTab CVR Id", "Gb"]], on="RCTab CVR Id")
    out = {}
    for key, hc, gc in [("head_to_head", "Hh", "Gh"), ("blocs", "Hb", "Gb")]:
        sub = m[m[hc].isin(["D", "R"]) & m[gc].isin(["D", "R"])]
        s = split(sub, hc, gc)
        out[key] = s
        print(f"\n== C4 ({key}): {s['ballots']:,} clean-contest ballots with a two-way vote in both races")
        print(f"  legislative {s['legislative_margin']:+.2f}  house {s['house_margin']:+.2f}  governor {s['governor_margin']:+.2f}")
        print(f"  gap == house - governor == {s['house_margin']:+.2f} - ({s['governor_margin']:+.2f}) == {s['gap']:+.2f}")
        print(f"  R-legislator voters {s['r_leg']['n']:,}: chose Peltola {s['r_leg']['to_house_D']:,}, chose Gara/Walker {s['r_leg']['to_gov_D']:,}")
        print(f"     D part == 2 x ({s['r_leg']['to_house_D']:,} - {s['r_leg']['to_gov_D']:,}) / {s['ballots']:,} x 100 == {s['d_part']:+.2f}")
        print(f"  D-legislator voters {s['d_leg']['n']:,}: chose House R {s['d_leg']['to_house_R']:,}, chose governor R {s['d_leg']['to_gov_R']:,}")
        print(f"     R part == -2 x ({s['d_leg']['to_house_R']:,} - {s['d_leg']['to_gov_R']:,}) / {s['ballots']:,} x 100 == {s['r_part']:+.2f}")
        print(f"  check: {s['d_part']:+.2f} + ({s['r_part']:+.2f}) == {s['d_part'] + s['r_part']:+.2f} (gap {s['gap']:+.2f})")
    return out


def main() -> None:
    pd.set_option("display.width", 200)
    out, _ = b1()
    out["c4"] = c4(legislative())
    (HERE / "tests_2022.json").write_text(json.dumps(out, indent=1, default=int))


if __name__ == "__main__":
    main()
