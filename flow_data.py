# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2"]
# ///
"""Build ballot-flow data (for the Sankey page) for 2026 and each 2024 snapshot.

Usage: uv run flow_data.py [OUT_JSON] [CVR_2026] [MULTI_2024]
Each dataset gets: elimination order, round-to-round links tagged with first choice, and summary numbers.
"""
import json
import sys
from collections import Counter
from pathlib import Path

import rcv

HERE = Path(__file__).parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "flow.json"
F2026 = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "2026-11-04_23-33_rctab_cvr.csv"
MULTI = Path(sys.argv[3]) if len(sys.argv) > 3 else HERE / "2026-11-04_23-57_rctab_cvr.csv"
DONE = "No more rankings"  # ran out of rankings, plus the few overvote / double-skip ballots
SNAPSHOTS_2024 = [("10 Nov", "20241110"), ("12 Nov", "20241112"), ("13 Nov", "20241113"), ("14 Nov", "20241114"), ("Final", "alaska-2024")]


def short(name: str) -> str:
    if name.startswith("inactive"):
        return DONE
    return name if name == "Write-in" else name.split(",")[0]


def build(ballots: Counter, label: str) -> dict:
    # Elimination order: drop the lowest active candidate until two remain.
    eliminated: list[str] = []
    rounds = []
    while True:
        tally = Counter()
        for b, n in ballots.items():
            tally[rcv.assign(b, set(eliminated))] += n
        active = {k: v for k, v in tally.items() if not k.startswith("inactive")}
        rounds.append({short(k): v for k, v in active.items()})
        if len(active) <= 2:
            break
        eliminated.append(min(active, key=active.get))
    finalists = [short(k) for k in rounds[-1]]

    links = Counter()
    for b, n in ballots.items():
        seq = [short(rcv.assign(b, set(eliminated[:k]))) for k in range(len(eliminated) + 1)]
        for k in range(len(seq) - 1):
            links[(k, seq[k], seq[k + 1], seq[0])] += n

    r1, fin = rounds[0], rounds[-1]
    begich_r1 = r1["Begich"] / sum(r1.values()) * 100
    begich_fin = fin["Begich"] / sum(fin.values()) * 100
    last = len(eliminated) - 1
    minors = {short(e) for e in eliminated}
    to = Counter()
    for (k, s, t, o), v in links.items():
        if k == last and o in minors:
            to[t] += v
    opp = next(f for f in finalists if f != "Begich")
    return {
        "label": label,
        "ballots": sum(ballots.values()),
        "eliminated": [short(e) for e in eliminated],
        "finalists": finalists,
        "opponent": opp,
        "round1": r1,
        "final": fin,
        "begich_r1_pct": round(begich_r1, 2),
        "begich_final_pct": round(begich_fin, 2),
        "minor_ballots": sum(to.values()),
        "minor_to_begich": to["Begich"],
        "minor_to_opp": to[opp],
        "minor_done": to[DONE],
        "links": [{"r": k, "s": s, "t": t, "o": o, "v": v} for (k, s, t, o), v in links.items()],
    }


def main() -> None:
    data = {"y2026": build(rcv.load(F2026, None), "2026 now"), "y2024": []}
    for label, key in SNAPSHOTS_2024:
        data["y2024"].append(build(rcv.load(MULTI, key), label))
    OUT.write_text(json.dumps(data))
    for d in [data["y2026"], *data["y2024"]]:
        print(f'{d["label"]:9s} ballots {d["ballots"]:>7,}  out: {d["eliminated"]}  '
              f'Begich R1 {d["begich_r1_pct"]:.2f}%  final {d["begich_final_pct"]:.2f}%  '
              f'minors {d["minor_ballots"]:,}: Begich {d["minor_to_begich"]:,} / {d["opponent"]} {d["minor_to_opp"]:,} / done {d["minor_done"]:,}  '
              f'final {d["final"]}')


if __name__ == "__main__":
    main()
