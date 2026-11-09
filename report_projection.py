# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2"]
# ///
"""Project the 2026 finish from the Division of Elections' Combined Ballot Report.

Uses the report's accepted/outstanding ballot counts plus the CVR's per-vote-type rates.
Ballots in hand but not counted = accepted (report) - counted (CVR).

Usage: uv run report_projection.py REPORT_HTML [CVR_2026] [--late-batch-r1 0.351] [--questioned 8000]
Writes report_projection.json.
"""
import argparse
import html
import json
import re
from pathlib import Path

import project

HERE = Path(__file__).parent
ROWS = ["MAIL", "ONLINE", "FAX", "IN-PERSON", "SPECIAL NEEDS", "ABSENTEE TOTAL", "EARLY VOTE", "QUESTIONED"]
COLS = ["accept_full", "accept_partial", "reject", "received", "undeliverable", "applications", "sent"]


def parse_report(path: Path) -> dict:
    s = path.read_text(encoding="utf-8", errors="replace")
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", s)
    tok = [t.strip() for t in html.unescape(re.sub(r"(?s)<[^>]+>", "\n", s)).split("\n") if t.strip()]
    as_of = next((re.search(r"as of:\s*(.+?)\s*\|?$", t)[1] for t in tok if t.startswith("as of:")), "")
    start = tok.index("REPORT TOTALS")
    out, j = {}, start
    for r in ROWS:
        j = tok.index(r, j)
        out[r] = dict(zip(COLS, (int(x.replace(",", "")) for x in tok[j + 1:j + 8])))
        j += 8
    return {"as_of": as_of, "totals": out}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("report", type=Path)
    ap.add_argument("cvr", type=Path, nargs="?", default=HERE / "2026-11-04_23-33_rctab_cvr.csv")
    ap.add_argument("--late-batch-r1", type=float, default=0.351, help="Begich first-choice share of ballots counted after the CVR")
    ap.add_argument("--transfer-lift", type=float, default=0.037, help="points ranked-choice transfers add to Begich's two-way share")
    ap.add_argument("--questioned", type=int, default=8000)
    ap.add_argument("--late-shift-2024", type=float, default=None, help="final-round gap, late vs early ballots, in 2024 (from flow.json)")
    args = ap.parse_args()

    rep = parse_report(args.report)
    T = rep["totals"]
    cvr = project.tally(args.cvr, None)["types"]
    keys = ["ballots", "r1_begich", "r1_active", "fin_begich", "fin_opp"]
    allc = {k: sum(v[k] for v in cvr.values()) for k in keys}
    per = lambda g: {k: g[k] / g["ballots"] for k in keys[1:]}
    early_r, abs_r, all_r = per(cvr["Early Voting"]), per(cvr["Absentee"]), per(allc)
    fin_per_ballot = (allc["fin_begich"] + allc["fin_opp"]) / allc["ballots"]
    r1_act = allc["r1_active"] / allc["ballots"]

    def fixed_share(r1: float, fin: float) -> dict:
        return {"r1_active": r1_act, "r1_begich": r1_act * r1, "fin_begich": fin_per_ballot * fin, "fin_opp": fin_per_ballot * (1 - fin)}

    late_batch = fixed_share(args.late_batch_r1, args.late_batch_r1 + args.transfer_lift)
    now_r1 = allc["r1_begich"] / allc["r1_active"]
    now_fin = allc["fin_begich"] / (allc["fin_begich"] + allc["fin_opp"])
    if args.late_shift_2024 is None:
        f = json.loads((HERE / "flow.json").read_text())["y2024"]
        a, z = f[0], f[-1]
        dr1 = (z["round1"]["Begich"] - a["round1"]["Begich"]) / (sum(z["round1"].values()) - sum(a["round1"].values())) - a["begich_r1_pct"] / 100
        dfn = (z["final"]["Begich"] - a["final"]["Begich"]) / (sum(z["final"].values()) - sum(a["final"].values())) - a["begich_final_pct"] / 100
    else:
        dr1 = dfn = args.late_shift_2024
    like_2024 = fixed_share(now_r1 + dr1, now_fin + dfn)

    counted_abs = cvr.get("Absentee", {"ballots": 0})["ballots"] + cvr.get("Overseas", {"ballots": 0})["ballots"]
    accepted_abs = T["ABSENTEE TOTAL"]["accept_full"] + T["ABSENTEE TOTAL"]["accept_partial"]
    early_rem = T["EARLY VOTE"]["accept_full"] + T["EARLY VOTE"]["accept_partial"] - cvr["Early Voting"]["ballots"]
    abs_rem = accepted_abs - counted_abs
    unreturned = sum(T[m]["sent"] - T[m]["received"] - T[m]["undeliverable"] for m in ["MAIL", "ONLINE", "FAX"])

    def run(groups):
        s = {k: allc[k] for k in keys}
        for n, r in groups:
            s["ballots"] += n
            for k in keys[1:]:
                s[k] += n * r[k]
        return {"ballots": round(s["ballots"]), "r1_pct": round(s["r1_begich"] / s["r1_active"] * 100, 2),
                "final_pct": round(s["fin_begich"] / (s["fin_begich"] + s["fin_opp"]) * 100, 2),
                "margin": round(s["fin_begich"] - s["fin_opp"])}

    scenarios = []
    for name, early, absentee in [("Vote like 2026's counted ballots of the same type", early_r, abs_r),
                                  ("Shift from the early count as much as 2024's late ballots did", like_2024, like_2024),
                                  ("Vote like the batch counted since the CVR", late_batch, late_batch)]:
        for rate in (0, 0.4, 1.0):
            u = unreturned * rate
            res = run([(early_rem, early), (abs_rem, absentee), (args.questioned, all_r), (u, absentee)])
            scenarios.append({"late": name, "unreturned_pct": int(rate * 100), **res})

    out = {"as_of": rep["as_of"], "totals": T, "counted_early": cvr["Early Voting"]["ballots"], "counted_abs": counted_abs,
           "accepted_abs": accepted_abs, "accepted_early": early_rem + cvr["Early Voting"]["ballots"],
           "early_rem": early_rem, "abs_rem": abs_rem, "unreturned": unreturned, "questioned_assumed": args.questioned,
           "late_batch_r1": args.late_batch_r1, "late_batch_final": args.late_batch_r1 + args.transfer_lift,
           "shift_2024_r1": round(dr1 * 100, 2), "shift_2024_final": round(dfn * 100, 2),
           "scenarios": scenarios}
    (HERE / "report_projection.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "totals"}, indent=1))


if __name__ == "__main__":
    main()
