# /// script
# dependencies = ["pandas"]
# ///
"""The Democrat's raw vote and share in Alaska's cities, every statewide race 2014-2026.

Cities, by precinct (consistent across the 2013 and 2021 maps):
  Anchorage == Municipality of Anchorage, Fairbanks == Fairbanks North Star Borough,
  Juneau == City and Borough of Juneau. Everything else == rest of state.

Two views:
  A. Election day, precinct level, full city definitions (precinct names like "35-582 Chena").
  B. All ballots (election day + the district-level absentee / early / question rows),
     only for House districts lying wholly inside a city, plus statewide totals.

Share == candidate votes / all votes cast for candidates in that race (minor candidates and
write-ins included; undervotes and overvotes excluded).

Sources: OpenElections precinct files 2014-2020 (external/openelections_ak/), RCTab CVR first
choices 2022 and 2024 (final counts), and the Division of Elections precinct results file for
2026 (GA_ENR_Precinct_State_of_Alaska.csv, saved 4 Nov 2026 evening, Alaska time; partial count).
Writes cities.csv and cities.json.
"""
import os
from pathlib import Path
import json
import re
import sys

import pandas as pd

OE = "external/openelections_ak/"
ENR_2026 = str(Path(os.environ.get("AK_DATA_DIR", "data")) / "GA_ENR_Precinct_State_of_Alaska.csv")

# ---- city definitions -------------------------------------------------------------------
OLD = dict(  # 2013 plan, elections 2014-2020
    Anchorage=(set(range(13, 29)), {12: {"Eklutna", "Peters Creek No. 1", "Peters Creek No. 2"}}),
    Fairbanks=(set(range(1, 6)), {6: {"Eielson", "Fox", "Moose Creek", "Salcha", "Steele Creek", "Two Rivers"}}),
    Juneau=({34}, {33: {"Douglas", "Juneau No. 1", "Juneau No. 2", "Juneau No. 3", "Lemon Creek", "North Douglas"}}),
)
NEW = dict(  # 2021 plan, elections 2022-2026
    Anchorage=(set(range(9, 25)), {}),
    Fairbanks=(set(range(31, 36)), {36: {"Goldstream No. 1", "Goldstream No. 2"}}),
    Juneau=({4}, {3: {"Auke Bay", "Lynn Canal", "Melvin Park", "Mendenhall Glacier", "Thunder Mountain"}}),
)
PRECINCT = re.compile(r"^(\d+)-\d+ (.*)$")
DISTRICT = re.compile(r"District (\d+)")


def classify(label, plan):
    """-> (kind, district, city). kind: 'precinct' (election day) or 'district' (other vote types)."""
    label = re.sub(r"\s+", " ", str(label)).strip()
    m = PRECINCT.match(label)
    if m:
        hd, name = int(m.group(1)), m.group(2).strip()
        for city, (whole, parts) in plan.items():
            if hd in whole or name in parts.get(hd, set()):
                return "precinct", hd, city
        return "precinct", hd, "Rest of state"
    m = DISTRICT.search(label)
    hd = int(m.group(1)) if m else 99
    for city, (whole, _) in plan.items():
        if hd in whole:
            return "district", hd, city
    return "district", hd, "Rest of state"


