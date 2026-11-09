# /// script
# dependencies = ["pandas"]
# ///
"""Panel data: Republican and Democratic side shares, every statewide race 2014-2026, by area.

Areas are defined precinct by precinct, so they cover the same places on both district maps:
  Anchorage  Municipality of Anchorage (Eagle River, Chugiak, Eklutna, Peters Creek, Girdwood in)
  Fairbanks  Fairbanks North Star Borough (North Pole, Eielson, Salcha in)
  Juneau     City and Borough of Juneau
  Cities     the three together
  Bush       every precinct of old-map HD37-40, plus the off-road Interior villages of old HD6
             (Arctic Village, Beaver, Fort Yukon, Stevens Village, Tanana, Venetie), followed by
             name into the new map
  Mat-Su     Matanuska-Susitna Borough
  Kenai      Kenai Peninsula Borough (Seward, Seldovia, Tyonek in)
  Rest of state  everything else: Kodiak, Cordova, Valdez, the Southeast towns, the road-system
             Interior, the Denali Borough

All ballots. Election-day votes are reported by precinct and go straight to the precinct's area.
Absentee / early / question votes are reported by House district: in a district lying wholly in
one area they go to that area; in a split district each candidate's district-level votes are
divided across areas in proportion to that candidate's election-day votes there (assumption:
absentee voters in a split district vote like that district's election-day voters, area by area).

Rows: the Democratic side (Gara + Walker 2022 and Hill + Hafner 2026 added together) and the
Republican side (Republicans on one ranked-choice ballot added together), plus Murkowski 2022 on
her own. Left out on the D side: 2016 and 2022 Senate (no real Democratic side).

Outliers: within each party x area panel, robust z == 0.6745 x (share - median) / MAD.
Flag |z| > 2, strong flag |z| > 3.

Writes panels.json.
"""
import json
import re

import pandas as pd

import cities as C

DIST = re.compile(r"District (\d+)")
OFFROAD_HD6 = {"Arctic Village", "Beaver", "Fort Yukon", "Stevens Village", "Tanana", "Venetie"}
# Matanuska-Susitna Borough and Kenai Peninsula Borough: (whole districts, {district: precinct names})
MATSU = {False: ({7, 8, 10, 11}, {9: {"Farm Loop", "Fishhook", "Sheep Mountain", "Sutton"},
                                  12: {"Butte", "Fairview No. 1", "Fairview No. 2", "Snowshoe"}}),
         True: ({25, 26, 27, 28}, {29: {"Farm Loop", "Fishhook", "Kings Lake", "Lakes No. 3", "Sheep Mountain", "Sutton"},
                                   30: {"Big Lake", "East Schrock", "Houston", "Knik Goose Bay No. 4", "Susitna",
                                        "Talkeetna", "Trapper Creek", "Willow"}})}
KENAI = {False: ({29, 30, 31}, {32: {"Seldovia-Kachemak Bay", "Seldovia/Kachemak Bay", "Tyonek"}}),
         True: ({6, 7, 8}, {5: {"Seward-Lowell Point"}})}
KENAI_ANYWHERE = {"Tyonek", "Seldovia-Kachemak Bay", "Seldovia/Kachemak Bay", "Seward-Lowell Point"}


def norm(label):
    return re.sub(r"\s+", " ", str(label)).strip()


def old_bush_names():
    names = set()
    for f in ["20141104", "20161108", "20181106", "20201103"]:
        d = pd.read_csv(f"{C.OE}{f}__ak__general__precinct.csv", usecols=["precinct"], dtype=str)
        for lab in d.precinct.dropna().unique():
            m = C.PRECINCT.match(norm(lab))
            if m and int(m.group(1)) in {37, 38, 39, 40}:
                names.add(m.group(2).strip())
    return names


BUSH_OLD = old_bush_names() | OFFROAD_HD6


def area_of(label, plan, new):
    """-> (kind, hd, area). kind 'precinct' or 'district'."""
    lab = norm(label)
    m = C.PRECINCT.match(lab)
    if m:
        hd, name = int(m.group(1)), m.group(2).strip()
        _, _, city = C.classify(lab, plan)
        if city != "Rest of state":
            return "precinct", hd, city
        for area, spec in [("Mat-Su", MATSU[new]), ("Kenai", KENAI[new])]:
            whole, parts = spec
            if hd in whole or name in parts.get(hd, set()):
                return "precinct", hd, area
        if name in KENAI_ANYWHERE:
            return "precinct", hd, "Kenai"
        if hd in {37, 38, 39, 40} or (not new and name in OFFROAD_HD6) or (new and hd == 36 and name in BUSH_OLD):
            return "precinct", hd, "Bush"
        return "precinct", hd, "Rest of state"
    m = DIST.search(lab)
    return "district", int(m.group(1)) if m else 99, None


