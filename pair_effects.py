# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2"]
# ///
"""Pair effects against a generic line drawn on the same ballots: each statewide race's two-way margin
minus the clean (one Democrat, one Republican) state legislative race on those exact ballots.

No lean, beta or national-wave model is needed: the legislative race supplies the generic party vote of
the same voters. A pair effect is the Democrat's effect plus the Republican's (D positive). Split into
rural House districts 37-40 and everywhere else.

Statewide races (two-way, Alaska ranked-choice rules via rcv.assign):
  2022  House final Peltola-Palin; House head to head Peltola-Begich; governor head to head Gara-Dunleavy
  2024  House final Peltola-Begich; president Harris-Trump
  2026  House final Hill-Begich; Senate final Peltola-Sullivan; governor first choice Kreiss-Tomkins
        against the three Republicans combined

Usage: uv run pair_effects.py   (needs the RCTab CVR exports listed below and the Dominion folders).
Writes pair_effects.json.
"""
import os
import json
from pathlib import Path

import pandas as pd

import project
import rcv
from legislative import leg_first

HERE = Path(__file__).parent
DL = Path(os.environ.get("AK_DATA_DIR", "data"))
RACES = {
    2022: [("House final, Peltola − Palin", "2026-11-05_14-31_rctab_cvr-2022-house.csv", "Peltola", "Palin", "two"),
           ("House head to head, Peltola − Begich", "2026-11-05_14-31_rctab_cvr-2022-house.csv", "Peltola", "Begich", "two"),
           ("Governor head to head, Gara − Dunleavy", "2026-11-05_14-33_rctab_cvr-2022-governor.csv", "Gara", "Dunleavy", "two")],
    2024: [("House final, Peltola − Begich", "2026-11-04_23-29_rctab_cvr.csv", "Peltola", "Begich", "two"),
           ("President, Harris − Trump", "2026-11-05_14-34_rctab_cvr-2024-president.csv", "Harris", "Trump", "two")],
    2026: [("House final, Hill − Begich", "2026-11-04_23-33_rctab_cvr.csv", "Hill", "Begich", "two"),
           ("Senate final, Peltola − Sullivan", "2026-11-05_00-56_rctab_cvr-senate.csv", "Peltola, Mary", "Sullivan, Dan S.", "two"),
           ("Governor first choice, Kreiss-Tomkins − Republicans", "2026-11-05_14-36_rctab_cvr-2026-governor.csv", "Kreiss-Tomkins", ("Wilson", "Bronson", "Taylor"), "bloc")],
}
norm = lambda r: rcv.SKIP if r == "undervote" else (rcv.OVER if "\n" in r else r)


def sides(path: Path, d, r, mode) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    cols = [c for c in df.columns if c.startswith("Rank ")]
    names = {v for c in cols for v in df[c].unique() if v != "undervote" and "\n" not in v}
    is_d = lambda n: n.startswith(d)
    is_r = (lambda n: n.startswith(r)) if isinstance(r, str) else (lambda n: n.startswith(r))
    elim = names - {n for n in names if is_d(n) or is_r(n)} if mode == "two" else set()
    out = []
    for row in df[cols].itertuples(index=False):
        a = rcv.assign(tuple(norm(v) for v in row), elim)
        out.append("D" if is_d(a) else ("R" if is_r(a) else "x"))
    return pd.DataFrame({"RCTab CVR Id": df["RCTab CVR Id"], "race": out, "loc": df["Precinct Portion"]})


def margin(s: pd.Series) -> tuple[float, int]:
    n = s.value_counts()
    d, r = n.get("D", 0), n.get("R", 0)
    return (d - r) / (d + r) * 100, d + r


def main() -> None:
    results = []
    for year, races in RACES.items():
        L0 = leg_first(DL / f"alaska-{year}")
        L0 = L0[L0.leg_first.isin(["D", "R"])]
        print(f"\n== {year}: clean legislative contests {sorted(L0[L0.clean].contest_name.unique())}")
        for label, f, d, r, mode in races:
            S = sides(HERE / f, d, r, mode)
            m0 = L0.merge(S, on="RCTab CVR Id")
            m0 = m0[m0.race.isin(["D", "R"])]
            m0["dist"] = m0["loc"].str.extract(r"^(?:House District |District |HD)?(\d+)", expand=False).astype(float)
            rural = m0.dist.isin([37, 38, 39, 40])
            m = m0[m0.clean]
            for region, sub in [("Clean, all", m), ("Contested, rural", m0[m0.contested & rural]), ("Contested, other", m0[m0.contested & ~rural])]:
                if len(sub) < 200:
                    continue
                rm, n = margin(sub.race)
                lm, _ = margin(sub.leg_first)
                results.append({"year": year, "race": label, "region": region, "ballots": int(n),
                                "race_margin": round(rm, 2), "legislative_margin": round(lm, 2), "pair_effect": round(rm - lm, 2)})
                print(f"  {label:52} {region:14} ballots {n:>7,}  race {rm:+7.2f}  legislative {lm:+7.2f}  "
                      f"pair effect {rm:+.2f} − ({lm:+.2f}) == {rm - lm:+.2f}")
    (HERE / "pair_effects.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
