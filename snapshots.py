# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2"]
# ///
"""Track how the 2024 count moved across its snapshot exports, and set the 2026 count beside it.

Usage: uv run snapshots.py [MULTI_SNAPSHOT_2024_CSV] [CVR_2026]
The multi-snapshot file holds several 2024 exports tabulated together; Source Filepath tells them apart
(CVR_Export_YYYYMMDDhhmmss = Alaska's export time; ...\\alaska-2024 = final).
"""
import re
import sys
from pathlib import Path

import pandas as pd

from compare import load as load_2026_style  # same location/vote-type/first-choice rules

HERE = Path(__file__).parent
MULTI = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "2026-11-04_23-57_rctab_cvr.csv"
F2026 = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "2026-11-04_23-33_rctab_cvr.csv"
BEGICH = "Begich, Nick"


def snapshot_label(src: str) -> str:
    m = re.search(r"CVR_Export_(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})", src)
    return f"{m[1]}-{m[2]}-{m[3]} {m[4]}:{m[5]}" if m else "2024 final"


def load_multi(path: Path) -> pd.DataFrame:
    src = pd.read_csv(path, usecols=["Source Filepath"], dtype=str, keep_default_na=False)["Source Filepath"]
    df = load_2026_style(path)
    df["snapshot"] = src.map(snapshot_label).values
    return df


def begich_table(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    g = df.groupby(by)
    return pd.DataFrame({"ballots": g.size(), "begich_pct": g["choice"].apply(lambda s: (s == BEGICH).mean() * 100)}).round(1)


def main() -> None:
    pd.set_option("display.width", 200, "display.max_columns", 30, "display.max_rows", 200)
    multi = load_multi(MULTI)
    now = load_2026_style(F2026)
    now["snapshot"] = "2026 now"
    both = pd.concat([multi, now])
    order = sorted(multi["snapshot"].unique(), key=lambda s: (s == "2024 final", s)) + ["2026 now"]

    print("== Begich first-choice share by snapshot and vote type (all locations) ==")
    t = begich_table(both, ["snapshot", "vote_type"]).unstack("vote_type")
    t = t.reindex(order)
    tot = begich_table(both, ["snapshot"]).reindex(order)
    t[("ballots", "ALL")], t[("begich_pct", "ALL")] = tot["ballots"], tot["begich_pct"]
    print(t["ballots"].fillna(0).astype(int).to_string())
    print()
    print(t["begich_pct"].to_string())

    # Same-location comparison: 2026 now vs each 2024 snapshot, restricted to locations present in 2026.
    print("\n== Same locations as 2026 has reported: Begich share by vote type ==")
    reported = set(now["location"])
    same = both[both["location"].isin(reported)]
    s = begich_table(same, ["snapshot", "vote_type"]).unstack("vote_type").reindex(order)
    print(s["ballots"].fillna(0).astype(int).to_string())
    print()
    print(s["begich_pct"].to_string())

    # Early vote, district by district, weighted to the 2026 district mix, so the mix of districts counted can't drive the gap.
    print("\n== Early Voting: 2024 snapshot share reweighted to 2026's district mix ==")
    ev = both[both["vote_type"] == "Early Voting"]
    d = begich_table(ev, ["snapshot", "district"]).unstack("snapshot")
    w = d[("ballots", "2026 now")].fillna(0)
    w = w / w.sum()
    rows = []
    for snap in order:
        pct = d[("begich_pct", snap)]
        ok = pct.notna() & (w > 0)
        rows.append({"snapshot": snap, "early_ballots": int(d[("ballots", snap)].sum()),
                     "begich_pct_reweighted": round((pct[ok] * w[ok]).sum() / w[ok].sum(), 1)})
    print(pd.DataFrame(rows).set_index("snapshot").to_string())


if __name__ == "__main__":
    main()
