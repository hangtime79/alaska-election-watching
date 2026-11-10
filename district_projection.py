# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2"]
# ///
"""District-by-district projection of the 2026 House and Senate final rounds.

Why: the Division of Elections counts absentee ballots district by district. On 4 Nov the CVR's absentees came
from 25 districts and none from HD8-16, 18; the 9 Nov export added HD9-16 and 18 (Anchorage, Hill +33 against +8 for
the earlier absentees, and no gap between old and new ballots inside any district). A statewide "vote like the
counted ballots of the same type" rate therefore depends on which districts happen to be counted. This script
projects each district's remaining ballots from that district's own counted ballots.

Remaining, per House district, from the Combined Ballot Report (accepted full + partial) minus the CVR:
  early      accepted early - CVR early                        x district early rate
  absentee   accepted absentee - CVR absentee                  x district absentee rate
  unreturned (sent - received - undeliverable), mail/online/fax x district absentee rate x arrival share (0/40/100%)
  questioned accepted questioned (none are in the CVR yet)     x district all-ballot rate
Judicial-split CVR rows (HD30, 36, 37, 39: mixed early/absentee/questioned) are taken off early first, then absentee.
Rates are final-round net and two-way votes per ballot (Alaska's rules, from crossover_2026.csv). A district with
fewer than MIN counted ballots of a type borrows its election-day rate plus the median within-district gap
(early - election day, absentee - early) from districts that have both. HD99 (overseas) uses the overseas rate.
The rural election-day batch (official count, not in the CVR) comes from revised_projection.json.

Model B adds Peltola's 2024 late-against-early gaps (late_2024.py, district-weighted) to the early and absentee
two-way votes, as house_check.py does.

Sign convention: D positive (Hill - Begich, Peltola - Sullivan).
Usage: uv run district_projection.py [REPORT_HTML]   (default combined-ballot-report-20261109.html)
Writes district_projection.json.
"""
import html
import json
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
REPORT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "combined-ballot-report-20261109.html"
MIN = 100
GAP_EARLY, GAP_ABS = 0.0641, -0.1035
RACES = {"House": ("HF", "Hill", "Begich"), "Senate": ("SF", "Peltola", "Sullivan")}
METHODS = ["MAIL", "ONLINE", "FAX", "IN-PERSON", "SPECIAL NEEDS", "ABSENTEE TOTAL", "EARLY VOTE", "QUESTIONED"]


def parse(path: Path) -> tuple[str, dict]:
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", path.read_text(encoding="utf-8", errors="replace"))
    tok = [t.strip() for t in html.unescape(re.sub(r"(?s)<[^>]+>", "\n", s)).split("\n") if t.strip()]
    as_of = next(re.search(r"as of:\s*(.+?)\s*\|?$", t)[1] for t in tok if t.startswith("as of:"))
    out = {}
    for i, t in enumerate(tok):
        m = re.match(r"HOUSE DISTRICT (\d+)$", t)
        if m:
            j, d = i, {}
            for r in METHODS:
                j = tok.index(r, j)
                d[r] = [int(x.replace(",", "")) for x in tok[j + 1:j + 8]]
                j += 8
            out[int(m[1])] = d
    return as_of, out


def remaining(rep: dict, x: pd.DataFrame) -> dict:
    """Ballots still to count per district: accepted (report) minus counted (CVR). x needs dist (int) and vt."""
    cnt = x.groupby(["dist", "vt"]).size().unstack(fill_value=0)
    rem = {}
    for d, r in rep.items():
        acc = lambda k: r[k][0] + r[k][1]
        c = cnt.loc[d] if d in cnt.index else pd.Series(dtype=int)
        e = acc("EARLY VOTE") - int(c.get("Early Voting", 0))
        a = acc("ABSENTEE TOTAL") - int(c.get("Absentee", 0)) - int(c.get("Overseas", 0))
        js = int(c.get("Judicial-split", 0))
        take = min(js, max(e, 0)); e -= take; a -= min(js - take, max(a, 0))
        unret = sum(r[k][6] - r[k][3] - r[k][4] for k in ["MAIL", "ONLINE", "FAX"])
        rem[d] = {"early": max(e, 0), "absentee": max(a, 0), "unreturned": max(unret, 0), "questioned": acc("QUESTIONED")}
    return rem


