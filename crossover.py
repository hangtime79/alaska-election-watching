# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2"]
# ///
"""House vs Senate on the same physical ballots (joined on RCTab CVR Id), 2026.

Usage: uv run crossover.py [HOUSE_CVR] [SENATE_CVR] [HOUSE_2024_FINAL]
Prints: final-round House x Senate crosstab, the decomposition of the House-vs-Senate margin gap,
first-choice crosstab, Hill vs Peltola by vote type and district, and Peltola 2024 House vs 2026 Senate
at the same locations. Writes crossover_2026.csv (one row per ballot).
Elimination sets are taken from the full-count rounds (rcv.py); re-check them if the order changes.
"""
import json
import sys
from pathlib import Path

import pandas as pd

import project
import rcv

HERE = Path(__file__).parent
HOUSE = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "2026-11-04_23-33_rctab_cvr.csv"
SENATE = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "2026-11-05_00-56_rctab_cvr-senate.csv"
H2024 = Path(sys.argv[3]) if len(sys.argv) > 3 else HERE / "2026-11-04_23-29_rctab_cvr.csv"
ELIM_H = {"Write-in", 'McDermott, James C. "Jim"', "Hafner, Eric"}
ELIM_S = {"Write-in", "Sullivan, Daniel J. Jr.", "Heikes, Gerald L."}
ELIM_H24 = {"Write-in", "Hafner, Eric", "Howe, John Wayne"}
DONE = "No more rankings"


def norm(r):
    return rcv.SKIP if r == "undervote" else (rcv.OVER if "\n" in r else r)


def short(x: str) -> str:
    if x.startswith("inactive"):
        return DONE
    return {"Sullivan, Dan S.": "Sullivan", "Sullivan, Daniel J. Jr.": "Sullivan Jr."}.get(x, x.split(",")[0])


def ranks(df, suffix=""):
    return [tuple(norm(r) for r in row) for row in df[[c + suffix for c in rcv.RANKS]].itertuples(index=False)]


def share(df, col, a, b):
    x = df[col].value_counts()
    return x.get(a, 0) / (x.get(a, 0) + x.get(b, 0)) * 100


