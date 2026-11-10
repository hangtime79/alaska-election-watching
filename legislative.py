# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2"]
# ///
"""Hill against a near-generic Democrat: the state legislative races on the same 2026 ballots.

Reads the Dominion CVR export folder directly (CvrExport_*.json, CandidateManifest.json,
ContestManifest.json) and takes each ballot's first choice in its state House and state Senate
contest. Uses the adjudicated ("Modified") card when there is one, as RCTab does. A first choice is the
lowest-ranked mark with IsVote; two candidates at that rank is an overvote.

Legislative candidates are low-profile, so their party label is the closest thing on the ballot to a
generic Democrat or Republican. Only contests with at least one Democrat and one Republican are used;
"clean" contests have exactly one of each and nobody else.

Joins to crossover_2026.csv on RCTab CVR Id ({TabulatorId}-{BatchId}-{RecordId}) and prints, for each
US House first-choice group (Hill, Hafner, Begich, McDermott) and for Peltola and Kreiss-Tomkins voters,
how they voted in their legislative race. Writes legislative_2026.csv (one row per ballot and contest).

Usage: uv run legislative.py [DOMINION_FOLDER]
"""
import os
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import cvr2026

HERE = Path(__file__).parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.environ.get("AK_DATA_DIR", "data")) / cvr2026.DOMINION


def party_sides(src: Path) -> dict:
    """PartyId -> "D" / "R" / "other", by party name (ids differ between years)."""
    out = {}
    for p in json.loads((src / "PartyManifest.json").read_text())["List"]:
        d = p["Description"]
        out[p["Id"]] = "D" if "Democrat" in d else ("R" if "Republican" in d else "other")
    return out


def leg_first(src: Path) -> pd.DataFrame:
    """One row per ballot and state legislative contest: the first choice's party side, plus whether the
    contest had a Democrat and a Republican (contested) and nobody else (clean). Party comes from the
    ballot marks, so it works for exports whose CandidateManifest has no Affiliations (2022)."""
    contests = {c["Id"]: c["Description"] for c in json.loads((src / "ContestManifest.json").read_text())["List"]}
    leg = {i: d for i, d in contests.items() if d.startswith(("House District", "Senate District"))}
    side = party_sides(src)
    regular = {c["Id"] for c in json.loads((src / "CandidateManifest.json").read_text())["List"] if c.get("Type", "Regular") == "Regular"}
    field = defaultdict(dict)  # contest -> regular (non-write-in) candidate -> side
    rows = []
    for f in sorted(src.glob("CvrExport*.json")):
        for s in json.loads(f.read_text())["Sessions"]:
            card_set = s.get("Modified") or s["Original"]
            bid = f'{s["TabulatorId"]}-{s["BatchId"]}-{s["RecordId"]}'
            for card in card_set["Cards"]:
                for c in card["Contests"]:
                    if c["Id"] not in leg:
                        continue
                    marks = [m for m in c["Marks"] if m.get("IsVote")]
                    for m in marks:
                        if m["CandidateId"] in regular:
                            field[c["Id"]][m["CandidateId"]] = side.get(m.get("PartyId"), "other")
                    if not marks:
                        first = "blank"
                    else:
                        top = min(m.get("Rank", 1) for m in marks)
                        at = [m for m in marks if m.get("Rank", 1) == top]
                        first = "overvote" if len({m["CandidateId"] for m in at}) > 1 else side.get(at[0].get("PartyId"), "other")
                    rows.append((bid, c["Id"], leg[c["Id"]], first))
    L = pd.DataFrame(rows, columns=["RCTab CVR Id", "contest", "contest_name", "leg_first"])
    sides = {i: sorted(v.values()) for i, v in field.items()}
    L["contested"] = L.contest.map(lambda i: "D" in sides.get(i, []) and "R" in sides.get(i, []))
    L["clean"] = L.contest.map(lambda i: sides.get(i, []) == ["D", "R"])
    return L


def main() -> None:
    L = leg_first(SRC)
    L.to_csv(HERE / "legislative_2026.csv", index=False)

    x = pd.read_csv(HERE / "crossover_2026.csv", dtype=str, keep_default_na=False)
    g = pd.read_csv(HERE / cvr2026.GOVERNOR, usecols=["RCTab CVR Id", "Rank 1"], dtype=str, keep_default_na=False)
    g["G1"] = g["Rank 1"].str.split("/").str[0]
    m = L.merge(x[["RCTab CVR Id", "H1", "S1"]], on="RCTab CVR Id").merge(g[["RCTab CVR Id", "G1"]], on="RCTab CVR Id", how="left")
    print(f"Legislative contest-ballots {len(L):,}; matched to the House CVR {len(m):,}")
    print(f"Clean one-Democrat, one-Republican contests: {sorted(L[L.clean].contest_name.unique())}")
    groups = {
        "Hill first (House)": m.H1 == "Hill",
        "  Hill first, Peltola + Kreiss-Tomkins": (m.H1 == "Hill") & (m.S1 == "Peltola") & (m.G1 == "Kreiss-Tomkins"),
        "  Hill first, not straight D": (m.H1 == "Hill") & ~((m.S1 == "Peltola") & (m.G1 == "Kreiss-Tomkins")),
        "Hafner first (House)": m.H1 == "Hafner",
        "Begich first (House)": m.H1 == "Begich",
        "McDermott first (House)": m.H1 == "McDermott",
        "Peltola first (Senate)": m.S1 == "Peltola",
        "Kreiss-Tomkins first (governor)": m.G1 == "Kreiss-Tomkins",
    }
    for label, sub in [("contested D and R", m.contested), ("clean one D, one R", m.clean)]:
        d = m[sub]
        print(f"\n== Legislative first choice, {label} contests ({d['RCTab CVR Id'].nunique():,} ballots, {len(d):,} contest-ballots)")
        out = []
        for gname, mask in groups.items():
            t = d[mask[sub]].leg_first.value_counts()
            n = t.sum()
            voted = t.get("D", 0) + t.get("R", 0) + t.get("other", 0)
            out.append({"group": gname, "contest-ballots": n,
                        "D": t.get("D", 0), "R": t.get("R", 0), "other": t.get("other", 0), "blank/over": n - voted,
                        "D % of votes": round(t.get("D", 0) / voted * 100, 1) if voted else None,
                        "R % of votes": round(t.get("R", 0) / voted * 100, 1) if voted else None})
        print(pd.DataFrame(out).to_string(index=False))


if __name__ == "__main__":
    main()
