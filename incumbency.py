# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2"]
# ///
"""Choose the incumbency advantage from the statewide races instead of fixing it at 2.

  margin == lean_2000 + drift x cycles + beta x national_wave + incumbency x inc + D effect + R effect

In sample, a free incumbency soaks up the strength of candidates who only ever ran as incumbents (Young's
eleven wins), because their own effects are shrunk toward zero and incumbency isn't. So incumbency is
chosen by leave-one-race-out prediction error: each race is predicted from a fit to all the others, at each
incumbency value on a grid. Done at several betas, with and without the races of candidates who never ran
except as incumbents (Young, Stevens, L.Murkowski, Parnell), and with the Holt-Winters form
(holt_winters.py, national margin as the season, one-step error).

Same races, 25-point cut and ridge (lambda 1) as panel.py.
Usage: uv run incumbency.py   Writes incumbency.json.
"""
import json
from pathlib import Path

import numpy as np

import holt_winters as hw
import panel
from panel import HOUSE_WAVE, MAX_MARGIN, PRES_WAVE, RACES

HERE = Path(__file__).parent
GRID = [round(v, 2) for v in np.arange(0.0, 8.01, 0.5)]
BETAS = [0.15, 0.25, 0.60, 0.93]
ALWAYS_INC = {"Young", "Stevens", "L.Murkowski", "Parnell"}
LAM = 1.0


def design(races, beta, inc_value):
    cands = sorted({r[2] for r in races} | {r[3] for r in races})
    X = np.zeros((len(races), 2 + len(cands))); y = np.zeros(len(races))
    for i, (yr, off, d, r, m, inc, _) in enumerate(races):
        wave = PRES_WAVE[yr] if off == "Pres" else HOUSE_WAVE[yr]
        X[i, 0] = 1; X[i, 1] = (yr - 2000) / 4
        X[i, 2 + cands.index(d)] = 1; X[i, 2 + cands.index(r)] = 1
        y[i] = m - beta * wave - inc_value * {"D": 1, "R": -1, None: 0}[inc]
    P = np.diag([0.0, 0.0] + [LAM] * len(cands))
    return X, y, P


def loo_error(races, beta, inc_value) -> float:
    X, y, P = design(races, beta, inc_value)
    errs = []
    for i in range(len(races)):
        k = np.arange(len(races)) != i
        coef = np.linalg.solve(X[k].T @ X[k] + P, X[k].T @ y[k])
        errs.append(y[i] - X[i] @ coef)
    return float(np.sqrt(np.mean(np.square(errs))))


def free_fit(races, beta) -> float:
    """In-sample incumbency, unshrunk (for comparison)."""
    X, y, P = design(races, beta, 0.0)
    incs = np.array([{"D": 1, "R": -1, None: 0}[r[5]] for r in races])
    X = np.column_stack([X, incs]); P = np.diag(list(np.diag(P)) + [0.0])
    m = np.array([r[4] for r in races]) - beta * np.array([PRES_WAVE[r[0]] if r[1] == "Pres" else HOUSE_WAVE[r[0]] for r in races])
    return float(np.linalg.solve(X.T @ X + P, X.T @ m)[-1])


def main() -> None:
    base = [r for r in RACES if abs(r[4]) <= MAX_MARGIN]
    no_always = [r for r in base if r[2] not in ALWAYS_INC and r[3] not in ALWAYS_INC]
    out = {}
    for label, races in [("all races", base), ("without always-incumbent candidates", no_always)]:
        print(f"\n== {label} ({len(races)} races): leave-one-race-out error by incumbency")
        print("   beta  " + " ".join(f"{v:>5}" for v in GRID) + "   best   in-sample free fit")
        rows = {}
        for b in BETAS:
            e = [loo_error(races, b, v) for v in GRID]
            best = GRID[int(np.argmin(e))]
            free = free_fit(races, b)
            rows[b] = {"errors": dict(zip(GRID, [round(x, 2) for x in e])), "best": best, "free_fit": round(free, 2)}
            print(f"   {b:4.2f}  " + " ".join(f"{x:5.2f}" for x in e) + f"   {best:4.1f}   {free:+.2f}")
        out[label] = rows

    print("\n== Holt-Winters form (national margin as the season, a 0.3, t 0): one-step error by incumbency")
    print("   beta  " + " ".join(f"{v:>5}" for v in GRID) + "   best")
    hwrows = {}
    for b in BETAS:
        e = []
        for v in GRID:
            hw.INC = panel.INC = v
            e.append(hw.run(b, 0.3, 0.0, 0.0)["one_step_rmse"])
        best = GRID[int(np.argmin(e))]
        hwrows[b] = {"errors": dict(zip(GRID, e)), "best": best}
        print(f"   {b:4.2f}  " + " ".join(f"{x:5.2f}" for x in e) + f"   {best:4.1f}")
    hw.INC = panel.INC = 2.0
    out["holt_winters_one_step"] = hwrows
    (HERE / "incumbency.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