# ---- races ------------------------------------------------------------------------------
# (year, office, democratic side label, note, loader, D names, R names)
RACES = [
    ("2014", "Senate", "Begich (Mark)", "", ("oe", "20141104", "U.S. Senate"), ["Begich, Mark"], ["Sullivan, Dan"]),
    ("2014", "Governor", "Walker/Mallott", "independent with Democratic running mate (unity ticket)", ("oe", "20141104", "Governor"), ["Walker/Mallott"], ["Parnell/Sullivan"]),
    ("2014", "House", "Dunbar", "", ("oe", "20141104", "U.S. House"), ["Dunbar, Forrest"], ["Young, Don"]),
    ("2016", "President", "Clinton", "", ("oe", "20161108", "President"), ["Clinton, Hillary"], ["Trump, Donald J."]),
    ("2016", "Senate", "Metcalfe", "no real Democratic side: Stock (independent) and Miller (Libertarian) split the anti-Murkowski vote", ("oe", "20161108", "U.S. Senate"), ["Metcalfe, Ray"], ["Murkowski, Lisa"]),
    ("2016", "House", "Lindbeck", "", ("oe", "20161108", "U.S. House"), ["Lindbeck, Steve"], ["Young, Don"]),
    ("2018", "Governor", "Begich (Mark)/Call", "Walker withdrew but stayed on the ballot", ("oe", "20181106", "GOVERNOR/LT. GOVERNOR"), ["Begich/Call"], ["Dunleavy/Meyer"]),
    ("2018", "House", "Galvin", "independent, Democratic nominee", ("oe", "20181106", "U.S. House"), ["Galvin, Alyse S."], ["Young, Don"]),
    ("2020", "President", "Biden", "", ("oe", "20201103", "President"), ["Joseph R. Biden"], ["Donald J. Trump"]),
    ("2020", "Senate", "Gross", "independent, Democratic nominee", ("oe", "20201103", "U.S. Senate"), ["Al Gross"], ["Dan Sullivan"]),
    ("2020", "House", "Galvin", "independent, Democratic nominee", ("oe", "20201103", "U.S. House"), ["Alyse S. Galvin"], ["Don Young"]),
    ("2022", "House", "Peltola", "first choices", ("cvr", "2026-11-05_14-31_rctab_cvr-2022-house.csv"), ["Peltola, Mary S."], ["Palin, Sarah", "Begich, Nick"]),
    ("2022", "Senate", "Chesbro", "first choices; no real Democratic side (Murkowski took most Democrats)", ("cvr", "2026-11-05_14-32_rctab_cvr-2022-senate.csv"), ["Chesbro, Patricia R."], ["Tshibaka, Kelly C.", "Murkowski, Lisa"]),
    ("2022", "Governor", "Gara", "first choices", ("cvr", "2026-11-05_14-33_rctab_cvr-2022-governor.csv"), ["Gara/Cook"], ["Dunleavy/Dahlstrom", "Pierce/Grunwald"]),
    ("2022", "Governor", "Gara + Walker", "first choices; Walker independent", ("cvr", "2026-11-05_14-33_rctab_cvr-2022-governor.csv"), ["Gara/Cook", "Walker/Drygas"], ["Dunleavy/Dahlstrom", "Pierce/Grunwald"]),
    ("2024", "President", "Harris", "first choices", ("cvr", "2026-11-05_14-34_rctab_cvr-2024-president.csv"), ["Harris/Walz"], ["Trump/Vance"]),
    ("2024", "House", "Peltola", "first choices", ("cvr", "2026-11-04_23-29_rctab_cvr.csv"), ["Peltola, Mary S."], ["Begich, Nick"]),
    ("2026", "Senate", "Peltola", "first choices; partial count", ("enr", "U.S. Senator"), ["Peltola, Mary"], ["Sullivan, Dan S."]),
    ("2026", "Governor", "Kreiss-Tomkins", "first choices; partial count", ("enr", "Governor / Lieutenant Governor"), ["Kreiss-Tomkins/Johnson"], ["Wilson/Shower", "Bronson/Church", "Taylor/English"]),
    ("2026", "House", "Hill", "first choices; partial count; independent, Democratic-endorsed", ("enr", "U.S. Representative"), ["Hill, Bill"], ["Begich, Nick"]),
    ("2026", "House", "Hill + Hafner", "first choices; partial count", ("enr", "U.S. Representative"), ["Hill, Bill", "Hafner, Eric"], ["Begich, Nick"]),
]
NOT_VOTES = {"Registered Voters", "Times Counted", "Over Votes", "Under Votes", "Ballots Cast"}

_cache = {}


