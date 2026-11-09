# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2"]
# ///
"""Run Alaska ranked-choice rounds on an RCTab CVR export.

Usage: uv run rcv.py CVR_CSV [--snapshot SUBSTRING]
  --snapshot filters on Source Filepath (for the multi-snapshot 2024 file), e.g. --snapshot 20241110

Rules (AS 15.15.350, 6 AAC 25.072):
  - A ballot counts for its highest-ranked continuing candidate.
  - It becomes inactive on reaching an overvote (several candidates at one rank),
    on two or more sequential skipped ranks before its next continuing ranking, or when it runs out of rankings.
  - A repeated ranking of the same candidate is disregarded after the first (not counted as a skip).
  - Lowest candidate is eliminated each round; Write-in is treated as one candidate.
  - Rounds continue until two candidates remain.
"""
import argparse
from collections import Counter
from pathlib import Path

import pandas as pd

RANKS = [f"Rank {i}" for i in range(1, 6)]
OVER, SKIP = object(), object()


def load(path: Path, snapshot: str | None) -> Counter:
    cols = ["Source Filepath", *RANKS]
    df = pd.read_csv(path, usecols=cols, dtype=str, keep_default_na=False)
    if snapshot:
        df = df[df["Source Filepath"].str.contains(snapshot, regex=False)]
    def norm(r):
        if r == "undervote":
            return SKIP
        return OVER if "\n" in r else r
    return Counter(tuple(norm(r) for r in row) for row in df[RANKS].itertuples(index=False))


def assign(ranks: tuple, eliminated: set) -> str:
    """Return the continuing candidate this ballot counts for, or an inactive reason."""
    skips, seen = 0, set()
    for r in ranks:
        if r is SKIP:
            skips += 1
            continue
        if skips >= 2:
            return "inactive: skipped ranks"
        if r is OVER:
            return "inactive: overvote"
        if r in seen:
            continue
        seen.add(r)
        skips = 0
        if r not in eliminated:
            return r
    return "inactive: no more rankings"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cvr", type=Path)
    ap.add_argument("--snapshot")
    args = ap.parse_args()

    ballots = load(args.cvr, args.snapshot)
    total = sum(ballots.values())
    eliminated: set = set()
    prev: dict[tuple, str] | None = None
    print(f"{args.cvr.name}{'  [' + args.snapshot + ']' if args.snapshot else ''}: {total:,} ballots\n")

    rnd = 0
    while True:
        rnd += 1
        where = {b: assign(b, eliminated) for b in ballots}
        tally = Counter()
        for b, n in ballots.items():
            tally[where[b]] += n
        active = {k: v for k, v in tally.items() if not k.startswith("inactive")}
        inactive = {k: v for k, v in tally.items() if k.startswith("inactive")}
        n_active = sum(active.values())

        print(f"--- Round {rnd} ---")
        for cand, v in sorted(active.items(), key=lambda kv: -kv[1]):
            print(f"  {cand:32s} {v:>9,}  {v / n_active * 100:5.1f}%")
        print(f"  {'(active ballots)':32s} {n_active:>9,}")
        for k, v in sorted(inactive.items()):
            print(f"  {k:32s} {v:>9,}")

        if prev is not None:
            moved = Counter()
            for b, n in ballots.items():
                if prev[b] == just_out:
                    moved[where[b]] += n
            out_n = sum(moved.values())
            print(f"  Transfers from {just_out} ({out_n:,} ballots):")
            for k, v in moved.most_common():
                print(f"    -> {k:30s} {v:>9,}  {v / out_n * 100:5.1f}%")
        print()

        if len(active) <= 2:
            break
        just_out = min(active, key=active.get)
        eliminated.add(just_out)
        prev = where


if __name__ == "__main__":
    main()
