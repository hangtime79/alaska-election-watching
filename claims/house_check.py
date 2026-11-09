# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2"]
# ///
"""House count check (Begich against Hill): every number on page/house_check.html.

Run from the repo root: uv run claims/house_check.py   (writes house_check.json)

Sign convention: D positive (Hill - Begich). Hill is the Democratic side.

Parts
  walk1      House rounds from the 4 Nov CVR (Alaska rules, rcv.assign), then the rural election-day batch in the
             official count but not the CVR, read two ways: statewide election-day transfer rates (revised.py) and
             rural (HD37-40) election-day rates.
  minors     Every Hafner and McDermott ranking order, where each ballot ends up, and the same ballots' Senate final
             round, governor first choice and legislative first choices.
  rows       Three readings of the final round, each projected to the final count:
               as_counted  Alaska's rules.
               stopped     stopped House ballots continue to their Senate final-round side (Hill's ceiling, one side).
               both        stopped ballots continue AND Hill voters a Democrat would not get come out (Grant's
                           definition, 6 Nov: Senate first choice not Peltola, or governor blank / write-in / overvote).
             Model A: late ballots vote like counted CVR ballots of the same type. Model B: Model A plus the 2024
             late-against-early gaps (late_2024.py, same race, Begich in both) on the early and absentee two-way votes.
  scenarios  data-backed scenarios each side; sensitivity grid.
"""
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, ".")
import rcv  # noqa: E402

HERE = Path(".")
HOUSE = HERE / "2026-11-04_23-33_rctab_cvr.csv"
GOV = HERE / "2026-11-05_14-36_rctab_cvr-2026-governor.csv"
RANKS = rcv.RANKS
SHORT = {"Begich, Nick": "Begich", "Hill, Bill": "Hill", "Hafner, Eric": "Hafner",
         'McDermott, James C. "Jim"': "McDermott", "Write-in": "Write-in"}
GAP_EARLY, GAP_ABS = 0.0641, -0.1035      # late_2024.py, district-weighted (Senate page, same script)
GAP_EARLY_RAW, GAP_ABS_RAW = 0.0767, -0.0816


def norm(v):
    return rcv.SKIP if v == "undervote" else (rcv.OVER if "\n" in v else v)


