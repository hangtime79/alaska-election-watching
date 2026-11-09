# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2"]
# ///
"""Test plan A1: Alaska's lean as an additive Holt-Winters series (period 2: presidential / midterm), iterated
with the candidate effects from panel.py.

  environment of a race == margin - beta x national_wave - incumbency x inc - D effect - R effect
  x_year               == average environment of that year's races
  Holt-Winters, one step per two-year cycle (season index: presidential year or midterm):
    forecast         == level_prev + trend_prev + season_two_back
    level            == a x (x_year - season_two_back) + (1 - a) x (level_prev + trend_prev)
    trend            == t x (level - level_prev) + (1 - t) x trend_prev
    season           == g x (x_year - level) + (1 - g) x season_two_back
    lean_year        == level + season          (a year with no races carries the forecast forward)
  then candidate effects are refitted against that lean (ridge, as panel.py) and the loop repeats until
  the lean stops moving.

Smoothing weights are fixed (a, t, g == 0.3, 0.1, 0.2) with a sensitivity grid. Alaska's beta is held at
each of 0.154, 0.30, 0.60, 0.93. (Holt-Winters' own "beta" is called the trend weight t here, to keep it
apart from Alaska's beta.) Same races, incumbency (2) and 25-point cut as panel.py.

Caveat: a lean that moves year by year can soak up the national wave, which is also one number per year,
so a flexible lean (large a) makes beta harder to see. The fit error by beta is printed for each weight set.

Usage: uv run holt_winters.py   Writes holt_winters.json.
       uv run holt_winters.py --scan   Grant's form (national margin as the season, no period-2 season): picks
       beta by one-step error over 0-1.2 for several weights. Writes holt_winters_scan.json.
"""
import itertools
import json
from pathlib import Path

import numpy as np

from panel import HOUSE_WAVE, INC, MAX_MARGIN, PRES_WAVE, RACES, fit

HERE = Path(__file__).parent
YEARS = list(range(2000, 2028, 2))
BETAS = [0.154, 0.30, 0.60, 0.93]
BASE = (0.3, 0.1, 0.2)
GRID = list(itertools.product([0.2, 0.3, 0.5], [0.05, 0.1, 0.2], [0.1, 0.2, 0.4]))
LAM = 1.0
SHOW = ["Peltola", "N.Begich", "Sullivan", "Dunleavy", "Trump", "Harris", "Hill+Hafner", "Kreiss-Tomkins"]

races = [r for r in RACES if abs(r[4]) <= MAX_MARGIN]
cands = sorted({r[2] for r in races} | {r[3] for r in races})
wave = np.array([PRES_WAVE[r[0]] if r[1] == "Pres" else HOUSE_WAVE[r[0]] for r in races])
inc = np.array([{"D": 1, "R": -1, None: 0}[r[5]] for r in races])
margin = np.array([r[4] for r in races])
yr = np.array([r[0] for r in races])
X = np.zeros((len(races), len(cands)))
for i, r in enumerate(races):
    X[i, cands.index(r[2])] = 1
    X[i, cands.index(r[3])] = 1


