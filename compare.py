# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2"]
# ///
"""Compare the partial 2026 count with 2024, using only locations that have reported in 2026.

Usage: uv run compare.py [CVR_2024] [CVR_2026]
Writes by_district.csv and by_location.csv next to this script.
"""
import re
import sys
from pathlib import Path

import pandas as pd
import cvr2026

HERE = Path(__file__).parent
F2024 = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "2026-11-04_23-29_rctab_cvr.csv"
F2026 = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / cvr2026.HOUSE
RANKS = [f"Rank {i}" for i in range(1, 6)]


def first_choice(row) -> str:
    """The first rank that isn't blank. If it has several names, call it an overvote."""
    for r in row:
        if r == "undervote":
            continue
        return "Overvote" if "\n" in r else r
    return "Blank"


def load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, usecols=["Precinct Portion", *RANKS], dtype=str, keep_default_na=False)
    loc = df["Precinct Portion"].str.replace(r"\s+", " ", regex=True).str.strip()
    out = pd.DataFrame({"location": loc})
    out["district"] = loc.str.extract(r"^(?:House District |District |HD)?(\d+)", expand=False).astype(int)
    out["vote_type"] = loc.map(
        lambda s: "Election Day" if re.match(r"^\d+-\d+ ", s)
        else "Judicial-split (mixed)" if "Judicial District" in s
        else s.split(" - ")[-1] if " - " in s else s
    )
    out["choice"] = df[RANKS].apply(first_choice, axis=1, raw=True)
    return out


def shares(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    t = pd.crosstab([df[c] for c in by], df["choice"]) if by else df["choice"].value_counts().to_frame().T
    return t.div(t.sum(axis=1), axis=0).mul(100).round(1).assign(ballots=t.sum(axis=1))


def main() -> None:
    a, b = load(F2024), load(F2026)
    reported = set(b["location"])
    a_same = a[a["location"].isin(reported)]
    pd.set_option("display.width", 200, "display.max_columns", 20, "display.max_rows", 100)

    missing = sorted(reported - set(a["location"]))
    print(f"2026 ballots so far: {len(b):,}  in {len(reported)} locations")
    print(f"2024 ballots in those same locations: {len(a_same):,}  (2024 total {len(a):,})")
    print(f"2026 ballots / 2024 ballots, same locations: {len(b) / len(a_same):.0%}")
    if missing:
        print(f"2026 locations with no 2024 match ({len(missing)}): {missing}")

    print("\n== First-choice share (%), same locations ==")
    overall = pd.concat(
        {"2024 all": shares(a, []), "2024 same locations": shares(a_same, []), "2026 so far": shares(b, [])}
    ).droplevel(1).fillna(0)
    print(overall.to_string())

    print("\n== By vote type ==")
    print(pd.concat({"2024": shares(a_same, ["vote_type"]), "2026": shares(b, ["vote_type"])}).fillna(0).to_string())

    # Begich ran both years, so his share is the like-for-like line.
    def begich(df, by):
        g = df.groupby(by)
        return pd.DataFrame({"ballots": g.size(), "begich_pct": g["choice"].apply(lambda s: (s == "Begich, Nick").mean() * 100)})

    d = begich(a_same, "district").join(begich(b, "district"), lsuffix="_2024", rsuffix="_2026", how="right")
    d["begich_change_pts"] = d["begich_pct_2026"] - d["begich_pct_2024"]
    d["counted_vs_2024"] = (d["ballots_2026"] / d["ballots_2024"] * 100).round(0)
    d = d.round(1)
    print("\n== Begich first-choice share by House district, same locations ==")
    print(d.to_string())
    d.to_csv(HERE / "by_district.csv")

    loc = begich(a_same, "location").join(begich(b, "location"), lsuffix="_2024", rsuffix="_2026", how="right")
    loc["begich_change_pts"] = loc["begich_pct_2026"] - loc["begich_pct_2024"]
    loc.round(1).sort_values("begich_change_pts").to_csv(HERE / "by_location.csv")


if __name__ == "__main__":
    main()
