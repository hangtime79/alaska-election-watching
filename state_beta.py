# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2", "pandas", "rdata"]
# ///
"""Step B: every state's beta (elasticity) and lean drift from statewide races 2000-2024 (Grant, 6 Nov).

  margin == lean_state + downballot_state x [not president] + drift_state x cycles_since_2000
            + (beta_mean + beta_dev_state) x national_wave + incumbency x inc
            + Democratic candidate effect + Republican candidate effect

  margin        D% - R% of all votes cast in the race (D positive).
  national_wave national presidential margin for presidential races, national House popular-vote margin
                otherwise, both computed from the MEDSL files (D% - R% of all votes).
  incumbency    fixed at 2 (step A, incumbency_us.py); inc +1 Democratic incumbent, -1 Republican, 0 open or president.
  beta_dev      each state's beta minus the mean of all states, ridge-shrunk: its prior sd is tau.
                tau small == every state gets the mean; tau large == each state on its own.
  candidates    one effect per person per state (Senate, governor and at-large House share it), ridge
                lambda 1 as in panel.py. Presidential candidates get none (the national margin carries them).
  lean, downballot, drift, beta_mean are not shrunk.

Races: president, US Senate (specials and deciding runoffs included), governor, at-large US House, even
years 2000-2024. A race needs a Democratic side and a Republican, and D + R >= 80% of the vote (drops
Sanders-free three-ways, McMullin is kept as the D side, King/Maine-style splits drop). Where no Democrat
ran, an independent with >= 30% is the Democratic side (Sanders, Orman 2014, McMullin 2022, Osborn 2024).
Alaska's rows are panel.py's hand-checked list (final rounds; Aug 2022 special and head-to-head duplicates
left out). DC is left out (no downballot races).

Data: external/medsl_pres (MEDSL president 1976-2024), external/medsl_senate, external/medsl_2024 (House),
external/gov/gubernatorial_county_returns_1865_2020.Rdata (Algara & Amlani, doi:10.7910/DVN/DGUMFI, summed
to state), external/gov/wiki_gov_2022_2024_raw.csv (Wikipedia 2022 / 2024 gubernatorial elections tables),
external/fec/weballYY.zip (Senate incumbent flags 2006+), external/fte/elasticity-by-state-2018.csv.

Usage: uv run state_beta.py [--cap MARGIN]   Writes state_beta.json.
"""
import csv
import io
import json
import re
import sys
import warnings
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = Path(__file__).parent
EXT = HERE / "external"
YEARS = list(range(2000, 2026, 2))
INC = 2.0
LAM_CAND = 1.0
TAUS = [0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 3.0]
PEERS = ["AK", "WY", "MT", "ND", "SD", "NH"]
SUFFIX = {"JR", "SR", "II", "III", "IV"}
FTE_2020_2022_AK = {2018: 1.16, 2020: 1.07, 2022: 1.22}  # only Alaska's 2020 / 2022 values are on file


def pkey(name: str, st: str) -> str:
    """State:SURNAME:first initial, from either 'Last, First' or 'First Last'."""
    n = re.sub(r'"[^"]*"|\([^)]*\)', " ", str(name).upper())
    if "," in n:
        last, first = n.split(",", 1)
        first = first.split()[0] if first.split() else ""
    else:
        toks = [t for t in re.sub(r"[^A-Z' -]", " ", n).split() if t.strip(".") not in SUFFIX]
        last, first = (toks[-1], toks[0]) if toks else ("", "")
    return f"{st}:{re.sub('[^A-Z]', '', last)}:{first[:1]}"


# ---------- national waves ----------
def national_waves(pres, house):
    pw = {}
    for y, g in pres.groupby("year"):
        tot = g.groupby("state_po").totalvotes.first().sum()
        d = g[g.party_simplified == "DEMOCRAT"].candidatevotes.sum(); r = g[g.party_simplified == "REPUBLICAN"].candidatevotes.sum()
        pw[y] = (d - r) / tot * 100
    hw = {}
    for y, g in house.groupby("year"):
        c = g.groupby(["state_po", "district", "candidate"]).agg(v=("candidatevotes", "sum"), p=("party", lambda s: set(s))).reset_index()
        sd = c.p.map(side_of)
        d = c[sd == "D"].v.sum(); r = c[sd == "R"].v.sum()
        tot = g.groupby(["state_po", "district"]).totalvotes.first().sum()
        hw[y] = (d - r) / tot * 100
    return pw, hw