def district_rates(x: pd.DataFrame, net: str, two: str, districts) -> dict:
    """Per district (net, two) per ballot for early, absentee and questioned (all-ballot) remaining ballots.
    A type with fewer than MIN counted ballots in a district borrows the district's election-day rate (early) or
    early rate (absentee) plus the median within-district gap from districts that have both."""
    g = x.groupby(["dist", "vt"]).agg(n=(net, "size"), net=(net, "mean"), two=(two, "mean"))
    allr = x.groupby("dist").agg(net=(net, "mean"), two=(two, "mean"))

    def rate(d, vt):
        return (g.loc[(d, vt), "net"], g.loc[(d, vt), "two"]) if (d, vt) in g.index and g.loc[(d, vt), "n"] >= MIN else None

    def gap(a_vt, b_vt):
        L = [(rate(d, a_vt)[0] - rate(d, b_vt)[0], rate(d, a_vt)[1] - rate(d, b_vt)[1]) for d in districts if rate(d, a_vt) and rate(d, b_vt)]
        return float(pd.Series([v[0] for v in L]).median()), float(pd.Series([v[1] for v in L]).median())
    gap_e, gap_a = gap("Early Voting", "Election Day"), gap("Absentee", "Early Voting")
    ovs = x[x.vt == "Overseas"]
    ov = (ovs[net].mean(), ovs[two].mean())
    out, borrowed = {}, {"early": [], "absentee": []}
    for d in sorted(districts):
        if d == 99:
            out[d] = {"early": ov, "absentee": ov, "questioned": ov}
            continue
        ed = rate(d, "Election Day") or (allr.loc[d, "net"], allr.loc[d, "two"])
        er = rate(d, "Early Voting")
        if er is None:
            er = (ed[0] + gap_e[0], ed[1] + gap_e[1]); borrowed["early"].append(d)
        ar = rate(d, "Absentee")
        if ar is None:
            ar = (er[0] + gap_a[0], er[1] + gap_a[1]); borrowed["absentee"].append(d)
        out[d] = {"early": er, "absentee": ar, "questioned": (allr.loc[d, "net"], allr.loc[d, "two"])}
    return {"rates": out, "borrowed": borrowed}


def parts(rem: dict, rates: dict) -> dict:
    """Statewide (net, two) for each remaining group; unreturned is for 100% arrival (scale it)."""
    P = {k: [0.0, 0.0] for k in ["early", "absentee", "unreturned", "questioned"]}
    for d, R in rem.items():
        r = rates[d]
        for k, rk in [("early", "early"), ("absentee", "absentee"), ("unreturned", "absentee"), ("questioned", "questioned")]:
            P[k][0] += R[k] * r[rk][0]; P[k][1] += R[k] * r[rk][1]
    return {k: tuple(v) for k, v in P.items()}


def project(P: dict, counted: float, u: float, model: str) -> dict:
    n = {k: P[k][0] * (u if k == "unreturned" else 1) for k in P}
    t = {k: P[k][1] * (u if k == "unreturned" else 1) for k in P}
    gapB = t["early"] * GAP_EARLY + (t["absentee"] + t["unreturned"]) * GAP_ABS if model == "B" else 0.0
    rn, rt = sum(n.values()) + gapB, sum(t.values())
    tot = counted + rn
    return {"model": model, "unreturned_pct": int(u * 100), "parts_net": {k: round(v) for k, v in n.items()},
            "parts_two": {k: round(v) for k, v in t.items()}, "gapB": round(gapB), "remaining_net": round(rn),
            "remaining_two": round(rt), "remaining_margin_pct": round(rn / rt * 100, 2), "total_net": round(tot),
            "flip_shift_pts": round(-tot / rt * 100, 2)}


def main() -> None:
    as_of, rep = parse(REPORT)
    x = pd.read_csv(HERE / "crossover_2026.csv", dtype=str, keep_default_na=False)
    x["dist"] = x["dist"].astype(int)
    rev = json.loads((HERE / "revised_projection.json").read_text())
    out = {"report": REPORT.name, "as_of": as_of, "min_ballots": MIN, "races": {}}
    rem = remaining(rep, x)
    out["remaining"] = {k: sum(v[k] for v in rem.values()) for k in ["early", "absentee", "unreturned", "questioned"]}
    for race, (col, dem, rep_) in RACES.items():
        x["net"] = (x[col] == dem).astype(int) - (x[col] == rep_).astype(int)
        x["two"] = x[col].isin([dem, rep_]).astype(int)
        dr = district_rates(x, "net", "two", rem)
        P = parts(rem, dr["rates"])
        cvr_net = int(x.net.sum())
        batch = rev["races"][race]["batch_net"]
        counted = cvr_net + batch
        scen = [project(P, counted, u, mdl) for mdl in ("A", "B") for u in (0, 0.4, 1.0)]
        out["races"][race] = {"dem": dem, "rep": rep_, "cvr_net": cvr_net, "batch_net": batch, "counted_net": counted,
                              "borrowed": dr["borrowed"], "scenarios": scen,
                              "by_district": [{"dist": d, **rem[d], "abs_margin_pct": round(r["absentee"][0] / r["absentee"][1] * 100, 1),
                                               "early_margin_pct": round(r["early"][0] / r["early"][1] * 100, 1)}
                                              for d, r in dr["rates"].items()]}
        print(f"== {race} ({dem} - {rep_})  CVR {cvr_net:+,}  batch {batch:+,}  counted {counted:+,}   borrowed rates: {dr['borrowed']}")
        for s in scen:
            print(f"   Model {s['model']} unreturned {s['unreturned_pct']:>3}%: remaining {s['remaining_net']:+,} ({s['remaining_margin_pct']:+.2f} on {s['remaining_two']:,})"
                  f" -> total {s['total_net']:+,}; flips if remaining shift {s['flip_shift_pts']:+.2f} pts")
    print("remaining ballots:", out["remaining"])
    (HERE / "district_projection.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
