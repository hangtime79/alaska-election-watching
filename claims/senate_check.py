# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2"]
# ///
"""Senate count check (Peltola against Sullivan): every number on page/senate_claims.html.

Run from the repo root: uv run claims/senate_check.py   (writes senate_check.json)
Needs crossover_2026.csv (crossover.py), legislative_2026.csv (legislative.py), revised_projection.json (revised.py)
and the Combined Ballot Report named in district_projection.py.

Sign convention: D positive (Peltola - Sullivan).

Parts
  walk1    Senate rounds (Alaska rules, rcv.assign), plus the rural election-day batch in the official count but not
           in the CVR (cross_race rates, as revised.py).
  sort     Every Sullivan Jr. first-choice ballot (first marked choice) by where the count sends it and by the same
           voter's lean down the ticket (US House, governor, state House, state Senate): clearly D, contested
           (leans D, even or none, leans R), clearly R. Grant's rules, 8 Nov.
  groups   Net as counted for the Sullivan Jr. and Heikes first-choice ballots, and both-Sullivans overvotes.
  proj     Remaining ballots by district (district_projection.py), Model A and Model B; confusion carried to the
           ballots not yet visible at each vote type's rates; Trump's method on the projected final; sensitivity.
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, ".")
import cross_race as cr  # noqa: E402
import cvr2026  # noqa: E402
import district_projection as dp  # noqa: E402
import rcv  # noqa: E402

HERE = Path(".")
SEN = HERE / cvr2026.SENATE
GOV = HERE / cvr2026.GOVERNOR
REPORT = HERE / "combined-ballot-report-20261109.html"
REL = HERE / "release_20261104_1309.json"
SHORT = {"Sullivan, Dan S.": "Sullivan", "Peltola, Mary": "Peltola", "Heikes, Gerald L.": "Heikes",
         "Sullivan, Daniel J. Jr.": "Sullivan Jr.", "Write-in": "Write-in"}
U = 0.4


def norm(v):
    return rcv.SKIP if v == "undervote" else (rcv.OVER if "\n" in v else v)


def first_marked(row):
    for v in row:
        if v == "undervote":
            continue
        if "\n" in v:
            names = set(v.split("\n"))
            return "both Sullivans" if names == {"Sullivan, Dan S.", "Sullivan, Daniel J. Jr."} else "overvote"
        return SHORT.get(v, v)
    return "blank"


def seq(row):
    out = []
    for v in row:
        if v == "undervote":
            continue
        x = "OV" if "\n" in v else SHORT.get(v, v)
        if x not in out:
            out.append(x)
        if x == "OV":
            break
    return out


def jr_group(q):
    for x in q[1:]:
        if x == "OV":
            return "overvote"
        if x in ("Sullivan", "Peltola"):
            if x == "Sullivan":
                return "sullivan_ahead"
            return "below_peltola" if "Sullivan" in q else "to_peltola"
    return "stops"


def main():
    out = {}
    s = pd.read_csv(SEN, usecols=["RCTab CVR Id", "Precinct Portion", *rcv.RANKS], dtype=str, keep_default_na=False)
    t = [tuple(norm(v) for v in r) for r in s[rcv.RANKS].itertuples(index=False)]

    # ---------- walk 1 ----------
    elim, order, rounds, holders = set(), [], [], []
    while True:
        cur = pd.Series([rcv.assign(x, elim) for x in t])
        holders.append(cur)
        tally = cur.value_counts()
        active = {k: int(v) for k, v in tally.items() if not k.startswith("inactive")}
        rounds.append({"active": {SHORT[k]: v for k, v in active.items()},
                       "inactive": int(tally[[k for k in tally.index if k.startswith("inactive")]].sum())})
        if len(active) <= 2:
            break
        c = min(active, key=active.get); elim.add(c); order.append(SHORT[c])
    steps = []
    for i, c in enumerate(order):
        a, b = rounds[i]["active"], rounds[i + 1]["active"]
        held = holders[i].map(lambda v: SHORT.get(v, v)) == c
        dest = holders[i + 1][held].map(lambda v: SHORT.get(v, "stops" if v.startswith("inactive") else v)).value_counts()
        steps.append({"out": c, "ballots": int(held.sum()), "to": {k: int(v) for k, v in dest.items()},
                      "net": (b["Peltola"] - a["Peltola"]) - (b["Sullivan"] - a["Sullivan"])})
    r1, rf = rounds[0]["active"], rounds[-1]["active"]
    walk = {"ballots": len(s), "rounds": rounds, "order": order, "steps": steps,
            "first_net": r1["Peltola"] - r1["Sullivan"], "cvr_final_net": rf["Peltola"] - rf["Sullivan"],
            "cvr_two": rf["Peltola"] + rf["Sullivan"]}
    s["fin"] = holders[-1].map(lambda v: SHORT.get(v, "stops")).values

    # rural batch (as revised.py)
    m = cr.load()
    rel = json.loads(REL.read_text())["senate"]["Election Day"]
    ed = m[m.vt == "Election Day"]
    batch = (pd.Series(rel, dtype=float) - cr.choices(ed, cr.SOURCES["senate"]).reindex(list(rel)).fillna(0)).clip(lower=0)
    bnet, btwo = cr.predict(batch, cr.rates(ed, cr.SOURCES["senate"]), "SF")
    walk["batch"] = {"first_choices": int(batch.sum()), "by": {k: int(v) for k, v in batch.items()},
                     "shares": {k: round(v / batch.sum() * 100, 1) for k, v in batch.items()},
                     "net": round(bnet), "two": round(btwo), "margin": round(bnet / btwo, 4)}
    counted = walk["cvr_final_net"] + bnet
    walk["counted"] = round(counted)
    out["walk1"] = walk

    # ---------- first-choice groups and the Sullivan Jr. sort ----------
    s["first"] = [first_marked(r) for r in s[rcv.RANKS].itertuples(index=False)]
    s["q"] = [seq(r) for r in s[rcv.RANKS].itertuples(index=False)]
    x = pd.read_csv(HERE / "crossover_2026.csv", dtype=str, keep_default_na=False)
    g = pd.read_csv(GOV, usecols=["RCTab CVR Id", "Rank 1"], dtype=str, keep_default_na=False)
    g["gov"] = g["Rank 1"].map(lambda v: "D" if v.startswith("Kreiss") else ("R" if v.startswith(("Wilson", "Bronson", "Taylor")) else "o"))
    L = pd.read_csv(HERE / "legislative_2026.csv", dtype=str)
    L["d"] = (L.leg_first == "D").astype(int); L["r"] = (L.leg_first == "R").astype(int)
    leg = L.groupby("RCTab CVR Id")[["d", "r"]].sum()
    s = s.merge(x[["RCTab CVR Id", "vt", "dist", "H1", "SF"]], on="RCTab CVR Id", how="left") \
         .merge(g[["RCTab CVR Id", "gov"]], on="RCTab CVR Id", how="left") \
         .merge(leg, left_on="RCTab CVR Id", right_index=True, how="left").fillna({"d": 0, "r": 0, "gov": "o"})
    s["D"] = s.d + s.H1.isin(["Hill", "Hafner"]) + (s.gov == "D")
    s["R"] = s.r + (s.H1 == "Begich") + (s.gov == "R")
    s["lean"] = ["D" if (a > 0 and b == 0) else "R" if (b > 0 and a == 0) else "C" for a, b in zip(s.D, s.R)]
    s["net"] = (s.SF == "Peltola").astype(int) - (s.SF == "Sullivan").astype(int)
    fc = {k: {"n": int(len(gg)), "peltola": int((gg.SF == "Peltola").sum()), "sullivan": int((gg.SF == "Sullivan").sum()),
              "stops": int((gg.SF == "No more rankings").sum()), "net": int(gg.net.sum())}
          for k, gg in s.groupby("first")}
    out["first_choice"] = fc
    jr = s[s["first"] == "Sullivan Jr."].copy()
    jr["grp"] = jr.q.map(jr_group)
    sort = {gname: {"n": int(len(gg)), **{k: int((gg.lean == k).sum()) for k in "DCR"}} for gname, gg in jr.groupby("grp")}
    out["sort"] = sort
    jr["lean5"] = ["D" if (a > 0 and b == 0) else "R" if (b > 0 and a == 0) else "LD" if a > b else "LR" if b > a else "E"
                   for a, b in zip(jr.D, jr.R)]
    jr["order"] = jr.q.map(lambda q: " > ".join("Jr" if v == "Sullivan Jr." else "WI" if v == "Write-in" else "overvote" if v == "OV" else v for v in q))
    out["orders"] = [{"grp": gp, "order": od, "n": int(len(gg)), **{k: int((gg.lean5 == k).sum()) for k in ("D", "LD", "E", "LR", "R")}}
                     for (gp, od), gg in jr.groupby(["grp", "order"])]
    W = {"below_peltola": 2, "to_peltola": 2, "stops": 1}
    cost = {lean: {gname: -W[gname] * sort[gname][lean] for gname in W} for lean in "RCD"}
    both = fc.get("both Sullivans", {"n": 0})["n"]
    cR, cC, cD = (sum(cost[k].values()) for k in "RCD")
    out["confusion_counted"] = {"R": cR, "R_parts": cost["R"], "both": -both, "C": cC, "C_parts": cost["C"], "D": cD, "D_parts": cost["D"],
                                "clearly_R_total": round(counted) + cR, "plus_both": round(counted) + cR - both,
                                "broad": round(counted) + cR - both + cC, "stress": round(counted) + cR - both + cC + cD}

    # rates by vote type for the ballots not yet visible
    jr["cR"] = [W.get(gp, 0) if ln == "R" else 0 for gp, ln in zip(jr.grp, jr.lean)]
    jr["cC"] = [W.get(gp, 0) if ln == "C" else 0 for gp, ln in zip(jr.grp, jr.lean)]
    allb = s.vt.value_counts()
    hk = s[s["first"] == "Heikes"]
    rate = {}
    for vt in ["Election Day", "Early Voting", "Absentee"]:
        n = int(allb[vt]); j = jr[jr.vt == vt]; h = hk[hk.vt == vt]
        rate[vt] = {"ballots": n, "jr": len(j), "jr_share": len(j) / n, "R_per_1000": j.cR.sum() / n * 1000, "C_per_1000": j.cC.sum() / n * 1000,
                    "heikes": len(h), "heikes_share": len(h) / n, "heikes_net": int(h.net.sum()), "heikes_net_per": h.net.sum() / len(h)}
    n = len(s)
    rate["All"] = {"ballots": n, "jr": len(jr), "jr_share": len(jr) / n, "R_per_1000": jr.cR.sum() / n * 1000, "C_per_1000": jr.cC.sum() / n * 1000,
                   "heikes": len(hk), "heikes_share": len(hk) / n, "heikes_net": int(hk.net.sum()), "heikes_net_per": hk.net.sum() / len(hk)}
    jr_net_per = jr.net.sum() / len(jr)

    # ---------- projection by district ----------
    as_of, report = dp.parse(REPORT)
    xd = x.assign(dist=x.dist.astype(int))
    xd["net"] = (xd.SF == "Peltola").astype(int) - (xd.SF == "Sullivan").astype(int)
    xd["two"] = xd.SF.isin(["Peltola", "Sullivan"]).astype(int)
    rem = dp.remaining(report, xd)
    tot = {k: sum(v[k] for v in rem.values()) for k in ["early", "absentee", "unreturned", "questioned"]}
    dr = dp.district_rates(xd, "net", "two", rem)
    P = dp.parts(rem, dr["rates"])
    sc = {f"{mdl}{int(u * 100)}": dp.project(P, counted, u, mdl) for mdl in ("A", "B") for u in (0, U, 1.0)}
    A, B = sc["A40"]["total_net"], sc["B40"]["total_net"]
    two = sc["A40"]["remaining_two"]

    # unseen ballots: the rural batch plus every remaining ballot
    batch_n = int(batch.sum())
    unseen = [("rural", batch_n, rate["Election Day"], batch.get("Sullivan Jr.", 0) / batch_n, batch.get("Heikes", 0) / batch_n),
              ("early", tot["early"], rate["Early Voting"], None, None),
              ("absentee", tot["absentee"] + round(tot["unreturned"] * U), rate["Absentee"], None, None),
              ("questioned", tot["questioned"], rate["All"], None, None)]
    rows, uR, uC, ujr, uh, uhe = [], 0.0, 0.0, 0.0, 0.0, 0.0
    for name, nb, r, jsh, hsh in unseen:
        jsh = r["jr_share"] if jsh is None else jsh
        hsh = r["heikes_share"] if hsh is None else hsh
        R_, C_ = nb * r["R_per_1000"] / 1000, nb * r["C_per_1000"] / 1000
        jn, hn = nb * jsh, nb * hsh
        he = hn * (1 + r["heikes_net_per"])
        rows.append({"name": name, "ballots": nb, "jr_share": round(jsh * 100, 2), "jr": round(jn), "R_per_1000": round(r["R_per_1000"], 2),
                     "C_per_1000": round(r["C_per_1000"], 2), "R": -round(R_), "C": -round(C_), "heikes_share": round(hsh * 100, 2),
                     "heikes": round(hn), "heikes_net": r["heikes_net"], "heikes_n": r["heikes"], "heikes_net_per": round(r["heikes_net_per"], 3),
                     "heikes_extra": round(1 + r["heikes_net_per"], 3), "heikes_effect": -round(he)})
        uR += R_; uC += C_; ujr += jn; uh += hn; uhe += he
    unseen_n = sum(r["ballots"] for r in rows)
    ub = unseen_n * both / n
    hard = ujr * (1 + jr_net_per)
    cc = out["confusion_counted"]
    broad = A + cR - both + cC - uR - ub - uC
    stress = broad + cD - (hard - (uR + ub + uC))
    jr_counted = -(len(jr) + int(jr.net.sum()))
    he_counted = -(len(hk) + int(hk.net.sum()))
    trump = A + jr_counted - hard + he_counted - uhe
    gapB = sc["B40"]["gapB"]
    proj = {"report": REPORT.name, "as_of": as_of, "remaining": tot, "borrowed": dr["borrowed"], "counted": round(counted),
            "scenarios": sc, "A": A, "B": B, "gapB": gapB, "two": two,
            "unseen": {"rows": rows, "ballots": unseen_n, "R": -round(uR), "C": -round(uC), "both": -round(ub), "jr": round(ujr),
                       "hard": -round(hard), "jr_net_per": round(jr_net_per, 4), "heikes": round(uh), "heikes_effect": -round(uhe)},
            "broad": round(broad), "stress": round(stress), "stress_rest": -round(hard - (uR + ub + uC)),
            "trump": {"jr_counted": jr_counted, "jr_unseen": -round(hard), "heikes_counted": he_counted, "heikes_unseen": -round(uhe),
                      "total": round(trump), "jr_only": round(A + jr_counted - hard), "heikes_only": round(A + he_counted - uhe)},
            "B_rows": {"rules": B, "broad": round(broad + gapB), "stress": round(stress + gapB), "trump": round(trump + gapB)}}
    raw = sc["A40"]["parts_two"]["early"] * 0.0767 + (sc["A40"]["parts_two"]["absentee"] + sc["A40"]["parts_two"]["unreturned"]) * (-0.0816)
    proj["gapB_raw"] = round(raw)
    proj["sens"] = {str(k): {"rules": round(A + two * k / 100), "broad": round(broad + two * k / 100), "stress": round(stress + two * k / 100)}
                    for k in (5, 2.5, 0, -2.5, -5, -7.5, -10, -15, -20)}
    proj["flip"] = {k: round(v / (two / 100), 1) for k, v in (("rules", A), ("broad", broad), ("stress", stress))}
    proj["flip_B"] = {k: round(v / (two / 100), 1) for k, v in (("rules", B), ("broad", broad + gapB), ("stress", stress + gapB))}
    out["proj"] = proj
    print(json.dumps({"walk1": {k: walk[k] for k in ("first_net", "cvr_final_net", "counted")}, "batch": walk["batch"],
                      "steps": steps, "sort": sort, "conf": cc, "fc": {k: fc[k] for k in ("Sullivan", "Peltola", "Sullivan Jr.", "Heikes", "both Sullivans")},
                      "proj": {k: proj[k] for k in ("A", "B", "gapB", "gapB_raw", "two", "broad", "stress", "stress_rest", "trump", "B_rows", "flip", "flip_B")},
                      "unseen": proj["unseen"]}, indent=1, default=float))
    Path("senate_check.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
