"""2024 House late-against-early gaps for every snapshot cut, plus questioned ballots against all ballots.

Same method as late_2024.py (final-round side, within-district gap weighted by late two-way ballots), with the
"early" set being ballots already in each 2024 export (10, 12, 13, 14 Nov). 2026 had counted about 18% of its
absentees on 4 Nov, so the cut whose counted-absentee share is nearest 18% is the closest match.
Run from the repo root: uv run --with pandas python claims/late_2024_snapshots.py   (writes late_2024_snapshots.json)
"""
import json, re, sys
import pandas as pd
sys.path.insert(0, "claims")
from late_2024 import side, F, RANKS

df = pd.read_csv(F, usecols=["Source Filepath", "RCTab CVR Id", "Precinct Portion", *RANKS], dtype=str, keep_default_na=False)
src = df["Source Filepath"]
fin = df[src.str.endswith("alaska-2024")].copy()
loc = fin["Precinct Portion"].str.replace(r"\s+", " ", regex=True).str.strip()
fin["district"] = loc.str.extract(r"^(?:House District |District |HD)?(\d+)", expand=False).astype(float)
fin["vt"] = loc.map(lambda s: "Election Day" if re.match(r"^\d+-\d+ ", s) else "Judicial-split" if "Judicial District" in s else s.split(" - ")[-1] if " - " in s else s)
fin["side"] = fin[RANKS].apply(lambda r: side(list(r)), axis=1)
def marg(x):
    p, b = (x.side == "P").sum(), (x.side == "B").sum()
    return int(p), int(b), ((p - b) / (p + b) * 100 if p + b else float("nan"))
out = {"cuts": {}}
for snap in ["20241110", "20241112", "20241113", "20241114"]:
    ids = set(df.loc[src.str.contains(snap), "RCTab CVR Id"])
    fin["inS"] = fin["RCTab CVR Id"].isin(ids)
    res = {}
    for vt in ["Early Voting", "Absentee"]:
        d = fin[fin.vt == vt]
        pi, bi, mi = marg(d[d.inS]); po, bo, mo = marg(d[~d.inS])
        rows = []
        for dist, g in d.groupby("district"):
            a, b_ = g[g.inS], g[~g.inS]
            if len(a) == 0 or len(b_) == 0: continue
            p2, b2, mb = marg(b_)
            rows.append((p2 + b2, mb - marg(a)[2]))
        w = sum(r[0] for r in rows)
        res[vt] = {"share_counted": round(d.inS.mean() * 100, 1), "early_margin": round(mi, 2), "late_margin": round(mo, 2),
                   "late_two": int(po + bo), "raw_gap": round(mo - mi, 2),
                   "gap": round(sum(r[0] * r[1] for r in rows) / w, 2) if w else None, "districts": len(rows)}
    out["cuts"][snap] = res
    print(snap, res)
p, b, ma = marg(fin); pq, bq, mq = marg(fin[fin.vt == "Question"])
out["question"] = {"all_margin": round(ma, 2), "question_margin": round(mq, 2), "question_two": int(pq + bq), "gap": round(mq - ma, 2)}
print(out["question"])
json.dump(out, open("late_2024_snapshots.json", "w"), indent=1)