# ---------- races ----------
def pick(cands, total):
    """cands: DataFrame candidate, side ('D','R',None), votes. Returns (d, r, dv, rv) or None."""
    c = cands.sort_values("votes", ascending=False)
    R = c[c.side == "R"]; D = c[c.side == "D"]
    if D.empty:
        oth = c[c.side.isna()]
        if not oth.empty and oth.votes.iloc[0] >= 0.30 * total:
            D = oth.head(1)
    if D.empty or R.empty:
        return None
    dv, rv = D.votes.iloc[0], R.votes.iloc[0]
    if (dv + rv) < 0.80 * total:
        return None
    return D.candidate.iloc[0], R.candidate.iloc[0], dv, rv


def side_of(parties):
    p = {str(x).upper() for x in parties}
    if p & {"DEMOCRAT", "DEMOCRATIC-FARMER-LABOR", "DEMOCRATIC-NPL"}: return "D"
    if "REPUBLICAN" in p: return "R"
    return None


def pres_races(pres):
    out = []
    for (y, st), g in pres[pres.year.isin(YEARS)].groupby(["year", "state_po"]):
        g = g.assign(side=g.party_simplified.map({"DEMOCRAT": "D", "REPUBLICAN": "R"}), votes=g.candidatevotes)
        p = pick(g, g.totalvotes.iloc[0])
        if p:
            out.append(dict(year=y, state=st, office="Pres", d=None, r=None, margin=(p[2] - p[3]) / g.totalvotes.iloc[0] * 100, inc=0))
    return out


def load_fec_inc():
    inc = set()
    for y in range(2006, 2026, 2):
        f = EXT / f"fec/weball{str(y)[2:]}.zip"
        if not f.exists():
            continue
        z = zipfile.ZipFile(f)
        for r in csv.reader(io.TextIOWrapper(z.open(z.namelist()[0]), encoding="latin-1"), delimiter="|"):
            if r[0].startswith("S") and r[2] == "I":
                inc.add((y, r[18], re.sub(r"[^A-Z]", "", r[1].split(",")[0].upper())))
    return inc


def senate_races():
    s = pd.read_csv(EXT / "medsl_senate/1976-2024-senate-state.csv", encoding="latin-1", low_memory=False)
    s["stage"] = s.stage.str.lower()
    s = s[s.stage != "pre"].copy()
    s["is_runoff"] = s.stage != "gen"
    s.loc[s.is_runoff & (s.year % 2 == 1), "year"] -= 1      # Georgia's Jan 2021 runoffs belong to 2020
    s["special"] = s.special.astype(str).str.lower() == "true"
    s = s[(s.year >= 1990) & (s.year % 2 == 0)]
    has_run = s.groupby(["year", "state_po", "special"]).is_runoff.transform("any")
    s = s[~has_run | s.is_runoff]
    fec = load_fec_inc()
    races, winners = [], []
    for (y, st, sp), g in s.groupby(["year", "state_po", "special"]):
        total = g.totalvotes.iloc[0]
        c = g.groupby("candidate").agg(votes=("candidatevotes", "sum"), side=("party_simplified", side_of)).reset_index()
        winners.append((y, st, pkey(c.sort_values("votes").candidate.iloc[-1], st)))
        p = pick(c, total)
        if p and y >= 2000:
            races.append(dict(year=y, state=st, office="Senate", d=pkey(p[0], st), r=pkey(p[1], st),
                              margin=(p[2] - p[3]) / total * 100, special=sp, dname=p[0], rname=p[1]))
    for r in races:
        prior = {k for (y, st, k) in winners if st == r["state"] and r["year"] - 6 <= y < r["year"]}
        sur = lambda k: k.split(":")[1]
        dI = r["d"] in prior or (r["year"], r["state"], sur(r["d"])) in fec
        rI = r["r"] in prior or (r["year"], r["state"], sur(r["r"])) in fec
        r["inc"] = 1 if dI and not rI else -1 if rI and not dI else 0
    return races


