# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2"]
# ///
"""The party-label question in the 2026 House race (Grant, 9 Nov).

Two sides of the same question, on the same ballots:
  A. Hafner ballots that stop. Did those voters vote Democratic everywhere else, and did they rank several
     candidates in the Senate and governor races (so they knew how to rank and chose not to rank Hill)?
     Control: 2024, when Hafner was on the ballot and the Democrat still in the race was Peltola.
  B. Hill's voters who otherwise voted Republican: Hill first choices whose Senate and governor first choices
     were Republican (and legislative picks, where present).
Writes label_effect.json. Run from the repo root: uv run claims/label_effect.py
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, ".")
import rcv  # noqa: E402
import cvr2026  # noqa: E402

R = rcv.RANKS
NAME = lambda v: v.split(",")[0]


def load(path, cols=("RCTab CVR Id",)):
    return pd.read_csv(path, usecols=[*cols, *R], dtype=str, keep_default_na=False)


def ranked(row):
    """Distinct candidates marked (overvotes count their names), blanks dropped."""
    out = []
    for v in row:
        if v == "undervote":
            continue
        for n in v.split("\n"):
            if n not in out:
                out.append(n)
    return out


def final_rounds(df, order):
    """Holder at each round for a fixed elimination order (list of full names)."""
    t = [tuple(rcv.SKIP if v == "undervote" else (rcv.OVER if "\n" in v else v) for v in r) for r in df[R].itertuples(index=False)]
    elim, out = set(), []
    for c in order:
        elim.add(c)
        out.append([rcv.assign(x, elim) for x in t])
    return out


def main():
    res = {}
    # ---------- 2026 ----------
    h = load(cvr2026.HOUSE)
    s = load(cvr2026.SENATE)
    g = load(cvr2026.GOVERNOR)
    for d, k in ((h, "h"), (s, "s"), (g, "g")):
        d[k + "_list"] = [ranked(r) for r in d[R].itertuples(index=False)]
        d[k + "_n"] = d[k + "_list"].map(len)
    W, MC, HF = "Write-in", 'McDermott, James C. "Jim"', "Hafner, Eric"
    rounds = final_rounds(h, [W, MC, HF])
    h["at_hafner"] = pd.Series(rounds[1]) == HF          # held by Hafner when he went out
    h["final"] = pd.Series(rounds[2]).map(lambda x: "stops" if x.startswith("inactive") else NAME(x))
    x = pd.read_csv("crossover_2026.csv", dtype=str, keep_default_na=False)[["RCTab CVR Id", "S1", "SF", "vt", "dist"]]
    L = pd.read_csv("legislative_2026.csv", dtype=str)
    L["d"] = (L.leg_first == "D").astype(int); L["r"] = (L.leg_first == "R").astype(int)
    leg = L.groupby("RCTab CVR Id")[["d", "r"]].sum()
    m = h[["RCTab CVR Id", "h_list", "h_n", "at_hafner", "final"]].merge(x, on="RCTab CVR Id", how="left") \
        .merge(s[["RCTab CVR Id", "s_n", "s_list"]], on="RCTab CVR Id", how="left") \
        .merge(g[["RCTab CVR Id", "g_n", "g_list"]], on="RCTab CVR Id", how="left") \
        .merge(leg, left_on="RCTab CVR Id", right_index=True, how="left").fillna({"d": 0, "r": 0, "g_n": -1})
    GOV_R = ("Wilson", "Bronson", "Taylor")
    m["gov1"] = m.g_list.map(lambda q: "none" if not isinstance(q, list) or not q else ("Kreiss-Tomkins" if q[0].startswith("Kreiss") else ("Republican" if q[0].startswith(GOV_R) else "other")))
    m["leg"] = m.apply(lambda r: "D" if r.d > 0 and r.r == 0 else ("R" if r.r > 0 and r.d == 0 else ("both" if r.r > 0 else "none")), axis=1)
    m["h1"] = m.h_list.map(lambda q: NAME(q[0]) if q else "blank")

    def prof(d):
        n = len(d)
        allD = ((d.S1 == "Peltola") & (d.gov1 == "Kreiss-Tomkins") & (d.leg.isin(["D", "none"])))
        allD_leg = allD & (d.leg == "D")
        allR = (d.S1.isin(["Sullivan", "Sullivan Jr.", "Heikes"])) & (d.gov1 == "Republican") & (d.leg.isin(["R", "none"]))
        return {"n": n,
                "all_D": int(allD.sum()), "all_D_with_leg": int(allD_leg.sum()), "all_R": int(allR.sum()),
                "senate_ranked_2plus": int((d.s_n >= 2).sum()), "gov_ranked_2plus": int((d.g_n >= 2).sum()),
                "either_2plus": int(((d.s_n >= 2) | (d.g_n >= 2)).sum()),
                "allD_and_ranked_2plus_elsewhere": int((allD & ((d.s_n >= 2) | (d.g_n >= 2))).sum()),
                "house_n": d.h_n.value_counts().sort_index().astype(int).to_dict()}
    A = {}
    hf = m[m.at_hafner]
    for k, d in hf.groupby("final"):
        A[k] = prof(d)
    A["only_hafner"] = prof(hf[hf.h_list.map(lambda q: q == [HF])])
    # baselines: ranking depth of every House first-choice group
    base = {}
    for k in ("Hill", "Begich", "Hafner", "McDermott"):
        d = m[m.h1 == k]
        base[k] = {"n": len(d), "house_only_one": int((d.h_n == 1).sum()),
                   "senate_2plus": int((d.s_n >= 2).sum()), "gov_2plus": int((d.g_n >= 2).sum())}
    res["A_2026"] = A
    res["baseline_2026"] = base

    # ---------- B: Hill voters who otherwise vote Republican ----------
    B = {}
    hill1 = m[m.h1 == "Hill"]
    hillF = m[m.final == "Hill"]
    for lab, d in (("hill_first_choice", hill1), ("hill_final_round", hillF)):
        sen = d.S1.map(lambda v: v if v in ("Peltola", "Sullivan", "Sullivan Jr.", "Heikes") else "other/blank")
        B[lab] = {"n": len(d),
                  "senate_x_gov": {f"{a} | {b}": int(n) for (a, b), n in pd.crosstab(sen, d.gov1).stack().items() if n},
                  "all_R_elsewhere": int(((d.S1.isin(["Sullivan", "Sullivan Jr.", "Heikes"])) & (d.gov1 == "Republican") & d.leg.isin(["R", "none"])).sum()),
                  "all_R_with_leg": int(((d.S1.isin(["Sullivan", "Sullivan Jr.", "Heikes"])) & (d.gov1 == "Republican") & (d.leg == "R")).sum()),
                  "sullivan_and_R_gov": int(((d.S1 == "Sullivan") & (d.gov1 == "Republican")).sum()),
                  "ranked_begich_2nd": int(d.h_list.map(lambda q: len(q) > 1 and NAME(q[1]) == "Begich").sum())}
    res["B_2026"] = B

    # ---------- 2024 control: Hafner then ----------
    h4 = load("2026-11-04_23-29_rctab_cvr.csv")
    h4["h_list"] = [ranked(r) for r in h4[R].itertuples(index=False)]
    h4["h_n"] = h4.h_list.map(len)
    p4 = load("2026-11-05_14-34_rctab_cvr-2024-president.csv")
    p4["p1"] = p4[R].apply(lambda r: next((NAME(v) for v in r if v != "undervote"), "blank"), axis=1)
    p4["p_n"] = [len(ranked(r)) for r in p4[R].itertuples(index=False)]
    names4 = sorted({n for q in h4.h_list for n in q})
    hafner4 = next(n for n in names4 if n.startswith("Hafner"))
    howe4 = next(n for n in names4 if n.startswith("Howe"))
    r4 = final_rounds(h4, ["Write-in", hafner4, howe4])
    h4["at_hafner"] = pd.Series(r4[0]) == hafner4
    h4["after"] = pd.Series(r4[1]).map(lambda v: "stops" if v.startswith("inactive") else NAME(v))
    h4["final"] = pd.Series(r4[2]).map(lambda v: "stops" if v.startswith("inactive") else NAME(v))
    mm = h4.merge(p4[["RCTab CVR Id", "p1", "p_n"]], on="RCTab CVR Id", how="left")
    d = mm[mm.at_hafner]
    res["hafner_2024"] = {"held": len(d), "next": d.after.value_counts().astype(int).to_dict(),
                          "final": d.final.value_counts().astype(int).to_dict(),
                          "only_hafner": int(d.h_list.map(lambda q: q == [hafner4]).sum()),
                          "president": d.p1.value_counts().head(6).astype(int).to_dict(),
                          "harris_voters_final": d[d.p1 == "Harris/Walz"].final.value_counts().astype(int).to_dict()}
    Path("label_effect.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
