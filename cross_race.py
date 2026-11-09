# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2"]
# ///
"""Cross-race check for the 2026 count: read the House and Senate final rounds off every race's first choices.

On the CVR's ballots, each first-choice group (say, Kreiss-Tomkins voters for governor) has a known net
final-round vote in the House and Senate (D side +1, R side -1, no more rankings 0). Applying those rates
to a new batch's first-choice mix gives three independent reads of the batch's House and Senate final
rounds, one per race. If they agree, the late ballots are behaving like the counted ones; if one race
disagrees, something candidate-specific is happening.

Rates must be taken within vote type. Fitted across vote types, the same first-choice group behaves
differently (early-vote Kreiss-Tomkins voters are more loyal to Peltola than election-day ones) and the
cross-race reads miss by 2-6 points. Fitted within vote type and tested on held-out districts (odd vs
even), they miss by under about 1 point (about 2 for House final from absentee ballots, a small group).

Sign convention: positive is Democratic side (Hill, Peltola), negative is Republican (Begich, Sullivan).

Usage:
  uv run cross_race.py                      # calibration + leave-one-vote-type-out test
  uv run cross_race.py --release REL.json   # also project from an official release

REL.json holds first-choice totals from an official results release by vote type, keyed by the short
names printed below:
  {"house": {"Absentee": {"Begich": ..., "Hill": ...}, "Early Voting": {...}, "Election Day": {...}},
   "senate": {...}, "governor": {...}}
Use "All" as the vote type for a statewide-only figure (then all-ballot rates are used: less accurate).
The batch is the release minus the CVR's first choices of the same vote type.

Needs crossover_2026.csv (from crossover.py) and the 2026 governor CVR.
"""
import argparse
import json
from pathlib import Path

import pandas as pd

import rcv

HERE = Path(__file__).parent
GOV = HERE / "2026-11-05_14-36_rctab_cvr-2026-governor.csv"
D_SIDE, R_SIDE = {"Hill", "Peltola"}, {"Begich", "Sullivan"}
SOURCES = {"house": "H1", "senate": "S1", "governor": "G1"}
TARGETS = {"House final": "HF", "Senate final": "SF"}
NOT_A_CHOICE = ("No more rankings", "inactive")


def load() -> pd.DataFrame:
    x = pd.read_csv(HERE / "crossover_2026.csv", dtype=str, keep_default_na=False)
    g = pd.read_csv(GOV, dtype=str, keep_default_na=False)
    norm = lambda r: rcv.SKIP if r == "undervote" else (rcv.OVER if "\n" in r else r)
    g["G1"] = [rcv.assign(tuple(norm(v) for v in row), set()) for row in g[rcv.RANKS].itertuples(index=False)]
    g["G1"] = g["G1"].map(lambda s: "No more rankings" if s.startswith("inactive") else s.split("/")[0])
    m = x.merge(g[["RCTab CVR Id", "G1"]], on="RCTab CVR Id", how="left").fillna({"G1": "No more rankings"})
    for col in TARGETS.values():
        m[col + "_net"] = m[col].map(lambda c: 1 if c in D_SIDE else (-1 if c in R_SIDE else 0))
        m[col + "_two"] = m[col + "_net"].abs()
    return m


def rates(df: pd.DataFrame, src: str) -> pd.DataFrame:
    d = df[~df[src].str.startswith(NOT_A_CHOICE)]
    return d.groupby(src)[[c + s for c in TARGETS.values() for s in ("_net", "_two")]].mean()


def choices(df: pd.DataFrame, src: str) -> pd.Series:
    return df[src][~df[src].str.startswith(NOT_A_CHOICE)].value_counts()


def predict(mix: pd.Series, r: pd.DataFrame, tgt: str) -> tuple[float, float]:
    """Net D-minus-R final-round votes and two-way final-round votes for a first-choice mix (counts)."""
    r = r.reindex(mix.index).fillna(0)
    return float((mix * r[tgt + "_net"]).sum()), float((mix * r[tgt + "_two"]).sum())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", type=Path)
    args = ap.parse_args()
    m = load()

    print("== Calibration: net final-round vote per first-choice voter (D +1, R -1), all CVR ballots")
    for race, src in SOURCES.items():
        r = rates(m, src)
        n = m[src].value_counts()
        print(f"\n{race} first choice")
        print(pd.DataFrame({"ballots": n.reindex(r.index), "House final net": r["HF_net"].round(3),
                            "Senate final net": r["SF_net"].round(3)}).sort_values("ballots", ascending=False).to_string())

    print("\n== Test: within each vote type, fit on odd districts and predict even, and the reverse"
          " (error in two-way final margin, points)")
    m["dist"] = m["dist"].astype(int)
    rows = []
    for vt in ["Election Day", "Early Voting", "Absentee"]:
        d = m[m.vt == vt]
        for half in (0, 1):
            test, fit = d[d.dist % 2 == half], d[d.dist % 2 != half]
            for tname, tgt in TARGETS.items():
                actual = test[tgt + "_net"].sum() / test[tgt + "_two"].sum() * 100
                row = {"vote type": vt, "held out": "odd" if half else "even", "target": tname, "actual": round(actual, 2)}
                for race, src in SOURCES.items():
                    net, two = predict(choices(test, src), rates(fit, src), tgt)
                    row[f"err {race}"] = round(net / two * 100 - actual, 2)
                rows.append(row)
    print(pd.DataFrame(rows).to_string(index=False))

    if args.release:
        rel = json.loads(args.release.read_text())
        print(f"\n== Projection from {args.release.name} (batch == release - CVR first choices, by vote type)")
        base = {tname: (m[tgt + "_net"].sum(), m[tgt + "_two"].sum()) for tname, tgt in TARGETS.items()}
        out = []
        for race, src in SOURCES.items():
            if race not in rel:
                continue
            row = {"read from": race, "batch first choices": 0}
            add = {tname: [0.0, 0.0] for tname in TARGETS}
            for vt, totals in rel[race].items():
                pool = m if vt == "All" else m[m.vt == vt]
                cvr = choices(pool, src)
                batch = (pd.Series(totals, dtype=float) - cvr.reindex(list(totals)).fillna(0)).clip(lower=0)
                row["batch first choices"] += int(batch.sum())
                r = rates(pool, src)
                for tname, tgt in TARGETS.items():
                    net, two = predict(batch, r, tgt)
                    add[tname][0] += net
                    add[tname][1] += two
            for tname in TARGETS:
                net, two = add[tname]
                bn, bt = base[tname]
                row[f"{tname}: batch margin"] = round(net / two * 100, 2) if two else None
                row[f"{tname}: total margin"] = round((bn + net) / (bt + two) * 100, 2)
                row[f"{tname}: total votes"] = round(bn + net)
            out.append(row)
        print(pd.DataFrame(out).T.to_string(header=False))

if __name__ == "__main__":
    main()
