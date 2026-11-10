"""Party-label effect, like for like (run after label_effect.py; same inputs).
1. Stop rate of Democratic Hafner voters: 2026 (alternative an independent, Hill) against 2024 (alternative a
   Democrat, Peltola). 2026 'Democratic' == Senate first choice Peltola and governor Kreiss-Tomkins;
   2024 'Democratic' == president Harris. Both: ballots Hafner held when he was eliminated.
2. Otherwise-Republican voters drawn by each 2026 Democratic-side candidate on the same ballots: first-choice
   voters whose first choices in the other two statewide races were both Republican-side.
Run: uv run --with pandas python claims/label_effect2.py   (writes label_effect2.json)
"""
import json, sys
import pandas as pd
sys.path.insert(0, "claims"); sys.path.insert(0, ".")
from label_effect import load, ranked, final_rounds, R
import cvr2026  # noqa: E402
NAME = lambda v: v.split(",")[0].split("/")[0]
out = {}
h = load(cvr2026.HOUSE); s = load(cvr2026.SENATE); g = load(cvr2026.GOVERNOR)
first = lambda d: [next((NAME(v.split("\n")[0]) if "\n" not in v else "overvote" for v in r if v != "undervote"), "blank") for r in d[R].itertuples(index=False)]
h["H1"] = first(h); s["S1"] = first(s); g["G1"] = first(g)
s["S1x"] = [next((v for v in r if v != "undervote"), "blank") for r in s[R].itertuples(index=False)]
rounds = final_rounds(h, ["Write-in", 'McDermott, James C. "Jim"', "Hafner, Eric"])
h["at_hafner"] = pd.Series(rounds[1]) == "Hafner, Eric"
h["final"] = pd.Series(rounds[2]).map(lambda x: "stops" if x.startswith("inactive") else NAME(x))
m = h[["RCTab CVR Id", "H1", "at_hafner", "final"]].merge(s[["RCTab CVR Id", "S1", "S1x"]], on="RCTab CVR Id", how="left").merge(g[["RCTab CVR Id", "G1"]], on="RCTab CVR Id", how="left")
GR = {"Wilson", "Bronson", "Taylor"}; SR = {"Sullivan", "Heikes"}  # Sullivan Jr. parses as "Sullivan" via NAME
d = m[m.at_hafner & (m.S1 == "Peltola") & (m.G1 == "Kreiss-Tomkins")]
out["hafner_D_2026"] = {"n": len(d), "final": d.final.value_counts().astype(int).to_dict()}
# otherwise-Republican first-choice voters for each Democratic-side candidate
hR = m.H1.isin(["Begich"]); sR = m.S1.isin(SR); gR = m.G1.isin(GR)
out["otherwise_R"] = {
  "Hill (House)": {"voters": int((m.H1 == "Hill").sum()), "other_two_R": int(((m.H1 == "Hill") & sR & gR).sum())},
  "Peltola (Senate)": {"voters": int((m.S1 == "Peltola").sum()), "other_two_R": int(((m.S1 == "Peltola") & hR & gR).sum())},
  "Kreiss-Tomkins (governor)": {"voters": int((m.G1 == "Kreiss-Tomkins").sum()), "other_two_R": int(((m.G1 == "Kreiss-Tomkins") & hR & sR).sum())}}
sD = m.S1x == "Sullivan, Dan S."
out["otherwise_R_strict"] = {
  "Hill (House): Senate Dan Sullivan + R governor": {"voters": int((m.H1 == "Hill").sum()), "n": int(((m.H1 == "Hill") & sD & gR).sum())},
  "Peltola (Senate): Begich + R governor": {"voters": int((m.S1 == "Peltola").sum()), "n": int(((m.S1 == "Peltola") & hR & gR).sum())},
  "Kreiss-Tomkins (governor): Begich + Senate Dan Sullivan": {"voters": int((m.G1 == "Kreiss-Tomkins").sum()), "n": int(((m.G1 == "Kreiss-Tomkins") & hR & sD).sum())}}
json.dump(out, open("label_effect2.json", "w"), indent=1); print(json.dumps(out, indent=1))
