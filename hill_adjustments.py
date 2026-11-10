# /// script
# dependencies = ["pandas"]
# ///
"""Both sides of the Hill adjustment (Grant, 6 Nov): if stopped House ballots are put back for the Democratic
side, Hill voters who would never vote for a Democrat have to come out too.

1. Stopped ballots. House final round as counted, against the same final round with each stopped House
   ballot assigned the side of its other-race final-round vote (Senate in 2026, president in 2024).
   stopped effect == actual margin - continued margin. Excess == 2026 effect - 2024 effect.
2. Hill voters a Democrat would not get (Grant's definition): House final Hill, and Senate first choice
   not Peltola, or governor first choice blank, write-in or overvote. Taken out of the continued margin.
   The 2024 stopped effect (+1.74) shows "normal" stopping depends on the field, so no baseline is subtracted.
Final round == head to head of the two finalists (begich_pairwise.side). Writes hill_adjustments.json.
Usage: uv run hill_adjustments.py
"""
import json
from pathlib import Path

import pandas as pd

from begich_pairwise import RANKS, side
import cvr2026

HERE = Path(__file__).parent


def final(path, R, D):
    df = pd.read_csv(HERE / path, usecols=["RCTab CVR Id"] + RANKS, dtype=str, keep_default_na=False)
    return pd.DataFrame({"id": df["RCTab CVR Id"], "e": [side(r, set(R), set(D)) for r in df[RANKS].itertuples(index=False)]})


def margins(h, o):
    """h, o: +1 R, -1 D, 0 none (House, other race). Returns actual, continued (D positive), counts."""
    hr, hd = (h == 1).sum(), (h == -1).sum()
    actual = (hd - hr) / (hd + hr) * 100
    c = h.where(h != 0, o)
    cr, cd = (c == 1).sum(), (c == -1).sum()
    cont = (cd - cr) / (cd + cr) * 100
    stopped = h == 0
    return dict(hill_or_D=int(hd), begich=int(hr), two_way=int(hd + hr), actual=round(actual, 2),
                cont_D=int(cd), cont_R=int(cr), cont_two_way=int(cd + cr), continued=round(cont, 2),
                stopped=int(stopped.sum()), stopped_to_D=int((stopped & (o == -1)).sum()),
                stopped_to_R=int((stopped & (o == 1)).sum()), stopped_none=int((stopped & (o == 0)).sum()),
                effect=round(actual - cont, 2))


def main():
    out = {}
    # 2026: House final Hill against Begich, Senate final Peltola against Sullivan
    h26 = final(cvr2026.HOUSE, ["Begich, Nick"], ["Hill, Bill"]).rename(columns={"e": "H"})
    s26 = final(cvr2026.SENATE, ["Sullivan, Dan S."], ["Peltola, Mary"]).rename(columns={"e": "S"})
    m26 = h26.merge(s26, on="id")
    out["stopped_2026"] = margins(m26.H, m26.S)
    # 2024: House final Peltola against Begich, president final Harris against Trump
    h24 = final("2026-11-04_23-29_rctab_cvr.csv", ["Begich, Nick"], ["Peltola, Mary S."]).rename(columns={"e": "H"})
    p24 = final("2026-11-05_14-34_rctab_cvr-2024-president.csv", ["Trump/Vance"], ["Harris/Walz"]).rename(columns={"e": "P"})
    m24 = h24.merge(p24, on="id")
    out["stopped_2024"] = margins(m24.H, m24.P)
    for k in ["stopped_2024", "stopped_2026"]:
        d = out[k]
        print(f"{k}: actual ({d['hill_or_D']:,} - {d['begich']:,}) / {d['two_way']:,} x 100 == {d['actual']:+.2f};"
              f" continued ({d['cont_D']:,} - {d['cont_R']:,}) / {d['cont_two_way']:,} x 100 == {d['continued']:+.2f};"
              f" effect {d['actual']:+.2f} - ({d['continued']:+.2f}) == {d['effect']:+.2f};"
              f" stopped {d['stopped']:,} (to D {d['stopped_to_D']:,}, to R {d['stopped_to_R']:,}, none {d['stopped_none']:,})")
    ex = out["stopped_2026"]["effect"] - out["stopped_2024"]["effect"]
    print(f"excess stopped effect == {out['stopped_2026']['effect']:+.2f} - ({out['stopped_2024']['effect']:+.2f}) == {ex:+.2f}\n")
    out["stopped_excess"] = round(ex, 2)

    # Hill voters a Democrat would not get (Grant's definition, 6 Nov): House final Hill, and Senate first choice
    # not Peltola, or governor first choice blank, write-in or overvote. Variants: without the Sullivan Jr. and
    # Heikes voters who chose Kreiss-Tomkins (protest voters), and a broader set (anything but Peltola AND
    # Kreiss-Tomkins). Each set is taken out of the continued margin.
    x = pd.read_csv(HERE / "crossover_2026.csv", dtype=str, keep_default_na=False)[["RCTab CVR Id", "S1"]].rename(columns={"RCTab CVR Id": "id"})
    g = pd.read_csv(HERE / cvr2026.GOVERNOR, usecols=["RCTab CVR Id", "Rank 1"], dtype=str, keep_default_na=False).rename(columns={"RCTab CVR Id": "id"})

    def gv(v):
        if v in ("", "undervote"):
            return "blank"
        if "\n" in v:
            return "overvote"
        if v.startswith("Kreiss"):
            return "Kreiss-Tomkins"
        return "Republican" if v.startswith(("Wilson", "Bronson", "Taylor")) else "write-in"

    g["gov"] = g["Rank 1"].map(gv)
    m = m26.merge(x, on="id", how="left").merge(g[["id", "gov"]], on="id", how="left")
    hill = m[m.H == -1]
    t = pd.crosstab(hill.S1.fillna("not matched"), hill.gov.fillna("not matched"), margins=True)
    print("Hill final-round voters, Senate first choice x governor first choice:")
    print(t.to_string())
    grant = (hill.S1 != "Peltola") | hill.gov.isin(["blank", "write-in", "overvote"])
    protest = hill.S1.isin(["Sullivan Jr.", "Heikes"]) & (hill.gov == "Kreiss-Tomkins")
    broad = (hill.S1 != "Peltola") | (hill.gov != "Kreiss-Tomkins")
    D, R = out["stopped_2026"]["cont_D"], out["stopped_2026"]["cont_R"]
    cont = out["stopped_2026"]["continued"]
    sets = {}
    for name, mask in [("Grant set", grant), ("without protest voters", grant & ~protest), ("broader", broad)]:
        k = int(mask.sum())
        mg = (D - k - R) / (D - k + R) * 100
        sets[name] = dict(ballots=k, margin=round(mg, 2), effect=round(mg - cont, 2))
        print(f"{name}: ({D:,} - {k:,} - {R:,}) / ({D - k + R:,}) x 100 == {mg:.2f}; effect {mg:.2f} - ({cont:+.2f}) == {mg - cont:+.2f}")
    net = out["stopped_2026"]["effect"] * -1 + sets["Grant set"]["effect"]
    print(f"both sides: stopped +{-out['stopped_2026']['effect']:.2f} + Hill non-D {sets['Grant set']['effect']:+.2f} == {net:+.2f}")
    out["hill_nonD"] = sets
    out["both_sides_net"] = round(net, 2)
    (HERE / "hill_adjustments.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
