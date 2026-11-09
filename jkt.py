# /// script
# dependencies = ["pandas"]
# ///
"""Kreiss-Tomkins (JKT): his own vote against the statewide Democrats on the same ballots.

2014-2020: JKT ran for state House, old HD35 (Sitka, Petersburg, Prince of Wales, the
Southeast villages), each time one Democrat against one Republican, as the incumbent.
For each year: two-bloc margin (D - R) / (D + R) x 100 on all HD35 ballots (precincts plus the
district's absentee / early / question rows) for JKT and for every statewide race.
JKT premium == JKT margin - the statewide Democrat's margin on the same ballots.

2026: JKT for governor. Same comparison in new HD2 (the old HD35 area; Sitka, Petersburg,
Prince of Wales, Hoonah, Kake, Angoon, Yakutat) and statewide, against Peltola (Senate) and
Hill + Hafner (House). 2026 is the 4 Nov partial count.
Writes jkt.json.
"""
import json
import re

import pandas as pd

import cities as C

OLD_RACES = {  # year: [(label, office in OpenElections file, D names, R names)]
    "2014": [("Mark Begich / Senate", "U.S. Senate", ["Begich, Mark"], ["Sullivan, Dan"]),
             ("Walker/Mallott / Governor", "Governor", ["Walker/Mallott"], ["Parnell/Sullivan"]),
             ("Dunbar / House", "U.S. House", ["Dunbar, Forrest"], ["Young, Don"])],
    "2016": [("Clinton / President", "President", ["Clinton, Hillary"], ["Trump, Donald J."]),
             ("Lindbeck / House", "U.S. House", ["Lindbeck, Steve"], ["Young, Don"])],
    "2018": [("Mark Begich / Governor", "GOVERNOR/LT. GOVERNOR", ["Begich/Call"], ["Dunleavy/Meyer"]),
             ("Galvin / House", "U.S. House", ["Galvin, Alyse S."], ["Young, Don"])],
    "2020": [("Biden / President", "President", ["Joseph R. Biden"], ["Donald J. Trump"]),
             ("Gross / Senate", "U.S. Senate", ["Al Gross"], ["Dan Sullivan"]),
             ("Galvin / House", "U.S. House", ["Alyse S. Galvin"], ["Don Young"])],
}
FILES = {"2014": "20141104", "2016": "20161108", "2018": "20181106", "2020": "20201103"}
JKT_OFFICE = {"2014": "State House", "2016": "State House", "2018": "State House", "2020": "House District 35"}
DIST = re.compile(r"District (\d+)")


def hd(label):
    lab = re.sub(r"\s+", " ", str(label)).strip()
    m = C.PRECINCT.match(lab)
    if m:
        return int(m.group(1))
    m = DIST.search(lab)
    return int(m.group(1)) if m else 99


def margin(sub, D, R):
    dv, rv = sub[sub.candidate.isin(D)].votes.sum(), sub[sub.candidate.isin(R)].votes.sum()
    return dict(D=int(dv), R=int(rv), margin=round(100 * (dv - rv) / (dv + rv), 2))


def main():
    out = []
    for yr, f in FILES.items():
        d = pd.read_csv(f"{C.OE}{f}__ak__general__precinct.csv", dtype=str)
        d["votes"] = pd.to_numeric(d.votes, errors="coerce").fillna(0)
        d["hd"] = d.precinct.map(hd)
        d = d[d.hd == 35]
        j = d[d.office == JKT_OFFICE[yr]]
        if yr != "2020":
            j = j[j.district.astype(str).str.strip().isin(["35", "35.0"])]
        jd = [c for c in j.candidate.unique() if "Kreiss" in str(c)]
        jr = [c for c in j[j.party == "REP"].candidate.unique()] or [c for c in j.candidate.unique() if c not in jd and c not in C.NOT_VOTES and "Write" not in str(c)]
        jm = margin(j, jd, jr)
        out.append(dict(year=yr, area="old HD35", race="JKT / State House", **jm, premium=None))
        for label, off, D, R in OLD_RACES[yr]:
            m = margin(d[d.office == off], D, R)
            out.append(dict(year=yr, area="old HD35", race=label, **m, premium=round(jm["margin"] - m["margin"], 2)))
    # 2026: new HD2 and statewide
    e = pd.read_csv(C.ENR_2026, dtype=str)
    e["votes"] = pd.to_numeric(e.total_votes)
    e = e.rename(columns={"candidate_name": "candidate"})
    e["hd"] = e.Precinct_name.map(hd)
    races26 = [("JKT / Governor", "Governor / Lieutenant Governor", ["Kreiss-Tomkins/Johnson"], ["Wilson/Shower", "Bronson/Church", "Taylor/English"]),
               ("Peltola / Senate", "U.S. Senator", ["Peltola, Mary"], ["Sullivan, Dan S."]),
               ("Hill + Hafner / House", "U.S. Representative", ["Hill, Bill", "Hafner, Eric"], ["Begich, Nick"])]
    for area, sub in [("new HD2", e[e.hd == 2]), ("Statewide", e)]:
        res = {lab: margin(sub[sub.Contest_title == off], D, R) for lab, off, D, R in races26}
        jm = res["JKT / Governor"]["margin"]
        for lab, m in res.items():
            out.append(dict(year="2026", area=area, race=lab, **m, premium=None if lab.startswith("JKT") else round(jm - m["margin"], 2)))
    df = pd.DataFrame(out)
    pd.set_option("display.width", 200)
    print(df.to_string(index=False))
    json.dump(out, open("jkt.json", "w"), indent=1)


if __name__ == "__main__":
    main()