def rows(loader):
    """-> DataFrame with columns label, candidate, votes (one row per label x candidate)."""
    key = loader
    if key in _cache:
        return _cache[key]
    kind = loader[0]
    if kind == "oe":
        d = pd.read_csv(f"{OE}{loader[1]}__ak__general__precinct.csv", dtype=str)
        d = d[d.office == loader[2]]
        d = d[~d.candidate.isin(NOT_VOTES)]
        out = pd.DataFrame(dict(label=d.precinct, candidate=d.candidate, votes=pd.to_numeric(d.votes, errors="coerce").fillna(0)))
    elif kind == "cvr":
        d = pd.read_csv(loader[1], usecols=["Precinct Portion", "Rank 1"], dtype=str)
        d = d[(d["Rank 1"] != "undervote") & ~d["Rank 1"].str.contains("\n", na=True)]
        out = d.groupby(["Precinct Portion", "Rank 1"]).size().reset_index()
        out.columns = ["label", "candidate", "votes"]
    else:
        d = pd.read_csv(ENR_2026, dtype=str)
        d = d[d.Contest_title == loader[1]]
        out = pd.DataFrame(dict(label=d.Precinct_name, candidate=d.candidate_name, votes=pd.to_numeric(d.total_votes)))
    _cache[key] = out
    return out


def main():
    recs = []
    for yr, off, dname, note, loader, D, R in RACES:
        plan = OLD if int(yr) < 2022 else NEW
        d = rows(loader).copy()
        cls = d.label.map(lambda l: classify(l, plan))
        d["kind"] = cls.str[0]
        d["hd"] = cls.str[1]
        d["city"] = cls.str[2]
        d["side"] = d.candidate.map(lambda c: "D" if c in D else ("R" if c in R else "other"))

        def summarise(sub, view, group):
            t = sub.groupby("side").votes.sum()
            Dv, Rv, Ov = int(t.get("D", 0)), int(t.get("R", 0)), int(t.get("other", 0))
            T = Dv + Rv + Ov
            recs.append(dict(year=yr, office=off, dem=dname, note=note, view=view, group=group, D=Dv, R=Rv, other=Ov, total=T,
                             d_pct=round(100 * Dv / T, 2) if T else None, r_pct=round(100 * Rv / T, 2) if T else None))

        eday = d[d.kind == "precinct"]
        for city in ["Anchorage", "Fairbanks", "Juneau"]:
            summarise(eday[eday.city == city], "A election day", city)
        summarise(eday[eday.city != "Rest of state"], "A election day", "Cities (all three)")
        summarise(eday[eday.city == "Rest of state"], "A election day", "Rest of state")
        # B: all ballots in districts lying wholly inside a city
        whole = {hd for _, (w, _) in plan.items() for hd in w}
        allb = d[d.hd.isin(whole)]
        summarise(allb, "B all ballots", "Whole-city districts")
        summarise(d, "B all ballots", "Statewide")
    res = pd.DataFrame(recs)
    res.to_csv("cities.csv", index=False)
    json.dump(recs, open("cities.json", "w"), indent=1)
    pd.set_option("display.width", 250)
    for view in res.view.unique():
        print("=====", view)
        print(res[res.view == view].pivot_table(index=["year", "office", "dem"], columns="group", values="d_pct", sort=False).round(2).to_string())
    print(res[(res.view == "A election day") & (res.group == "Cities (all three)")][["year", "office", "dem", "D", "R", "other", "total", "d_pct"]].to_string(index=False))
    republicans()


