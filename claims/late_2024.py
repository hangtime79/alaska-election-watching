# Run from the repo root: uv run --with pandas python claims/late_2024.py
"""2024 House late-arriving ballots against early-counted ones, same ballot type, same districts.

For every ballot in the 2024 final CVR: its final-round side (Peltola or Begich, the first of the two
it ranks), its vote type and district, and whether it was already counted in the 10 Nov 2024 export.
Two-way margin (Peltola - Begich) / (Peltola + Begich), D-positive, for ballots in by 10 Nov against
ballots counted later. The gap is computed within each district and weighted by the late ballots, so
the comparison holds the district mix fixed. Needs 2026-11-04_23-57_rctab_cvr.csv (gitignored; five
2024 exports tabulated together).
"""
import re
import sys
import pandas as pd

sys.path.insert(0, '.')
F = "2026-11-04_23-57_rctab_cvr.csv"
RANKS = [f"Rank {i}" for i in range(1, 6)]


def side(row):
    for v in row:
        if v == "undervote":
            continue
        names = v.split("\n")
        hit = [n for n in names if n.startswith(("Begich", "Peltola"))]
        if len(names) > 1:
            return "stop" if hit else None if False else ("stop" if hit else "skipover")
        if hit:
            return "P" if hit[0].startswith("Peltola") else "B"
    return "stop"


def main():
    df = pd.read_csv(F, usecols=["Source Filepath", "RCTab CVR Id", "Precinct Portion", *RANKS], dtype=str, keep_default_na=False)
    src = df["Source Filepath"]
    snap10 = set(df.loc[src.str.contains("20241110"), "RCTab CVR Id"])
    fin = df[src.str.endswith("alaska-2024")].copy()
    loc = fin["Precinct Portion"].str.replace(r"\s+", " ", regex=True).str.strip()
    fin["district"] = loc.str.extract(r"^(?:House District |District |HD)?(\d+)", expand=False).astype(float)
    fin["vt"] = loc.map(lambda s: "Election Day" if re.match(r"^\d+-\d+ ", s) else "Judicial-split" if "Judicial District" in s else s.split(" - ")[-1] if " - " in s else s)
    fin["side"] = fin[RANKS].apply(lambda r: side(list(r)), axis=1)
    fin["in10"] = fin["RCTab CVR Id"].isin(snap10)
    print(f"final ballots {len(fin):,}; 10 Nov ballots {len(snap10):,}; final ballots found in 10 Nov {fin.in10.sum():,}")
    for vt in ["Early Voting", "Absentee", "Election Day"]:
        d = fin[fin.vt == vt]
        def m(x):
            p, b = (x.side == "P").sum(), (x.side == "B").sum()
            return p, b, (p - b) / (p + b) * 100 if p + b else float("nan")
        pi, bi, mi = m(d[d.in10]); po, bo, mo = m(d[~d.in10])
        rows = []
        for dist, g in d.groupby("district"):
            a, b_ = g[g.in10], g[~g.in10]
            if len(a) == 0 or len(b_) == 0:
                continue
            _, _, ma = m(a); po_, bo_, mb = m(b_)
            rows.append((dist, po_ + bo_, mb - ma))
        w = sum(r[1] for r in rows)
        gap_w = sum(r[1] * r[2] for r in rows) / w if w else float("nan")
        print(f"{vt:13} in10 {len(d[d.in10]):6,} two-way {pi+bi:6,} margin {mi:+6.2f} | later {len(d[~d.in10]):6,} two-way {po+bo:6,} margin {mo:+6.2f} | raw gap {mo-mi:+6.2f} | district-weighted gap {gap_w:+6.2f} ({len(rows)} districts, {w:,} late two-way)")
        print(f"{'':13} share counted by 10 Nov: {len(d[d.in10]) / len(d):.1%}")


main()
