# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2"]
# ///
"""Alaska's lean and every candidate's effect, estimated together from all statewide races, 2000-2026.

  margin == lean_2000 + drift × cycles_since_2000 + beta × national_wave + incumbency × inc
            + Democratic-side candidate effect + Republican candidate effect

Sign convention: D positive. A strong Republican has a negative effect. inc is +1 for a Democratic
incumbent, -1 for a Republican one, 0 for an open seat (presidential races 0: the national margin
already carries the president). national_wave is the national presidential margin for presidential races
and the national House margin otherwise. Candidate effects are ridge-shrunk toward 0 (the average
candidate is generic); lean, drift, beta and incumbency are not shrunk. Effects are per candidate across
offices and years, so a candidate who runs several times links the years.

Margins: D% - R% as reported; ranked-choice years use the final round (or a head to head where noted).
Left out: races with a large third candidate not on either side (2010 and 2016 Senate) and Republican
against Republican (2022 Senate). Walker 2014 is the Democratic side (unity ticket); Gara + Walker 2022
are combined as the Democratic side; Gross 2020 and Hill 2026 are Democratic-endorsed independents.
Sources: Wikipedia (Alaska results); national House margins from memory; 2026 rows are projections.

Usage: uv run panel.py [LAMBDA ...]   (default lambdas 0.25 1 4). Prints the fit; writes panel.json.
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
HOUSE_WAVE = {2000: -0.5, 2002: -4.8, 2004: -2.6, 2006: 8.0, 2008: 10.6, 2010: -6.8, 2012: 1.2, 2014: -5.7,
              2016: -1.1, 2018: 8.6, 2020: 3.1, 2022: -2.8, 2024: -2.6, 2026: 13.0}
PRES_WAVE = {2000: 0.51, 2004: -2.46, 2008: 7.27, 2012: 3.86, 2016: 2.09, 2020: 4.45, 2024: -1.48}

# (year, office, D side, R side, margin D-R, incumbent side 'D'/'R'/None, note)
RACES = [
    (2000, "Pres", "Gore", "Bush", -30.95, None, ""), (2004, "Pres", "Kerry", "Bush", -25.55, None, ""),
    (2008, "Pres", "Obama", "McCain-Palin", -21.53, None, ""), (2012, "Pres", "Obama", "Romney", -13.99, None, ""),
    (2016, "Pres", "Clinton", "Trump", -14.73, None, ""), (2020, "Pres", "Biden", "Trump", -10.06, None, ""),
    (2024, "Pres", "Harris", "Trump", -13.13, None, ""),
    (2000, "House", "Greene", "Young", -53.1, "R", ""), (2002, "House", "Greene", "Young", -57.2, "R", ""),
    (2004, "House", "Higgins", "Young", -48.7, "R", ""), (2006, "House", "Benson", "Young", -16.6, "R", ""),
    (2008, "House", "Berkowitz", "Young", -5.1, "R", ""), (2010, "House", "Crawford", "Young", -38.5, "R", ""),
    (2012, "House", "Cissna", "Young", -35.32, "R", ""), (2014, "House", "Dunbar", "Young", -10.01, "R", ""),
    (2016, "House", "Lindbeck", "Young", -14.30, "R", ""), (2018, "House", "Galvin", "Young", -6.58, "R", ""),
    (2020, "House", "Galvin", "Young", -9.14, "R", ""),
    (2022, "House", "Peltola", "Palin", 2.96, None, "Aug special, final round"),
    (2022, "House", "Peltola", "N.Begich", -5.12, None, "Aug special, head to head"),
    (2022, "House", "Peltola", "Palin", 9.92, "D", "Nov, final round"),
    (2022, "House", "Peltola", "N.Begich", 10.75, "D", "Nov, head to head"),
    (2024, "House", "Peltola", "N.Begich", -2.44, "D", "final round"),
    (2026, "House", "Hill+Hafner", "N.Begich", -3.20, "R", "projected final round"),
    (2002, "Senate", "Vondersaar", "Stevens", -67.66, "R", ""), (2004, "Senate", "Knowles", "L.Murkowski", -3.03, "R", ""),
    (2008, "Senate", "M.Begich", "Stevens", 1.25, "R", ""), (2014, "Senate", "M.Begich", "Sullivan", -2.13, "D", ""),
    (2020, "Senate", "Gross", "Sullivan", -12.71, "R", ""), (2026, "Senate", "Peltola", "Sullivan", 3.08, "R", "projected final round"),
    (2002, "Gov", "Ulmer", "F.Murkowski", -15.15, None, ""), (2006, "Gov", "Knowles", "Palin", -7.36, None, ""),
    (2010, "Gov", "Berkowitz", "Parnell", -21.39, "R", ""), (2014, "Gov", "Walker", "Parnell", 2.22, "R", ""),
    (2018, "Gov", "M.Begich", "Dunleavy", -7.03, None, ""), (2022, "Gov", "Gara+Walker", "Dunleavy", -5.35, "R", "first round, D side combined"),
    (2026, "Gov", "Kreiss-Tomkins", "Republicans 2026", -1.74, None, "first choices, three Republicans combined"),
]


INC = 2.0       # incumbency fixed: Young's 11 wins make it inseparable from his own effect
MAX_MARGIN = 25  # races decided by more than this had token opponents and say little about lean


def fit(lam: float, beta_fixed: float | None = None, races=None):
    races = [r for r in RACES if abs(r[4]) <= MAX_MARGIN] if races is None else races
    cands = sorted({r[2] for r in races} | {r[3] for r in races})
    fixed = ["lean_2000", "drift"] + ([] if beta_fixed is not None else ["beta"])
    cols = fixed + cands
    X = np.zeros((len(races), len(cols))); y = np.zeros(len(races))
    for i, (yr, off, d, r, m, inc, _) in enumerate(races):
        wave = PRES_WAVE[yr] if off == "Pres" else HOUSE_WAVE[yr]
        X[i, 0] = 1; X[i, 1] = (yr - 2000) / 4
        y[i] = m - INC * {"D": 1, "R": -1, None: 0}[inc]
        if beta_fixed is None:
            X[i, 2] = wave
        else:
            y[i] -= beta_fixed * wave
        X[i, cols.index(d)] = 1; X[i, cols.index(r)] = 1
    P = np.diag([0.0] * len(fixed) + [lam] * len(cands))
    coef = np.linalg.solve(X.T @ X + P, X.T @ y)
    resid = y - X @ coef
    return dict(zip(cols, coef)), resid, races


def main() -> None:
    lams = [float(a) for a in sys.argv[1:]] or [0.25, 1.0, 4.0]
    out = {}
    for lam in lams:
        c, resid, races = fit(lam)
        rmse = float(np.sqrt((resid ** 2).mean()))
        lean = {yr: c["lean_2000"] + c["drift"] * (yr - 2000) / 4 for yr in (2022, 2024, 2026)}
        print(f"\n== lambda {lam}: {len(races)} races, beta {c['beta']:.2f}, drift {c['drift']:+.2f} per 4 years, incumbency fixed {INC}, rmse {rmse:.2f}")
        print("   lean: " + ", ".join(f"{yr} {v:+.2f}" for yr, v in lean.items()))
        eff = sorted(((k, v) for k, v in c.items() if k not in ("lean_2000", "drift", "beta")), key=lambda kv: kv[1])
        print("   candidate effects (D positive; negative helps the Republican side):")
        for k, v in eff:
            print(f"     {k:18} {v:+6.2f}")
        out[str(lam)] = {"params": {k: round(float(c[k]), 3) for k in ("lean_2000", "drift", "beta")} | {"incumbency": INC},
                         "lean": {str(k): round(float(v), 2) for k, v in lean.items()}, "rmse": round(rmse, 2),
                         "effects": {k: round(float(v), 2) for k, v in eff},
                         "residuals": [{"year": r[0], "office": r[1], "race": f"{r[2]} - {r[3]}", "note": r[6], "resid": round(float(e), 2)} for r, e in zip(races, resid)]}
    c, resid, races = fit(1.0)
    print("\n== residuals at lambda 1 (actual minus fitted)")
    for r, e in zip(races, resid):
        print(f"   {r[0]} {r[1]:6} {r[2] + ' - ' + r[3]:32} {r[6]:42} {e:+6.2f}")
    (HERE / "panel.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