def house_al_races(house):
    h = house.copy()
    al = h.groupby(["year", "state_po"]).district.transform("nunique") == 1
    h = h[al & ~h.special.astype(str).str.lower().eq("true")]
    races, win = [], {}
    for (y, st), g in h.groupby(["year", "state_po"]):
        total = g.totalvotes.iloc[0]
        c = g.groupby("candidate").agg(votes=("candidatevotes", "sum"), side=("party", side_of)).reset_index()
        win[(y, st)] = pkey(c.sort_values("votes").candidate.iloc[-1], st)
        p = pick(c, total)
        if p and y in YEARS:
            races.append(dict(year=y, state=st, office="House", d=pkey(p[0], st), r=pkey(p[1], st), margin=(p[2] - p[3]) / total * 100))
    for r in races:
        w = win.get((r["year"] - 2, r["state"]))
        r["inc"] = 1 if w == r["d"] else -1 if w == r["r"] else 0
    return races


ABBR = {"Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA", "Colorado": "CO", "Connecticut": "CT",
        "Delaware": "DE", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA",
        "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI",
        "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH",
        "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
        "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN",
        "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY"}


def gov_races():
    import rdata
    g = rdata.read_rda(EXT / "gov/gubernatorial_county_returns_1865_2020.Rdata")["gov_elections_release"]
    g = g[g.election_year.isin(YEARS) & (g.election_type == "G")]
    a = g.groupby(["election_year", "state", "dem_nominee", "rep_nominee", "seat_status"])[
        ["democratic_raw_votes", "republican_raw_votes", "raw_county_vote_totals"]].sum().reset_index()
    out = []
    for _, r in a.iterrows():
        tot = r.raw_county_vote_totals
        if tot <= 0 or r.democratic_raw_votes <= 0 or r.republican_raw_votes <= 0 or (r.democratic_raw_votes + r.republican_raw_votes) < 0.8 * tot:
            continue
        st = r.state
        out.append(dict(year=int(r.election_year), state=st, office="Gov", d=pkey(r.dem_nominee, st), r=pkey(r.rep_nominee, st),
                        margin=(r.democratic_raw_votes - r.republican_raw_votes) / tot * 100,
                        inc={"Democratic Incumbent": 1, "Republican Incumbent": -1}.get(r.seat_status, 0)))
    w = pd.read_csv(EXT / "gov/wiki_gov_2022_2024_raw.csv")
    for _, r in w.iterrows():
        st = ABBR[r.state]
        cs = [c.split(";") for c in str(r.cands).split(" | ")]
        df = pd.DataFrame([(n, None if p.startswith("Democratic") or p == "DFL" else None, float(v)) for n, p, v in cs], columns=["candidate", "x", "votes"])
        df["side"] = [("D" if p.startswith("Democratic") or p == "DFL" else "R" if p == "Republican" else None) for _, p, _ in cs]
        p = pick(df, 100.0)
        if not p:
            continue
        running = str(r.status).startswith(("Incumbent re-elected", "Incumbent lost", "Incumbent elected to full", "Incumbent defeated"))
        side = "D" if str(r.gov_party).startswith(("Democratic", "DFL")) else "R"
        out.append(dict(year=int(r.year), state=st, office="Gov", d=pkey(p[0], st), r=pkey(p[1], st), margin=p[2] - p[3],
                        inc=(1 if side == "D" else -1) if running else 0))
    return out


def alaska_races():
    sys.path.insert(0, str(HERE))
    from panel import RACES
    out = []
    for yr, off, d, r, m, inc, note in RACES:
        if yr > 2024 or "Aug special" in note or "head to head" in note:
            continue
        out.append(dict(year=yr, state="AK", office=off, d=None if off == "Pres" else f"AK:{d}", r=None if off == "Pres" else f"AK:{r}",
                        margin=m, inc={"D": 1, "R": -1, None: 0}[inc] if off != "Pres" else 0))
    return out