def main():
    out = {}
    h = pd.read_csv(HOUSE, usecols=["RCTab CVR Id", *RANKS], dtype=str, keep_default_na=False)
    h["t"] = [tuple(norm(v) for v in r) for r in h[RANKS].itertuples(index=False)]

    # ---------- walk 1: rounds ----------
    elim, order, rounds = set(), [], []
    holder_by_round = []
    while True:
        cur = h.t.map(lambda t: rcv.assign(t, elim))
        holder_by_round.append(cur)
        tally = cur.value_counts()
        active = {k: int(v) for k, v in tally.items() if not k.startswith("inactive")}
        rounds.append({"active": {SHORT[k]: v for k, v in active.items()},
                       "inactive": int(tally[[k for k in tally.index if k.startswith("inactive")]].sum())})
        if len(active) <= 2:
            break
        out_c = min(active, key=active.get)
        elim.add(out_c); order.append(SHORT[out_c])
    steps = []
    for i, c in enumerate(order):
        a, b = rounds[i]["active"], rounds[i + 1]["active"]
        prev_held = holder_by_round[i].map(lambda x: SHORT.get(x, x)) == c
        dest = holder_by_round[i + 1][prev_held].map(lambda x: SHORT.get(x, "stops" if x.startswith("inactive") else x)).value_counts()
        steps.append({"out": c, "ballots": int(prev_held.sum()), "to": {k: int(v) for k, v in dest.items()},
                      "net": (b["Hill"] - a["Hill"]) - (b["Begich"] - a["Begich"])})
    r1 = rounds[0]["active"]; rf = rounds[-1]["active"]
    walk = {"rounds": rounds, "order": order, "steps": steps,
            "first_net": r1["Hill"] - r1["Begich"], "cvr_final_net": rf["Hill"] - rf["Begich"],
            "ballots": len(h)}
    h["HFr"] = holder_by_round[-1].map(lambda x: SHORT.get(x, "stops"))
    print("first", walk["first_net"], [(s["out"], s["net"]) for s in steps], "final", walk["cvr_final_net"])

    # ---------- per-ballot frame ----------
    x = pd.read_csv(HERE / "crossover_2026.csv", dtype=str, keep_default_na=False)
    g = pd.read_csv(GOV, usecols=["RCTab CVR Id", "Rank 1"], dtype=str, keep_default_na=False)

    def gv(v):
        if v in ("", "undervote"): return "blank"
        if "\n" in v: return "overvote"
        if v.startswith("Kreiss"): return "Kreiss-Tomkins"
        return "Republican" if v.startswith(("Wilson", "Bronson", "Taylor")) else "write-in"
    g["gov"] = g["Rank 1"].map(gv)
    L = pd.read_csv(HERE / "legislative_2026.csv", dtype=str)
    L["d"] = (L.leg_first == "D").astype(int); L["r"] = (L.leg_first == "R").astype(int)
    leg = L.groupby("RCTab CVR Id")[["d", "r"]].sum()
    m = h.merge(x, on="RCTab CVR Id", how="left").merge(g[["RCTab CVR Id", "gov"]], on="RCTab CVR Id", how="left") \
         .merge(leg, left_on="RCTab CVR Id", right_index=True, how="left").fillna({"d": 0, "r": 0, "gov": "no race (overseas federal ballot)"})
    assert (m.HFr.replace({"stops": "No more rankings"}) == m.HF).all(), "final round mismatch with crossover"
    m["dist"] = pd.to_numeric(m.dist, errors="coerce")
    m["sen"] = m.SF.map(lambda s: "Peltola" if s == "Peltola" else ("Sullivan" if s == "Sullivan" else "none"))
    m["legside"] = m.apply(lambda r: "D" if r.d > 0 and r.r == 0 else ("R" if r.r > 0 and r.d == 0 else ("both" if r.r > 0 else "none")), axis=1)

    # three final-round readings
    hf = m.HF.map({"Hill": 1, "Begich": -1}).fillna(0)
    sf = m.sen.map({"Peltola": 1, "Sullivan": -1, "none": 0})
    cont = hf.where(hf != 0, sf)
    grant = (m.HF == "Hill") & ((m.S1 != "Peltola") | m.gov.isin(["blank", "write-in", "overvote"]))
    protest = grant & m.S1.isin(["Sullivan Jr.", "Heikes"]) & (m.gov == "Kreiss-Tomkins")
    both = cont.where(~grant, 0)
    both_np = cont.where(~(grant & ~protest), 0)
    sym = (m.HF == "Hill") & (m.sen == "Sullivan")   # same test as the stopped side: Senate final round
    both_sym = cont.where(~sym, 0)
    V = {"as_counted": hf, "stopped": cont, "both": both, "both_no_protest": both_np, "both_symmetric": both_sym}
    for k, s in V.items():
        m[k + "_net"] = s; m[k + "_two"] = s.abs()
    hill_adj = {"stopped": int((hf == 0).sum()), "stopped_to_hill": int(((hf == 0) & (sf == 1)).sum()),
                "stopped_to_begich": int(((hf == 0) & (sf == -1)).sum()), "stopped_none": int(((hf == 0) & (sf == 0)).sum()),
                "grant_set": int(grant.sum()), "symmetric_set": int(sym.sum()), "protest": int(protest.sum()),
                "grant_by": {f"{a} | {b}": int(n) for (a, b), n in m[grant].groupby(["S1", "gov"]).size().items()},
                "cvr_net": {k: int(s.sum()) for k, s in V.items()}, "cvr_two": {k: int(s.abs().sum()) for k, s in V.items()}}
    # where the stopped ballots came from
    hb3 = holder_by_round[-2].map(lambda x: SHORT.get(x, "earlier"))
    hill_adj["stopped_from"] = {k: int(v) for k, v in hb3[hf == 0].value_counts().items()}
    print("hill adj", hill_adj["cvr_net"])

    # ---------- minors: every ranking order ----------
    def seq(t):
        o = []
        for v in t:
            if v is rcv.SKIP: continue
            s = "overvote" if v is rcv.OVER else SHORT.get(v, v)
            if s not in o: o.append(s)
            if s == "overvote": break
        return o
    m["seq"] = m.t.map(seq)
    minors = {}
    for cand, rnd_idx in (("Hafner", order.index("Hafner")), ("McDermott", order.index("McDermott"))):
        held = holder_by_round[rnd_idx].map(lambda x: SHORT.get(x, x)) == cand
        d = m[held].copy()
        d["dest"] = d.HFr
        # order after cand: drop names before cand, keep the rest
        d["after"] = d.seq.map(lambda q: " > ".join(q[q.index(cand):]) if cand in q else "?")
        d["first"] = d.seq.map(lambda q: q[0] if q else "")
        rows = []
        for (after, dest), gg in d.groupby(["after", "dest"]):
            rows.append({"order": after, "dest": dest, "n": len(gg),
                         "first_other": int((gg["first"] != cand).sum()),
                         "sen": gg.sen.value_counts().reindex(["Peltola", "Sullivan", "none"], fill_value=0).astype(int).to_dict(),
                         "gov": gg.gov.value_counts().reindex(["Kreiss-Tomkins", "Republican", "blank", "write-in", "overvote"], fill_value=0).astype(int).to_dict(),
                         "leg": gg.legside.value_counts().reindex(["D", "R", "both", "none"], fill_value=0).astype(int).to_dict()})
        rows.sort(key=lambda r: -r["n"])
        def summ(gg):
            return {"n": len(gg), "sen": gg.sen.value_counts().reindex(["Peltola", "Sullivan", "none"], fill_value=0).astype(int).to_dict(),
                    "gov": gg.gov.value_counts().reindex(["Kreiss-Tomkins", "Republican", "blank", "write-in", "overvote"], fill_value=0).astype(int).to_dict(),
                    "leg": gg.legside.value_counts().reindex(["D", "R", "both", "none"], fill_value=0).astype(int).to_dict(),
                    "vt": gg.vt.value_counts().astype(int).to_dict(),
                    "rural": int((gg.dist >= 37).sum())}
        minors[cand] = {"held": int(held.sum()), "first_choice": int((d["first"] == cand).sum()),
                        "dest": {k: summ(gg) for k, gg in d.groupby("dest")}, "orders": rows}
        # only-ranked-cand (no other name anywhere)
        only = d[d.seq.map(lambda q: q == [cand])]
        minors[cand]["only"] = summ(only)
        # all Hafner/McDermott voters' House rank structure
        print(cand, "held", minors[cand]["held"], {k: v["n"] for k, v in minors[cand]["dest"].items()}, "only", len(only))
    # Senate comparison for context: Hill and Begich final-round voters' Senate final round
    ctx = {}
    for k in ("Hill", "Begich"):
        gg = m[m.HF == k]
        ctx[k] = {"n": len(gg), "sen": gg.sen.value_counts().reindex(["Peltola", "Sullivan", "none"], fill_value=0).astype(int).to_dict(),
                  "gov": gg.gov.value_counts().reindex(["Kreiss-Tomkins", "Republican", "blank", "write-in", "overvote"], fill_value=0).astype(int).to_dict()}
    minors["context"] = ctx

    # ---------- projection ----------
    R = json.loads((HERE / "report_projection.json").read_text())
    rel = json.loads((HERE / "release_20261104_1309.json").read_text())["house"]["Election Day"]
    ed = m[m.vt == "Election Day"]
    rural_ed = ed[ed.dist >= 37]
    cvr_ed_fc = ed.H1.value_counts()
    batch = (pd.Series(rel, dtype=float) - cvr_ed_fc.reindex(list(rel)).fillna(0)).clip(lower=0)

    def read_batch(src, key):
        r = src.groupby("H1")[[key + "_net", key + "_two"]].mean().reindex(batch.index).fillna(0)
        return float((batch * r[key + "_net"]).sum()), float((batch * r[key + "_two"]).sum()), \
               {c: round(float(r.loc[c, key + "_net"]), 4) for c in batch.index}

    by_vt = lambda key: {vt: (gg[key + "_net"].mean(), gg[key + "_two"].mean()) for vt, gg in m.groupby("vt")}
    allrate = lambda key: (m[key + "_net"].mean(), m[key + "_two"].mean())
    proj = {"inputs": {"early_rem": R["early_rem"], "abs_rem": R["abs_rem"], "unreturned": R["unreturned"],
                       "questioned": R["questioned_assumed"], "batch": {k: int(v) for k, v in batch.items()},
                       "rural_ed_ballots": len(rural_ed)}, "rows": {}}
    for key in V:
        bnet, btwo, brate = read_batch(ed, key)
        rnet_, rtwo_, rrate = read_batch(rural_ed, key)
        cnet, ctwo = float(m[key + "_net"].sum()) + bnet, float(m[key + "_two"].sum()) + btwo
        bv = by_vt(key); ar = allrate(key)
        sc = []
        for u in (0, 0.4, 1.0):
            parts = {"early": (R["early_rem"], bv["Early Voting"]), "absentee": (R["abs_rem"], bv["Absentee"]),
                     "unreturned": (R["unreturned"] * u, bv["Absentee"]), "questioned": (R["questioned_assumed"], ar)}
            pn = {k: n * a for k, (n, (a, b)) in parts.items()}
            pt = {k: n * b for k, (n, (a, b)) in parts.items()}
            rnet, rtwo = sum(pn.values()), sum(pt.values())
            e2, a2 = pt["early"], pt["absentee"] + pt["unreturned"]
            gapB = e2 * GAP_EARLY + a2 * GAP_ABS
            gapBraw = e2 * GAP_EARLY_RAW + a2 * GAP_ABS_RAW
            A = cnet + rnet
            sc.append({"u": int(u * 100), "parts_net": {k: round(v) for k, v in pn.items()},
                       "parts_two": {k: round(v) for k, v in pt.items()}, "remaining_net": round(rnet),
                       "remaining_two": round(rtwo), "early_two": round(e2), "abs_two": round(a2),
                       "gapB": round(gapB), "gapB_raw": round(gapBraw), "A": round(A), "B": round(A + gapB),
                       "B_raw": round(A + gapBraw), "flipA": round(-A / rtwo * 100, 2), "flipB": round(-(A + gapB) / rtwo * 100, 2)})
        proj["rows"][key] = {"cvr_net": int(m[key + "_net"].sum()), "cvr_two": int(m[key + "_two"].sum()),
                             "batch_net": round(bnet), "batch_two": round(btwo), "batch_rate": brate,
                             "batch_net_rural": round(rnet_), "batch_rate_rural": rrate,
                             "counted": round(cnet), "counted_two": round(ctwo),
                             "rates": {vt: [round(a, 4), round(b, 4)] for vt, (a, b) in bv.items()}, "all_rate": [round(ar[0], 4), round(ar[1], 4)],
                             "sc": sc}
        print(key, "counted", round(cnet), [(s["u"], s["A"], s["B"]) for s in sc], "batch rural", round(rnet_), "vs", round(bnet))

    # ---------- scenarios ----------
    ov = m[m.vt == "Overseas"]
    ov_rate = (ov.as_counted_net.mean(), ov.as_counted_two.mean())
    scen = {"overseas": {"counted": len(ov), "net": int(ov.as_counted_net.sum()), "two": int(ov.as_counted_two.sum()),
                         "rate": [round(ov_rate[0], 4), round(ov_rate[1], 4)], "vol_2024": 398}}
    out.update(walk1=walk, hill_adj=hill_adj, minors=minors, proj=proj, scen=scen)
    (HERE / "house_check.json").write_text(json.dumps(out, indent=1, default=int))


if __name__ == "__main__":
    main()
