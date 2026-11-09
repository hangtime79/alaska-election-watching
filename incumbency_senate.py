# /// script
# dependencies = ["pandas", "statsmodels"]
# ///
"""Step A, Senate: the US Senate incumbency advantage outside Alaska, in margin points (Grant, 6 Nov).

Same Gelman-King form as incumbency_us.py, one row per state-race:
  margin_t == year effect + b x margin_(t-6) + c x party_(t-6) + psi x incumbency_t
  margin_(t-6) is the same seat's previous regular election (a regular race six years earlier in the
  same state is the same Senate class). Specials are left out on both sides.
  Where a runoff decided the race (Georgia), the runoff is used.
Incumbent status and receipts: FEC candidate summaries (weball, CAND_ICI), matched by state, party and surname.
Races without both a Democrat and a Republican (Sanders, King, McMullin, top-two D-on-D) drop out.
Data: external/medsl_senate/1976-2024-senate-state.csv (MEDSL Dataverse, from downloads/), external/fec/.
Writes incumbency_senate.json. Usage: uv run incumbency_senate.py
"""
import csv
import io
import json
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

HERE = Path(__file__).parent
YEARS = list(range(2006, 2026, 2))


def norm(s):
    return re.sub(r"[^A-Z ]", " ", str(s).upper())


def load_medsl():
    s = pd.read_csv(HERE / "external/medsl_senate/1976-2024-senate-state.csv", encoding="latin-1", low_memory=False)
    s["stage"] = s.stage.str.lower()
    s = s[s.stage.isin(["gen", "runoff", "gen runoff"]) & (s.special.astype(str).str.lower() == "false") & (s.year >= 2000)].copy()
    s["is_runoff"] = s.stage != "gen"
    # keep the deciding stage: the runoff where one exists
    has_run = s.groupby(["year", "state_po"]).is_runoff.transform("any")
    s = s[~has_run | s.is_runoff]
    s["side"] = s.party_simplified.map({"DEMOCRAT": "D", "REPUBLICAN": "R"})
    cand = s.groupby(["year", "state_po", "candidate"]).agg(
        votes=("candidatevotes", "sum"), sides=("side", lambda x: set(x.dropna()))).reset_index()
    cand = cand[cand.sides.map(len) == 1]
    cand["side"] = cand.sides.map(lambda x: next(iter(x)))
    top = cand.sort_values("votes", ascending=False).groupby(["year", "state_po", "side"]).head(1)
    w = top.pivot_table(index=["year", "state_po"], columns="side", values=["votes", "candidate"], aggfunc="first")
    w.columns = [f"{a}_{b}" for a, b in w.columns]
    w = w.reset_index().dropna(subset=["votes_D", "votes_R"])
    w = w[(w.votes_D > 0) & (w.votes_R > 0)]
    w["margin"] = (w.votes_D - w.votes_R) / (w.votes_D + w.votes_R) * 100
    return w


def load_fec(year):
    z = zipfile.ZipFile(HERE / f"external/fec/weball{str(year)[2:]}.zip")
    rows = list(csv.reader(io.TextIOWrapper(z.open(z.namelist()[0]), encoding="latin-1"), delimiter="|"))
    out = []
    for r in rows:
        if not r[0].startswith("S") or r[4] not in ("DEM", "REP", "DFL"):
            continue
        out.append(dict(state_po=r[18], side="R" if r[4] == "REP" else "D", ici=r[2],
                        surname=re.sub(r"[^A-Z ]", "", r[1].split(",")[0].upper()).strip(), receipts=float(r[5] or 0)))
    return pd.DataFrame(out)


def main():
    w = load_medsl()
    prev = w[["year", "state_po", "margin"]].copy()
    prev["year"] += 6
    prev = prev.rename(columns={"margin": "lag"})
    d = w[w.year.isin(YEARS)].merge(prev, on=["year", "state_po"])
    recs = []
    for y in YEARS:
        f = load_fec(y)
        idx = {k: g for k, g in f.groupby(["state_po", "side"])}
        for _, r in d[d.year == y].iterrows():
            row = {"year": y, "state_po": r.state_po}
            for sd in "DR":
                g = idx.get((r.state_po, sd))
                name = norm(r[f"candidate_{sd}"])
                hit = None
                if g is not None:
                    m = g[g.surname.map(lambda sn: bool(sn) and f" {sn} " in f" {name} ")]
                    if len(m):
                        hit = m.sort_values("receipts", ascending=False).iloc[0]
                row[f"ici_{sd}"] = hit.ici if hit is not None else None
                row[f"rec_{sd}"] = hit.receipts if hit is not None else np.nan
            recs.append(row)
    d = d.merge(pd.DataFrame(recs), on=["year", "state_po"])
    print(f"Senate races contested both times (regular, same class): {len(d):,}; both matched to FEC: {(d.ici_D.notna() & d.ici_R.notna()).sum():,}")
    d = d[d.ici_D.notna() & d.ici_R.notna()].copy()
    d["party_prev"] = np.sign(d.lag)
    d["inc"] = np.where(d.ici_D == "I", 1, 0) - np.where(d.ici_R == "I", 1, 0)
    d = d[~((d.ici_D == "I") & (d.ici_R == "I"))]
    d["chal_rec"] = np.where(d.inc == 1, d.rec_R, np.where(d.inc == -1, d.rec_D, np.nan))
    d["inc_rec"] = np.where(d.inc == 1, d.rec_D, np.where(d.inc == -1, d.rec_R, np.nan))
    out = {}

    def fit(sub, label):
        m = smf.ols("margin ~ lag + party_prev + inc + C(year)", data=sub).fit()
        psi, se = m.params["inc"], m.bse["inc"]
        ni, no = int((sub.inc != 0).sum()), int((sub.inc == 0).sum())
        print(f"  {label:52} n {len(sub):>4} (incumbent {ni}, open {no})  incumbency {psi:+.2f} (se {se:.2f})  lag {m.params['lag']:.2f}")
        out[label] = dict(n=len(sub), incumbent=ni, open=no, psi=round(psi, 2), se=round(se, 2))

    for era, sub in [("2006-2024", d), ("2014-2024", d[d.year >= 2014])]:
        print(f"\n{era}:")
        fit(sub, f"{era} all contested")
        fit(sub[(sub.inc == 0) | (sub.lag.abs() <= 25)], f"{era} last margin within 25")
        fit(sub[(sub.inc == 0) | (sub.chal_rec >= 2_000_000)], f"{era} challenger >= $2M")
        fit(sub[(sub.inc == 0) | (sub.chal_rec >= 5_000_000)], f"{era} challenger >= $5M")
        fit(sub[(sub.inc == 0) | (sub.chal_rec >= 0.5 * sub.inc_rec)], f"{era} challenger >= half the incumbent")
    print("\nAlaska rows in the sample:")
    print(d[d.state_po == "AK"][["year", "candidate_D", "candidate_R", "margin", "lag", "inc", "chal_rec"]].to_string(index=False))
    (HERE / "incumbency_senate.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
