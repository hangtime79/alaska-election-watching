# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2"]
# ///
"""2024 on the same ballots: Peltola - Begich (House) against Harris - Trump (president).

Joins the 2024 final House CVR and the 2024 presidential CVR on RCTab CVR Id. Both final rounds use
Alaska's ranked-choice rules (rcv.assign); the presidential final round eliminates everyone but
Harris and Trump. Premium == House two-way margin - presidential two-way margin, D positive.

Prints: the ballot-level crosstab, where the premium comes from (Trump voters choosing Peltola, Harris
voters choosing Begich, ballots that stop before one final round), and the premium by vote type and by
House district. Writes ballot_2024.json.

Usage: uv run ballot_2024.py [HOUSE_2024] [PRESIDENT_2024]
"""
import json
import sys
from pathlib import Path

import pandas as pd

import project
import rcv

HERE = Path(__file__).parent
HOUSE = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "2026-11-04_23-29_rctab_cvr.csv"
PRES = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "2026-11-05_14-34_rctab_cvr-2024-president.csv"
ELIM_H = {"Write-in", "Hafner, Eric", "Howe, John Wayne"}
DONE = "No more rankings"


def final(df: pd.DataFrame, eliminated: set) -> list[str]:
    cols = [c for c in df.columns if c.startswith("Rank ")]
    norm = lambda r: rcv.SKIP if r == "undervote" else (rcv.OVER if "\n" in r else r)
    out = []
    for row in df[cols].itertuples(index=False):
        a = rcv.assign(tuple(norm(r) for r in row), eliminated)
        out.append(DONE if a.startswith("inactive") else a.split(",")[0].split("/")[0])
    return out


def two_way(s: pd.Series, d: str, r: str) -> float:
    n = s.value_counts()
    return (n.get(d, 0) - n.get(r, 0)) / (n.get(d, 0) + n.get(r, 0)) * 100


def main() -> None:
    pd.set_option("display.width", 200)
    h = pd.read_csv(HOUSE, dtype=str, keep_default_na=False)
    p = pd.read_csv(PRES, dtype=str, keep_default_na=False)
    pres_all = set(v for c in p.columns if c.startswith("Rank ") for v in p[c].unique()) - {"undervote", "Harris/Walz", "Trump/Vance"}
    h["HF"] = final(h, ELIM_H)
    p["PF"] = final(p, {v for v in pres_all if "\n" not in v})
    m = h[["RCTab CVR Id", "Precinct Portion", "HF"]].merge(p[["RCTab CVR Id", "PF"]], on="RCTab CVR Id")
    print(f"House {len(h):,}  President {len(p):,}  matched {len(m):,}")
    m["vt"] = m["Precinct Portion"].map(project.vote_type)
    m["dist"] = m["Precinct Portion"].str.extract(r"^(?:House District |District |HD)?(\d+)", expand=False).astype(int)

    x = pd.crosstab(m.HF, m.PF, margins=True)
    print("\n== Final round, House x President\n", x.to_string())

    hm, pm = two_way(m.HF, "Peltola", "Begich"), two_way(m.PF, "Harris", "Trump")
    print(f"\nPeltola - Begich {hm:+.2f}   Harris - Trump {pm:+.2f}   premium {hm:+.2f} - ({pm:+.2f}) == {hm - pm:+.2f}")

    # Where the premium comes from, in votes (D positive): each cell moves the House margin relative to the presidential one
    g = lambda r, c: int(x.loc[r, c]) if r in x.index and c in x.columns else 0
    parts = {
        "Trump voters choosing Peltola (x2)": 2 * g("Peltola", "Trump"),
        "Harris voters choosing Begich (x2)": -2 * g("Begich", "Harris"),
        "Trump voters with no House final-round vote": g(DONE, "Trump"),
        "Harris voters with no House final-round vote": -g(DONE, "Harris"),
        "Peltola voters with no presidential final-round vote": g("Peltola", DONE),
        "Begich voters with no presidential final-round vote": -g("Begich", DONE),
    }
    hv = (m.HF == "Peltola").sum() - (m.HF == "Begich").sum()
    pv = (m.PF == "Harris").sum() - (m.PF == "Trump").sum()
    print(f"\nHouse margin {hv:,} votes, presidential margin {pv:,}, gap {hv - pv:,}")
    for k, v in parts.items():
        print(f"  {k:55} {v:+,}")
    print(f"  {'sum':55} {sum(parts.values()):+,}")

    by = lambda key: pd.DataFrame([(k, len(d), two_way(d.HF, "Peltola", "Begich"), two_way(d.PF, "Harris", "Trump"),
                                    (d.PF == "Trump").sum() and ((d.PF == "Trump") & (d.HF == "Peltola")).sum() / (d.PF == "Trump").sum() * 100,
                                    (d.PF == "Harris").sum() and ((d.PF == "Harris") & (d.HF == "Begich")).sum() / (d.PF == "Harris").sum() * 100)
                                   for k, d in m.groupby(key)],
                                  columns=[key, "ballots", "house", "president", "trump_to_peltola_pct", "harris_to_begich_pct"])
    for key in ("vt", "dist"):
        t = by(key)
        t["premium"] = t.house - t.president
        t = t.round(2)
        print(f"\n== By {'vote type' if key == 'vt' else 'House district'}\n", t.sort_values("premium", ascending=False).to_string(index=False))
        if key == "dist":
            dist = t
    w = dist.ballots
    c = dist[["premium", "president"]].corr().iloc[0, 1]
    print(f"\nDistrict premium vs presidential margin: correlation {c:.2f}")
    out = {"matched": len(m), "house_margin": round(hm, 2), "president_margin": round(pm, 2), "premium": round(hm - pm, 2),
           "parts_votes": parts, "by_district": dist.to_dict(orient="records")}
    (HERE / "ballot_2024.json").write_text(json.dumps(out, indent=1, default=int))


if __name__ == "__main__":
    main()
