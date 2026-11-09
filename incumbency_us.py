# /// script
# dependencies = ["pandas", "statsmodels"]
# ///
"""Step A: the US House incumbency advantage outside Alaska, in margin points (Grant, 6 Nov).

Gelman-King: margin_t == year effect + b x margin_(t-1) + c x party_(t-1) + psi x incumbency_t
  margin      D-positive two-party margin, (D - R) / (D + R) x 100, general election, regular (not special)
  party_(t-1) +1 if a Democrat won the seat last time, -1 a Republican
  incumbency  +1 a Democratic incumbent is running, -1 a Republican incumbent, 0 open seat
  psi         the incumbency advantage in margin points; the year effects take out the national wave
Incumbent status: FEC candidate summaries (weball, CAND_ICI == I), matched to the general-election candidate
by surname. Challenger quality stand-in: the general-election challenger's FEC receipts.
Sample: districts contested by both parties this time and last time, no redistricting between the two.
Data: external/medsl_2024/1976-2024-house.tab (MEDSL Dataverse, unzipped from downloads/), external/fec/weballYY.zip.
Writes incumbency_us.json. Usage: uv run incumbency_us.py
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
YEARS = [2006, 2008, 2010, 2014, 2016, 2018, 2020, 2024]  # lag year == year - 2; 2004, 2012 and 2022 follow redistricting
# state-years whose districts changed since the previous election (mid-decade redistricting)
REDRAWN = {(2006, "TX"), (2006, "GA"), (2016, "FL"), (2016, "VA"), (2016, "NC"), (2018, "PA"), (2020, "NC"),
           (2024, "AL"), (2024, "LA"), (2024, "GA"), (2024, "NC"), (2024, "NY")}
SUFFIX = {"JR", "SR", "II", "III", "IV"}


def surname_fec(name: str) -> str:
    return re.sub(r"[^A-Z ]", "", name.split(",")[0].upper()).strip()


def norm(s: str) -> str:
    return re.sub(r"[^A-Z ]", " ", str(s).upper())


def load_medsl():
    h = pd.read_csv(HERE / "external/medsl_2024/1976-2024-house.tab", encoding="latin-1", low_memory=False)
    h = h[(h.stage.str.upper() == "GEN") & (h.special.astype(str).str.upper() == "FALSE") & (h.year >= 2004)].copy()
    h["party"] = h.party.astype(str).str.upper()
    h["mode"] = h["mode"].astype(str).str.upper()
    # some states report by vote mode from 2020: use the TOTAL row where there is one, otherwise sum the modes
    has_total = h.groupby(["year", "state_po", "district", "candidate"])["mode"].transform(lambda m: (m == "TOTAL").any())
    h = h[~has_total | (h["mode"] == "TOTAL")]
    h["side"] = h.party.map({"DEMOCRAT": "D", "DEMOCRATIC-FARMER-LABOR": "D", "REPUBLICAN": "R"})
    # fusion: sum each candidate's lines; the candidate's side is the major line they carry
    cand = h.groupby(["year", "state_po", "district", "candidate"]).agg(
        votes=("candidatevotes", "sum"), sides=("side", lambda s: set(s.dropna()))).reset_index()
    cand = cand[cand.sides.map(len) == 1]
    cand["side"] = cand.sides.map(lambda s: next(iter(s)))
    # the top D and the top R in each district-year
    top = cand.sort_values("votes", ascending=False).groupby(["year", "state_po", "district", "side"]).head(1)
    w = top.pivot_table(index=["year", "state_po", "district"], columns="side", values=["votes", "candidate"], aggfunc="first")
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
        if not r[0].startswith("H") or r[4] not in ("DEM", "REP", "DFL"):
            continue
        out.append(dict(state_po=r[18], district=int(r[19] or 0), side="R" if r[4] == "REP" else "D",
                        ici=r[2], surname=surname_fec(r[1]), receipts=float(r[5] or 0)))
    return pd.DataFrame(out)


def attach_fec(w):
    years = sorted(set(w.year))
    have = {y for y in years if (HERE / f"external/fec/weball{str(y)[2:]}.zip").exists()}
    recs = []
    for y in years:
        d = w[w.year == y]
        if y not in have:
            continue
        f = load_fec(y)
        idx = {k: g for k, g in f.groupby(["state_po", "district", "side"])}
        for _, r in d.iterrows():
            row = {"year": y, "state_po": r.state_po, "district": r.district}
            for s in "DR":
                g = idx.get((r.state_po, r.district, s))
                name = norm(r[f"candidate_{s}"])
                hit = None
                if g is not None:
                    m = g[g.surname.map(lambda sn: bool(sn) and f" {sn} " in f" {name} ")]
                    if len(m):
                        hit = m.sort_values("receipts", ascending=False).iloc[0]
                row[f"ici_{s}"] = hit.ici if hit is not None else None
                row[f"rec_{s}"] = hit.receipts if hit is not None else np.nan
            recs.append(row)
    return w.merge(pd.DataFrame(recs), on=["year", "state_po", "district"], how="left")


def main():
    w = load_medsl()
    prev = w[["year", "state_po", "district", "margin"]].copy()
    prev["year"] += 2
    prev = prev.rename(columns={"margin": "lag"})
    d = w[w.year.isin(YEARS)].merge(prev, on=["year", "state_po", "district"])
    d = d[~d.apply(lambda r: (r.year, r.state_po) in REDRAWN, axis=1)]
    d = attach_fec(d)
    d["party_prev"] = np.sign(d.lag)
    d["inc"] = np.where(d.ici_D == "I", 1, 0) - np.where(d.ici_R == "I", 1, 0)
    d = d[~((d.ici_D == "I") & (d.ici_R == "I"))]  # two incumbents (rare)
    d["chal_rec"] = np.where(d.inc == 1, d.rec_R, np.where(d.inc == -1, d.rec_D, np.nan))
    d["inc_rec"] = np.where(d.inc == 1, d.rec_D, np.where(d.inc == -1, d.rec_R, np.nan))
    matched = d.ici_D.notna() & d.ici_R.notna()
    print(f"district-years contested both times, no redistricting: {len(d):,}; both candidates matched to FEC: {matched.sum():,}")
    d = d[matched]
    out = {}

    def fit(sub, label, formula="margin ~ lag + party_prev + inc + C(year)"):
        m = smf.ols(formula, data=sub).fit()
        psi, se = m.params["inc"], m.bse["inc"]
        n_inc = int((sub.inc != 0).sum()); n_open = int((sub.inc == 0).sum())
        print(f"  {label:62} n {len(sub):>5,} (incumbent {n_inc:,}, open {n_open:,})  incumbency {psi:+.2f} (se {se:.2f})  lag {m.params['lag']:.2f}")
        out[label] = dict(n=len(sub), incumbent=n_inc, open=n_open, psi=round(psi, 2), se=round(se, 2), lag=round(m.params["lag"], 3))
        return m

    print("\nAll years pooled (2006-2024 without 2012 and 2022):")
    fit(d, "all contested")
    for thr in [250_000, 500_000, 1_000_000]:
        # open seats stay in (they anchor the comparison); incumbent races need a funded challenger
        sub = d[(d.inc == 0) | (d.chal_rec >= thr)]
        fit(sub, f"challenger raised >= ${thr:,.0f}")
    sub = d[(d.inc == 0) | (d.chal_rec >= 0.5 * d.inc_rec)]
    fit(sub, "challenger raised >= half the incumbent")
    sub = d[(d.inc == 0) | (d.lag.abs() <= 25)]
    fit(sub, "last margin within 25 (Alaska panel rule)")
    print("\nRecent era, 2014-2024:")
    r = d[d.year >= 2014]
    fit(r, "2014-2024 all contested")
    fit(r[(r.inc == 0) | (r.lag.abs() <= 25)], "2014-2024 last margin within 25")
    fit(r[(r.inc == 0) | (r.chal_rec >= 500_000)], "2014-2024 challenger >= $500k")
    fit(r[(r.inc == 0) | (r.chal_rec >= 0.5 * r.inc_rec)], "2014-2024 challenger >= half the incumbent")

    print("\nBy year (all contested / challenger raised >= $500k):")
    for y in YEARS:
        dy = d[d.year == y]
        fit(dy, f"{y} all contested", "margin ~ lag + party_prev + inc")
        fit(dy[(dy.inc == 0) | (dy.chal_rec >= 500_000)], f"{y} challenger >= $500k", "margin ~ lag + party_prev + inc")

    print("\n2018 split by incumbent party (D-positive; a Republican incumbent's advantage shows as -inc_R):")
    dy = d[d.year == 2018].copy()
    dy["inc_D"] = (dy.inc == 1).astype(int); dy["inc_R"] = (dy.inc == -1).astype(int)
    for label, sub in [("2018 all contested", dy), ("2018 challenger >= $500k", dy[(dy.inc == 0) | (dy.chal_rec >= 500_000)])]:
        m = smf.ols("margin ~ lag + party_prev + inc_D + inc_R", data=sub).fit()
        print(f"  {label:30} Democratic incumbents {m.params['inc_D']:+.2f} (se {m.bse['inc_D']:.2f}); Republican incumbents {m.params['inc_R']:+.2f} (se {m.bse['inc_R']:.2f}), n {len(sub):,}")
        out[label + " by party"] = dict(inc_D=round(m.params["inc_D"], 2), se_D=round(m.bse["inc_D"], 2),
                                         inc_R=round(m.params["inc_R"], 2), se_R=round(m.bse["inc_R"], 2), n=len(sub))
    (HERE / "incumbency_us.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