def holt_winters(x: dict, a: float, t: float, g: float, level0: float, trend0: float):
    """x: year -> observed environment (missing years absent). Returns filtered lean, forecasts, state."""
    level, trend, season = level0, trend0, {0: 0.0, 1: 0.0}
    lean, fc = {}, {}
    for y in YEARS:
        k = (y // 2) % 2  # 0 presidential year, 1 midterm
        f = level + trend + season[k]
        fc[y] = f
        if y in x:
            new_level = a * (x[y] - season[k]) + (1 - a) * (level + trend)
            trend = t * (new_level - level) + (1 - t) * trend
            level = new_level
            season[k] = g * (x[y] - level) + (1 - g) * season[k]
        else:
            level = level + trend
        lean[y] = level + season[k]
    return lean, fc, {"level": level, "trend": trend, "season_pres": season[0], "season_mid": season[1]}


def run(beta: float, a: float, t: float, g: float) -> dict:
    c0, _, _ = fit(LAM, beta_fixed=beta)
    eff = np.array([c0[k] for k in cands])
    level0, trend0 = c0["lean_2000"], c0["drift"] / 2  # panel drift is per 4 years; one step is 2
    base = margin - beta * wave - INC * inc
    prev = None
    for it in range(200):
        env = base - X @ eff
        x = {y: float(env[yr == y].mean()) for y in YEARS if (yr == y).any()}
        lean, fc, state = holt_winters(x, a, t, g, level0, trend0)
        L = np.array([lean[y] for y in yr])
        eff = np.linalg.solve(X.T @ X + LAM * np.eye(len(cands)), X.T @ (base - L))
        vec = np.array([lean[y] for y in YEARS])
        if prev is not None and np.abs(vec - prev).max() < 1e-4:
            break
        prev = vec
    resid = base - L - X @ eff
    one_step = [x[y] - fc[y] for y in YEARS if y in x and y >= 2006]
    # 2026 out of sample: run the filter on data through 2024 only
    lean24, fc24, _ = holt_winters({y: v for y, v in x.items() if y <= 2024}, a, t, g, level0, trend0)
    e = dict(zip(cands, eff))
    return {"beta": beta, "weights": [a, t, g], "iterations": it + 1,
            "race_rmse": round(float(np.sqrt((resid ** 2).mean())), 2),
            "one_step_rmse": round(float(np.sqrt(np.mean(np.square(one_step)))), 2),
            "x": {y: round(v, 2) for y, v in x.items()},
            "lean": {y: round(lean[y], 2) for y in YEARS},
            "lean_2026_forecast_from_2024": round(fc24[2026], 2),
            "state": {k: round(v, 2) for k, v in state.items()},
            "generic_d": {y: round(lean[y] + beta * HOUSE_WAVE[y], 2) for y in (2022, 2024, 2026)},
            "effects": {k: round(float(e[k]), 2) for k in SHOW}}


def scan() -> dict:
    """Grant's form: base (Alaska's lean) + beta x national margin, and each cycle's miss feeds the next base.
    Same as the filter above with the season switched off (g == 0): the national margin is the season.
    The base is set before the year is seen, so a one-step miss can't be absorbed by the base, and beta has
    to explain the wave. Beta chosen by the one-step error (2006 on)."""
    betas = [round(b, 2) for b in np.arange(0.0, 1.25, 0.05)]
    rows = []
    for a, t in itertools.product([0.2, 0.3, 0.5, 1.0], [0.0, 0.1]):
        errs = {b: run(b, a, t, 0.0) for b in betas}
        best = min(errs, key=lambda b: errs[b]["one_step_rmse"])
        rows.append({"a": a, "t": t, "best_beta": best, "one_step": {b: r["one_step_rmse"] for b, r in errs.items()},
                     "lean": errs[best]["lean"], "effects": errs[best]["effects"]})
        e = errs
        print(f"  a {a:.1f} t {t:.1f}: best beta {best:.2f} (one-step {e[best]['one_step_rmse']:.2f});"
              f" one-step at beta 0.15 {e[0.15]['one_step_rmse']:.2f}, 0.30 {e[0.3]['one_step_rmse']:.2f},"
              f" 0.60 {e[0.6]['one_step_rmse']:.2f}, 0.95 {e[0.95]['one_step_rmse']:.2f};"
              f" lean 2024 {e[best]['lean'][2024]:+.2f}; Peltola {e[best]['effects']['Peltola']:+.2f}, Begich {e[best]['effects']['N.Begich']:+.2f}")
    return rows


def main() -> None:
    if "--scan" in __import__("sys").argv:
        print("== Base + beta x national margin, no presidential/midterm season (g == 0); beta by one-step error")
        (HERE / "holt_winters_scan.json").write_text(json.dumps(scan(), indent=1))
        return
    out = {"base": [], "grid": []}
    print(f"== Base weights a, t, g == {BASE}")
    for b in BETAS:
        r = run(b, *BASE)
        out["base"].append(r)
        print(f"\n-- beta {b}: {r['iterations']} iterations, race fit error {r['race_rmse']}, one-step error {r['one_step_rmse']}")
        print("   year environment x: " + ", ".join(f"{y} {v:+.2f}" for y, v in r["x"].items()))
        print("   lean (level + season): " + ", ".join(f"{y} {r['lean'][y]:+.2f}" for y in YEARS))
        print(f"   season: presidential {r['state']['season_pres']:+.2f}, midterm {r['state']['season_mid']:+.2f};"
              f" trend {r['state']['trend']:+.2f} per cycle")
        print(f"   2026 lean forecast from data through 2024: {r['lean_2026_forecast_from_2024']:+.2f}")
        for y in (2022, 2024, 2026):
            print(f"   generic D {y} == lean + beta x wave == {r['lean'][y]:+.2f} + {b} x {HOUSE_WAVE[y]:+.1f} == {r['generic_d'][y]:+.2f}")
        print("   effects: " + ", ".join(f"{k} {v:+.2f}" for k, v in r["effects"].items()))
    print("\n== Sensitivity over the weight grid (a in 0.2/0.3/0.5, t in 0.05/0.1/0.2, g in 0.1/0.2/0.4)")
    for b in BETAS:
        rows = [run(b, *w) for w in GRID]
        out["grid"] += rows
        rng = lambda f: (min(f(r) for r in rows), max(f(r) for r in rows))
        parts = {"race error": rng(lambda r: r["race_rmse"]), "lean 2022": rng(lambda r: r["lean"][2022]),
                 "lean 2024": rng(lambda r: r["lean"][2024]), "lean 2026": rng(lambda r: r["lean"][2026]),
                 "Peltola": rng(lambda r: r["effects"]["Peltola"]), "Begich": rng(lambda r: r["effects"]["N.Begich"])}
        print(f"  beta {b}: " + "; ".join(f"{k} {lo:+.2f} to {hi:+.2f}" for k, (lo, hi) in parts.items()))
    print("\n== Which beta fits best, for each weight set (race fit error)")
    best = {}
    for w in GRID:
        errs = {r["beta"]: r["race_rmse"] for r in out["grid"] if tuple(r["weights"]) == w}
        best[min(errs, key=errs.get)] = best.get(min(errs, key=errs.get), 0) + 1
    print("  " + ", ".join(f"beta {b}: best in {n} of {len(GRID)}" for b, n in sorted(best.items())))
    (HERE / "holt_winters.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