def main() -> None:
    pd.set_option("display.width", 200)
    h = pd.read_csv(HOUSE, dtype=str, keep_default_na=False)
    s = pd.read_csv(SENATE, dtype=str, keep_default_na=False)
    m = h.merge(s[["RCTab CVR Id", *rcv.RANKS]], on="RCTab CVR Id", suffixes=("", "_s"))
    print(f"House {len(h):,}  Senate {len(s):,}  matched {len(m):,}")
    hr, sr = ranks(m), ranks(m, "_s")
    m["H1"] = [short(rcv.assign(t, set())) for t in hr]
    m["HF"] = [short(rcv.assign(t, ELIM_H)) for t in hr]
    m["S1"] = [short(rcv.assign(t, set())) for t in sr]
    m["SF"] = [short(rcv.assign(t, ELIM_S)) for t in sr]
    m["vt"] = m["Precinct Portion"].map(project.vote_type)
    m["dist"] = m["Precinct Portion"].str.extract(r"^(?:House District |District |HD)?(\d+)", expand=False).astype(int)

    x = pd.crosstab(m.HF, m.SF)
    print("\n== Final round, House x Senate\n", pd.crosstab(m.HF, m.SF, margins=True).to_string())
    g = lambda r, c: int(x.loc[r, c]) if r in x.index and c in x.columns else 0
    split = 2 * (g("Begich", "Peltola") - g("Hill", "Sullivan"))
    h_done = g(DONE, "Peltola") - g(DONE, "Sullivan")
    s_done = g("Begich", DONE) - g("Hill", DONE)
    hm = (m.HF == "Begich").sum() - (m.HF == "Hill").sum()
    sm = (m.SF == "Sullivan").sum() - (m.SF == "Peltola").sum()
    print(f"\nHouse margin (Begich-Hill) {hm:,}  Senate margin (Sullivan-Peltola) {sm:,}  gap {hm - sm:,}")
    print(f"  split tickets 2 x ({g('Begich','Peltola'):,} - {g('Hill','Sullivan'):,}) = {split:,}")
    print(f"  House ballots with no more rankings: Peltola {g(DONE,'Peltola'):,} - Sullivan {g(DONE,'Sullivan'):,} = {h_done:,}")
    print(f"  Senate ballots with no more rankings: Begich {g('Begich',DONE):,} - Hill {g('Hill',DONE):,} = {s_done:,}")
    print(f"  sum {split + h_done + s_done:,}")

    print("\n== First choice, House x Senate\n", pd.crosstab(m.H1, m.S1, margins=True).to_string())
    vt = pd.DataFrame([(k, len(d), share(d, "HF", "Hill", "Begich"), share(d, "SF", "Peltola", "Sullivan")) for k, d in m.groupby("vt")],
                      columns=["vote_type", "ballots", "hill_final", "peltola_final"]).round(1)
    print("\n== Final-round share by vote type\n", vt.to_string(index=False))
    d = pd.DataFrame([(k, len(g_), share(g_, "HF", "Hill", "Begich"), share(g_, "SF", "Peltola", "Sullivan")) for k, g_ in m.groupby("dist")],
                     columns=["district", "ballots", "hill_final", "peltola_final"]).round(1)
    d["peltola_minus_hill"] = (d.peltola_final - d.hill_final).round(1)
    print("\n== Final-round share by House district\n", d.sort_values("peltola_minus_hill").to_string(index=False))
    m[["RCTab CVR Id", "vt", "dist", "H1", "HF", "S1", "SF"]].to_csv(HERE / "crossover_2026.csv", index=False)
    out = {
        "ballots": len(m),
        "final": {r: {c: g(r, c) for c in ["Peltola", "Sullivan", DONE]} for r in ["Begich", "Hill", DONE]},
        "house_margin": int(hm), "senate_margin": int(sm),
        "decomp": {"split": split, "house_done": h_done, "senate_done": s_done},
        "hafner_peltola": int(((m.H1 == "Hafner") & (m.S1 == "Peltola")).sum()),
        "r1": {"Peltola": int((m.S1 == "Peltola").sum()), "Hill": int((m.H1 == "Hill").sum())},
        "vote_type": vt.to_dict("records"),
        "district": d.sort_values("district").to_dict("records"),
    }

    # Peltola 2024 House vs 2026 Senate, same locations, final round
    p = pd.read_csv(H2024, usecols=["Precinct Portion", *rcv.RANKS], dtype=str, keep_default_na=False)
    p["F"] = [short(rcv.assign(t, ELIM_H24)) for t in ranks(p)]
    p["loc"] = p["Precinct Portion"].str.replace(r"\s+", " ", regex=True).str.strip()
    p["vt"] = p["Precinct Portion"].map(project.vote_type)
    m["loc"] = m["Precinct Portion"].str.replace(r"\s+", " ", regex=True).str.strip()
    p = p[p["loc"].isin(set(m["loc"]))]
    print(f"\n== Peltola final-round share, same locations: 2024 House {share(p,'F','Peltola','Begich'):.2f}%  2026 Senate {share(m,'SF','Peltola','Sullivan'):.2f}%")
    out["peltola_same_loc"] = [{"vote_type": "All", "h2024": round(share(p, "F", "Peltola", "Begich"), 2), "s2026": round(share(m, "SF", "Peltola", "Sullivan"), 2)}]
    for t in ["Election Day", "Early Voting", "Absentee"]:
        a, b = share(p[p.vt == t], "F", "Peltola", "Begich"), share(m[m.vt == t], "SF", "Peltola", "Sullivan")
        out["peltola_same_loc"].append({"vote_type": t, "h2024": round(a, 2), "s2026": round(b, 2)})
        print(f"  {t:13s} 2024 House {a:.1f}%  2026 Senate {b:.1f}%")
    (HERE / "crossover.json").write_text(json.dumps(out, indent=1, default=int))


if __name__ == "__main__":
    main()