def by_area(loader, year):
    """-> DataFrame area x candidate votes, all ballots, split districts allocated."""
    new = int(year) >= 2022
    plan = C.NEW if new else C.OLD
    d = C.rows(loader).copy()
    cls = d.label.map(lambda l: area_of(l, plan, new))
    d["kind"], d["hd"], d["area"] = cls.str[0], cls.str[1], cls.str[2]
    ed = d[d.kind == "precinct"]
    out = ed.groupby(["area", "candidate"]).votes.sum()
    ed_c = ed.groupby(["hd", "candidate", "area"]).votes.sum()   # candidate's election day by district x area
    ed_t = ed.groupby(["hd", "area"]).votes.sum()                 # fallback: all election-day votes
    extra = {}
    for (hd, cand), v in d[d.kind == "district"].groupby(["hd", "candidate"]).votes.sum().items():
        if v == 0:
            continue
        try:
            w = ed_c.loc[(hd, cand)]
        except KeyError:
            w = pd.Series(dtype=float)
        if w.sum() == 0:
            w = ed_t.loc[hd] if hd in ed_t.index.get_level_values(0) else pd.Series({"Rest of state": 1.0})
        w = w / w.sum()
        for area, share in w.items():
            extra[(area, cand)] = extra.get((area, cand), 0) + v * share
    ex = pd.Series(extra, dtype=float)
    if len(ex):
        ex.index = pd.MultiIndex.from_tuples(ex.index, names=["area", "candidate"])
        out = out.astype(float).add(ex, fill_value=0)
    return out.unstack(fill_value=0)


DEM_ROWS = [(r[0], r[1], r[2], r[5]) for r in C.RACES
            if (r[0], r[1]) not in {("2016", "Senate"), ("2022", "Senate")} and r[2] not in {"Gara", "Hill"}]
REP_ROWS = [(r[0], r[1], r[2], r[4]) for r in C.REPS
            if r[2] not in {"Palin", "Begich (Nick)", "Tshibaka", "Murkowski + Tshibaka", "Dunleavy/Dahlstrom",
                            "Wilson/Shower", "Bronson/Church", "Taylor/English"}
            or (r[2] == "Begich (Nick)" and r[0] != "2022")]
LABEL = {"Begich (Mark)": "Mark Begich", "Begich (Mark)/Call": "Mark Begich", "Begich (Nick)": "Nick Begich",
         "Dunleavy/Meyer": "Dunleavy", "Parnell/Sullivan": "Parnell"}
AREAS = ["Anchorage", "Fairbanks", "Juneau", "Cities", "Bush", "Mat-Su", "Kenai", "Rest of state"]


def main():
    cache, recs = {}, []
    for party, rowset in [("D", DEM_ROWS), ("R", REP_ROWS)]:
        for yr, off, label, names in rowset:
            key = (yr, off)
            if key not in cache:
                cache[key] = by_area(C.LOAD[key], yr)
            t = cache[key]
            t.loc["Cities"] = t.loc[[a for a in ["Anchorage", "Fairbanks", "Juneau"] if a in t.index]].sum()
            for area in AREAS:
                row = t.loc[area]
                v, T = float(row[[n for n in names if n in row.index]].sum()), float(row.sum())
                recs.append(dict(party=party, year=yr, office=off, cand=LABEL.get(label, label), combo=len(names) > 1,
                                 area=area, votes=round(v), total=round(T), share=round(100 * v / T, 2)))
            t = t.drop(index="Cities"); cache[key] = t
    df = pd.DataFrame(recs)
    stats = []
    for (party, area), g in df.groupby(["party", "area"]):
        med = g.share.median()
        mad = (g.share - med).abs().median()
        df.loc[g.index, "z"] = (0.6745 * (g.share - med) / mad).round(2)
        stats.append(dict(party=party, area=area, n=len(g), median=round(med, 2), mad=round(mad, 2), robust_sd=round(1.4826 * mad, 2)))
    df["flag"] = df.z.abs().map(lambda a: 2 if a > 3 else (1 if a > 2 else 0))
    json.dump(dict(rows=df.to_dict("records"), stats=stats), open("panels.json", "w"), indent=1)
    pd.set_option("display.width", 220)
    print(pd.DataFrame(stats).to_string(index=False))
    for party in ["R", "D"]:
        print("=====", party)
        print(df[df.party == party].pivot_table(index=["year", "office", "cand"], columns="area", values="share", sort=False)[AREAS].round(2).to_string())
    print("===== flagged")
    print(df[df.flag > 0][["party", "area", "year", "office", "cand", "share", "z"]].sort_values(["party", "area", "z"]).to_string(index=False))
    # checks: statewide reproduces cities.py; Bush share of state
    for key, t in cache.items():
        tot = t.sum().sum()
        print(key, "areas:", {a: round(100 * t.loc[a].sum() / tot, 1) for a in t.index})


if __name__ == "__main__":
    main()