def build(cap=None):
    pres = pd.read_csv(EXT / "medsl_pres/1976-2024-president.csv")
    house = pd.read_csv(EXT / "medsl_2024/1976-2024-house.tab", low_memory=False)
    house.columns = [c.lower() for c in house.columns]
    house = house[(house.stage.str.upper() == "GEN") & (house.year >= 1998)]
    pw, hw = national_waves(pres, house)
    rows = pres_races(pres) + senate_races() + house_al_races(house) + gov_races()
    rows = [r for r in rows if r["state"] not in ("AK", "DC")] + alaska_races()
    df = pd.DataFrame(rows)
    df["wave"] = [pw[y] if o == "Pres" else hw[y] for y, o in zip(df.year, df.office)]
    if cap is not None:
        df = df[df.margin.abs() <= cap]
    return df.reset_index(drop=True), pw, hw


# ---------- fit ----------
def design(df, states, cands):
    """Columns: lean[S], downballot[S], drift[S], beta_mean_pres, beta_mean_down, beta_dev[S], candidates[C]."""
    si = {s: i for i, s in enumerate(states)}; ci = {c: i for i, c in enumerate(cands)}
    S, C = len(states), len(cands)
    X = np.zeros((len(df), 4 * S + 2 + C))
    for i, r in enumerate(df.itertuples()):
        s = si[r.state]; down = r.office != "Pres"
        X[i, s] = 1
        X[i, S + s] = down
        X[i, 2 * S + s] = (r.year - 2000) / 4
        X[i, 3 * S + down] = r.wave
        X[i, 3 * S + 2 + s] = r.wave
        for k in (r.d, r.r):
            if k is not None and k in ci:
                X[i, 4 * S + 2 + ci[k]] = 1
    y = (df.margin - INC * df.inc).to_numpy(float)
    return X, y


def penalty(S, C, lam_b, lam_c):
    return np.r_[np.zeros(3 * S + 2), np.full(S, lam_b), np.full(C, lam_c)]


def solve(X, y, pen, train=None):
    Xt, yt = (X, y) if train is None else (X[train], y[train])
    A = Xt.T @ Xt + np.diag(pen) + np.eye(len(pen)) * 1e-9
    return np.linalg.solve(A, Xt.T @ yt), A


def held_out(X, y, pen, years):
    """Leave one cycle out: RMSE over all held-out races, and the 2018 RMSE."""
    err, e18 = [], None
    for yr in YEARS:
        tr = years != yr
        coef, _ = solve(X, y, pen, train=tr)
        e = y[~tr] - X[~tr] @ coef
        err.append(e)
        if yr == 2018:
            e18 = float(np.sqrt((e ** 2).mean()))
    e = np.concatenate(err)
    return float(np.sqrt((e ** 2).mean())), e18


