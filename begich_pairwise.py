# /// script
# dependencies = ["pandas"]
# ///
"""Begich against another Republican on the same ballots, head to head, by region (Grant's pairwise view, 6 Nov).

For each comparison: Begich's race (Begich against his Democratic-side opponent) and the comparison race
(the other Republican side against its Democratic side), on the same ballots (RCTab CVR Id).
Head to head: each ballot counts for whichever of the two named sides it ranks higher, everyone else
eliminated (Alaska rules as in rcv.assign: an overvote or two skipped ranks ends the ballot).
  House effect      == +1 Begich, -1 his opponent, 0 neither
  comparison effect == +1 the comparison Republican side, -1 its opponent, 0 neither
  weight            == House effect - comparison effect (toward Begich)
  points            == sum of weights / ballots x 100; signed D-positive == -points
Region: rural == HD37-40, from Precinct Portion. Writes begich_pairwise.json.
Usage: uv run begich_pairwise.py
"""
import json
import re
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RANKS = [f"Rank {i}" for i in range(1, 6)]
OVER, SKIP = "OVER", "SKIP"

# (label, Begich race file, Begich D side, comparison file, comparison R side, comparison D side, where Peltola is)
COMPARISONS = [
    ("2026: Begich against the governor Republicans", "2026-11-04_23-33_rctab_cvr.csv", ["Hill, Bill", "Hafner, Eric"],
     "2026-11-05_14-36_rctab_cvr-2026-governor.csv", ["Wilson/Shower", "Bronson/Church", "Taylor/English"], ["Kreiss-Tomkins/Johnson"], "nowhere"),
    ("2026: Begich against Sullivan", "2026-11-04_23-33_rctab_cvr.csv", ["Hill, Bill", "Hafner, Eric"],
     "2026-11-05_00-56_rctab_cvr-senate.csv", ["Sullivan, Dan S."], ["Peltola, Mary"], "comparison side"),
    ("2024: Begich against Trump", "2026-11-04_23-29_rctab_cvr.csv", ["Peltola, Mary S.", "Hafner, Eric"],
     "2026-11-05_14-34_rctab_cvr-2024-president.csv", ["Trump/Vance"], ["Harris/Walz"], "Begich side"),
    ("2022: Begich against Dunleavy", "2026-11-05_14-31_rctab_cvr-2022-house.csv", ["Peltola, Mary S."],
     "2026-11-05_14-33_rctab_cvr-2022-governor.csv", ["Dunleavy/Dahlstrom"], ["Gara/Cook", "Walker/Drygas"], "Begich side"),
]
BEGICH = "Begich, Nick"


def district(label: str) -> int:
    m = re.match(r"\s*(?:House District |District |HD)?(\d+)", label)
    return int(m.group(1)) if m else -1


def side(ranks, R: set, D: set) -> int:
    skips = 0
    for v in ranks:
        if v == "undervote":
            skips += 1
            continue
        if skips >= 2:
            return 0
        skips = 0
        names = v.split("\n")
        hit = [n for n in names if n in R or n in D]
        if not hit:
            if len(names) > 1:
                return 0  # overvote among others ends the ballot
            continue
        if len(names) > 1:
            return 0  # overvote involving a named side
        return 1 if hit[0] in R else -1
    return 0


def effects(path, R, D, with_dist=False):
    cols = ["RCTab CVR Id"] + RANKS + (["Precinct Portion"] if with_dist else [])
    df = pd.read_csv(HERE / path, usecols=cols, dtype=str, keep_default_na=False)
    out = pd.DataFrame({"id": df["RCTab CVR Id"],
                        "e": [side(r, set(R), set(D)) for r in df[RANKS].itertuples(index=False)]})
    if with_dist:
        out["rural"] = df["Precinct Portion"].map(lambda s: district(s) in (37, 38, 39, 40))
    return out


def main():
    rows = []
    for label, hfile, hD, cfile, cR, cD, peltola in COMPARISONS:
        h = effects(hfile, [BEGICH], hD, with_dist=True).rename(columns={"e": "H"})
        c = effects(cfile, cR, cD).rename(columns={"e": "C"})
        m = h.merge(c, on="id")
        m["w"] = m.H - m.C
        print(f"\n{label}  (Peltola: {peltola}); matched {len(m):,}")
        for reg, d in [("Rural HD37-40", m[m.rural]), ("Everywhere else", m[~m.rural]), ("Statewide", m)]:
            n, w = len(d), int(d.w.sum())
            cross_b = int(((d.H == 1) & (d.C == -1)).sum())   # Begich and the comparison Democrat
            cross_c = int(((d.H == -1) & (d.C == 1)).sum())   # Begich's opponent and the comparison Republican
            pts = w / n * 100
            r = {"comparison": label, "peltola": peltola, "region": reg, "ballots": n, "begich_and_comp_D": cross_b,
                 "opp_and_comp_R": cross_c, "weighted": w, "points": round(pts, 2), "signed": round(-pts, 2)}
            rows.append(r)
            print(f"  {reg:16} ballots {n:>7,}  Begich+compD {cross_b:>6,}  opp+compR {cross_c:>6,}  "
                  f"weighted {w:>+7,}  points {w:,} / {n:,} x 100 == {pts:.2f}  signed {-pts:+.2f}")
    (HERE / "begich_pairwise.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