# ---- Republicans: each Republican candidate, and the bloc where there were several --------
LOAD = {(r[0], r[1]): r[4] for r in RACES}
REPS = [  # (year, office, label, note, names)
    ("2014", "Senate", "Sullivan", "", ["Sullivan, Dan"]),
    ("2014", "Governor", "Parnell/Sullivan", "incumbent", ["Parnell/Sullivan"]),
    ("2014", "House", "Young", "incumbent", ["Young, Don"]),
    ("2016", "President", "Trump", "", ["Trump, Donald J."]),
    ("2016", "Senate", "Murkowski", "incumbent; Miller (Libertarian) ran to her right", ["Murkowski, Lisa"]),
    ("2016", "House", "Young", "incumbent", ["Young, Don"]),
    ("2018", "Governor", "Dunleavy/Meyer", "open seat", ["Dunleavy/Meyer"]),
    ("2018", "House", "Young", "incumbent", ["Young, Don"]),
    ("2020", "President", "Trump", "incumbent", ["Donald J. Trump"]),
    ("2020", "Senate", "Sullivan", "incumbent", ["Dan Sullivan"]),
    ("2020", "House", "Young", "incumbent", ["Don Young"]),
    ("2022", "House", "Palin", "first choices", ["Palin, Sarah"]),
    ("2022", "House", "Begich (Nick)", "first choices", ["Begich, Nick"]),
    ("2022", "House", "Palin + Begich", "first choices, both Republicans", ["Palin, Sarah", "Begich, Nick"]),
    ("2022", "Senate", "Murkowski", "first choices; incumbent; drew many Democrats", ["Murkowski, Lisa"]),
    ("2022", "Senate", "Tshibaka", "first choices", ["Tshibaka, Kelly C."]),
    ("2022", "Senate", "Murkowski + Tshibaka", "first choices, both Republicans", ["Murkowski, Lisa", "Tshibaka, Kelly C."]),
    ("2022", "Governor", "Dunleavy/Dahlstrom", "first choices; incumbent", ["Dunleavy/Dahlstrom"]),
    ("2022", "Governor", "Dunleavy + Pierce", "first choices, both Republicans", ["Dunleavy/Dahlstrom", "Pierce/Grunwald"]),
    ("2024", "President", "Trump", "first choices", ["Trump/Vance"]),
    ("2024", "House", "Begich (Nick)", "first choices", ["Begich, Nick"]),
    ("2026", "Senate", "Sullivan", "first choices; incumbent; partial count", ["Sullivan, Dan S."]),
    ("2026", "House", "Begich (Nick)", "first choices; incumbent; partial count", ["Begich, Nick"]),
    ("2026", "Governor", "Wilson/Shower", "first choices; open seat; partial count", ["Wilson/Shower"]),
    ("2026", "Governor", "Bronson/Church", "first choices; partial count", ["Bronson/Church"]),
    ("2026", "Governor", "Taylor/English", "first choices; partial count", ["Taylor/English"]),
    ("2026", "Governor", "Wilson + Bronson + Taylor", "first choices, all three Republicans; partial count", ["Wilson/Shower", "Bronson/Church", "Taylor/English"]),
]


def republicans():
    recs = []
    for yr, off, label, note, names in REPS:
        plan = OLD if int(yr) < 2022 else NEW
        d = rows(LOAD[(yr, off)]).copy()
        cls = d.label.map(lambda l: classify(l, plan))
        d["kind"], d["hd"], d["city"] = cls.str[0], cls.str[1], cls.str[2]
        d["mine"] = d.candidate.isin(names)
        whole = {hd for _, (w, _) in plan.items() for hd in w}
        eday = d[d.kind == "precinct"]
        groups = [("A election day", c, eday[eday.city == c]) for c in ["Anchorage", "Fairbanks", "Juneau"]]
        groups += [("A election day", "Cities (all three)", eday[eday.city != "Rest of state"]),
                   ("A election day", "Rest of state", eday[eday.city == "Rest of state"]),
                   ("B all ballots", "Whole-city districts", d[d.hd.isin(whole)]),
                   ("B all ballots", "Statewide", d)]
        for view, group, sub in groups:
            R, T = int(sub[sub.mine].votes.sum()), int(sub.votes.sum())
            recs.append(dict(year=yr, office=off, rep=label, note=note, view=view, group=group, R=R, total=T, r_pct=round(100 * R / T, 2) if T else None))
    res = pd.DataFrame(recs)
    res.to_csv("cities_rep.csv", index=False)
    json.dump(recs, open("cities_rep.json", "w"), indent=1)
    print("===== Republicans")
    print(res.pivot_table(index=["year", "office", "rep"], columns="group", values="r_pct", sort=False).round(2).to_string())
    print(res[(res.view == "A election day") & (res.group == "Cities (all three)")][["year", "office", "rep", "R", "total", "r_pct"]].to_string(index=False))


if __name__ == "__main__":
    main()