def arg(name, default):
    return float(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def main():
    cap = arg("--cap", None)
    lam_c = arg("--lamc", 1.0)
    df, pw, hw = build(cap)
    states = sorted(df.state.unique())
    cands = sorted({k for k in pd.concat([df.d, df.r]).dropna()})
    S, C = len(states), len(cands)
    X, y = design(df, states, cands)
    years = df.year.to_numpy()
    print(f"{len(df)} races, {S} states, {C} candidates, cap {cap}, candidate lambda {lam_c}. By office: {df.office.value_counts().to_dict()}")
    print("National waves (D% - R%, computed): House " + ", ".join(f"{k} {v:+.1f}" for k, v in hw.items() if k in YEARS))
    print("                                    Pres  " + ", ".join(f"{k} {v:+.1f}" for k, v in pw.items() if k in YEARS))

    coef0, A0 = solve(X, y, penalty(S, C, (5.0 / 0.3) ** 2, lam_c))
    dof = len(y) - np.trace(X @ np.linalg.solve(A0, X.T))
    sigma = float(np.sqrt(((y - X @ coef0) ** 2).sum() / dof))
    print(f"Residual sd sigma {sigma:.2f} margin points (effective dof {dof:.0f})")

    fte = pd.read_csv(EXT / "fte/elasticity-by-state-2018.csv").set_index("state").elasticity
    weights = pd.read_csv(EXT / "medsl_pres/1976-2024-president.csv").query("year == 2024").groupby("state_po").totalvotes.first()

    # tau by held-out error; plus FiveThirtyEight-shaped betas (beta_state == k x FTE_state, k fitted per office)
    cv = {}
    for tau in TAUS:
        cv[tau] = held_out(X, y, penalty(S, C, sigma ** 2 / tau ** 2, lam_c), years)
    fs = np.array([fte[s] for s in states]); fs = fs / fs.mean()
    Xf = X.copy()
    for i, st in enumerate(df.state):
        Xf[i, 3 * S:3 * S + 2] *= fs[states.index(st)]
    Xf[:, 3 * S + 2:4 * S + 2] = 0
    cv_fte = held_out(Xf, y, penalty(S, C, 1e6, lam_c), years)
    print("\nHeld-out error (leave one cycle out; 2018 = fit without 2018, predict 2018):")
    print("   state betas                         all-cycles RMSE   2018 RMSE")
    for tau, (a, b) in cv.items():
        print(f"   ours, tau {tau:<5} (lambda {sigma**2/tau**2:8.1f})   {a:7.3f}          {b:7.3f}")
    print(f"   FiveThirtyEight 2018 shape          {cv_fte[0]:7.3f}          {cv_fte[1]:7.3f}")
    best = min(cv, key=lambda t: cv[t][0]); best18 = min(cv, key=lambda t: cv[t][1])
    print(f"   best tau: {best} (all cycles), {best18} (2018)")

    out = dict(cap=cap, lam_c=lam_c, sigma=sigma, cv={str(k): v for k, v in cv.items()}, cv_fte=cv_fte, best_tau=best, best_tau_2018=best18,
               waves=dict(house={str(k): round(v, 2) for k, v in hw.items() if k in YEARS}, pres={str(k): round(v, 2) for k, v in pw.items() if k in YEARS}),
               n_races=len(df), fits={})
    ci = {c: i for i, c in enumerate(cands)}
    for tau in TAUS:
        coef, A = solve(X, y, penalty(S, C, sigma ** 2 / tau ** 2, lam_c))
        cov = sigma ** 2 * np.linalg.inv(A)
        bp, bd = coef[3 * S], coef[3 * S + 1]; jd = 3 * S + 1
        tab = []
        for s, st in enumerate(states):
            j = 3 * S + 2 + s
            se = float(np.sqrt(cov[jd, jd] + cov[j, j] + 2 * cov[jd, j]))
            tab.append(dict(state=st, beta_down=float(bd + coef[j]), beta_pres=float(bp + coef[j]), se=se, dev=float(coef[j]),
                            lean2000=float(coef[s]), downballot=float(coef[S + s]), drift=float(coef[2 * S + s]),
                            races=int((df.state == st).sum()), fte2018=float(fte.get(st, np.nan))))
        t = pd.DataFrame(tab).set_index("state")
        w = weights.reindex(t.index).fillna(0)
        wmean = float((t.beta_pres * w).sum() / w.sum())
        t["relative"] = t.beta_pres / wmean
        r_p = float(np.corrcoef(t.dev, t.fte2018)[0, 1]); r_s = float(t.dev.rank().corr(t.fte2018.rank()))
        # Alaska 2026: generic downballot margin at national House +13, and the three races with known candidate effects
        a = states.index("AK")
        eff = lambda k: float(coef[4 * S + 2 + ci[k]]) if k in ci else 0.0
        gen26 = coef[a] + coef[S + a] + coef[2 * S + a] * 6.5 + (bd + coef[3 * S + 2 + a]) * 13.0
        gen24 = coef[a] + coef[S + a] + coef[2 * S + a] * 6.0 + (bd + coef[3 * S + 2 + a]) * hw[2024]
        ak = dict(generic_2024=float(gen24), generic_2026=float(gen26), eff_NBegich=eff("AK:N.Begich"), eff_Peltola=eff("AK:Peltola"),
                  eff_Sullivan=eff("AK:Sullivan"), beta_down=float(bd + coef[3 * S + 2 + a]),
                  effects={k: round(float(coef[4 * S + 2 + i]), 3) for k, i in ci.items() if k.startswith("AK:")},
                  drift=float(coef[2 * S + a]), lean_at_zero_2026=float(gen26 - (bd + coef[3 * S + 2 + a]) * 13.0))
        out["fits"][str(tau)] = dict(beta_mean_pres=float(bp), beta_mean_down=float(bd), beta_mean_down_se=float(np.sqrt(cov[jd, jd])),
                                     vote_weighted_pres=wmean, corr_fte_pearson=r_p, corr_fte_spearman=r_s, alaska_2026=ak,
                                     states=t.round(4).reset_index().to_dict("records"))
        if tau in (best, best18, 0.3, 3.0):
            print(f"\n== tau {tau}: mean beta president {bp:.3f}, downballot {bd:.3f} (se {np.sqrt(cov[jd,jd]):.3f}); vote-weighted president {wmean:.3f}")
            print(f"   state deviations against FiveThirtyEight 2018: Pearson {r_p:+.2f}, Spearman {r_s:+.2f}")
            print("   state  downballot beta  se    95% range      pres beta  FTE2018  races  drift/4yr  lean2000  downballot offset")
            for st in PEERS:
                r = t.loc[st]
                print(f"   {st}     {r.beta_down:5.2f}        {r.se:4.2f}  {r.beta_down-1.96*r.se:5.2f} to {r.beta_down+1.96*r.se:5.2f}   {r.beta_pres:5.2f}    {r.fte2018:4.2f}   {int(r.races):4d}   {r.drift:+6.2f}    {r.lean2000:+7.2f}   {r.downballot:+6.2f}")
            print("   highest:", ", ".join(f"{s} {v:.2f}" for s, v in t.beta_down.sort_values(ascending=False).head(6).items()))
            print("   lowest: ", ", ".join(f"{s} {v:.2f}" for s, v in t.beta_down.sort_values().head(6).items()))
            print(f"   Alaska generic downballot: 2024 {gen24:+.2f}, 2026 at national +13 {gen26:+.2f}. Effects: N.Begich {ak['eff_NBegich']:+.2f},"
                  f" Peltola {ak['eff_Peltola']:+.2f}, Sullivan {ak['eff_Sullivan']:+.2f}")

    # 2018 held out at the chosen tau, Alaska's rows
    tr = years != 2018
    coef, _ = solve(X, y, penalty(S, C, sigma ** 2 / best ** 2, lam_c), train=tr)
    t18 = df[~tr].copy()
    t18["pred"] = X[~tr] @ coef + INC * t18.inc
    t18["resid"] = t18.margin - t18.pred
    print(f"\n== 2018 held out (tau {best}): mean residual by office, all states (D positive)")
    print("   " + ", ".join(f"{o} {v:+.2f} (n {n})" for o, v, n in zip(*[t18.groupby('office').resid.mean().index, t18.groupby('office').resid.mean().values, t18.groupby('office').size().values])))
    for r in t18[t18.state == "AK"].itertuples():
        print(f"   AK {r.office:6} actual {r.margin:+7.2f}  predicted {r.pred:+7.2f}  residual {r.resid:+6.2f}")
    out["held_out_2018"] = dict(tau=best, by_office=t18.groupby("office").resid.mean().round(3).to_dict(),
                                alaska=t18[t18.state == "AK"][["office", "d", "r", "margin", "pred", "resid", "wave", "inc"]].round(3).to_dict("records"))
    suffix = ("" if cap is None else f"_cap{int(cap)}") + ("" if lam_c == 1.0 else f"_lamc{lam_c:g}")
    df.to_csv(HERE / "state_beta_races.csv", index=False)
    (HERE / f"state_beta{suffix}.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
