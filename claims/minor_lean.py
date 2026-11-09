# Run from the repo root: uv run --with pandas python claims/<script>.py
import sys; sys.path.insert(0,'.')
import pandas as pd
import senate_minor as sm
H=sm.HERE
s=pd.read_csv(sm.SEN,dtype=str,keep_default_na=False)
fn=[sm.first_and_next(r) for r in s[sm.RANKS].itertuples(index=False)]
s["first"],s["next"]=[a for a,_ in fn],[b for _,b in fn]
x=pd.read_csv(H/"crossover_2026.csv",dtype=str,keep_default_na=False)
g=pd.read_csv(sm.GOV,usecols=["RCTab CVR Id","Rank 1"],dtype=str,keep_default_na=False)
g["gov"]=g["Rank 1"].map(lambda v:"D" if v.startswith("Kreiss") else ("R" if v.startswith(("Wilson","Bronson","Taylor")) else "o"))
m=s[["RCTab CVR Id","first","next"]].merge(x[["RCTab CVR Id","H1","SF"]],on="RCTab CVR Id").merge(g[["RCTab CVR Id","gov"]],on="RCTab CVR Id",how="left")
m["house"]=m.H1.map(lambda v:"D" if v in("Hill","Hafner") else ("R" if v=="Begich" else "o"))
def side(r):
    if r.house=="D" and r.gov=="D": return "both D"
    if r.house=="R" and r.gov=="R": return "both R"
    return "split/other"
m["side"]=m.apply(side,axis=1)
print(m.SF.value_counts())
for f in ["Sullivan Jr.","Heikes","both Sullivans"]:
    d=m[m["first"]==f]
    print("\n==",f,len(d))
    print(pd.crosstab([d.SF],d.side,margins=True))
    print(pd.crosstab([d.next],d.side,margins=True))

print("\n\n===== DEEPER: legislative races added")
L=pd.read_csv(H/"legislative_2026.csv",dtype=str)
L["d"]=(L.leg_first=="D").astype(int); L["r"]=(L.leg_first=="R").astype(int)
agg=L.groupby("RCTab CVR Id")[["d","r"]].sum()
m=m.merge(agg,left_on="RCTab CVR Id",right_index=True,how="left").fillna({"d":0,"r":0})
m["D"]=m.d+(m.house=="D")+(m.gov=="D"); m["R"]=m.r+(m.house=="R")+(m.gov=="R")
def lean(r):
    if r.D>0 and r.R==0: return "all D"
    if r.R>0 and r.D==0: return "all R"
    if r.D==0 and r.R==0: return "no party votes"
    return "D>R" if r.D>r.R else ("R>D" if r.R>r.D else "even")
m["lean"]=m.apply(lean,axis=1)
for f in ["Sullivan Jr.","Heikes"]:
    d=m[m["first"]==f]
    print("\n==",f)
    print(pd.crosstab(d.SF,d.lean,margins=True))
    dd=d[(d.SF=="Peltola")]
    print("Peltola-ending, old side x new lean"); print(pd.crosstab(dd.side,dd.lean,margins=True))
    ds=d[(d.SF=="No more rankings")]
    print("stopped, old side x new lean"); print(pd.crosstab(ds.side,ds.lean,margins=True))
print("\nparty picks available per ballot (Jr.):"); print((m[m['first']=='Sullivan Jr.'].D+m[m['first']=='Sullivan Jr.'].R).value_counts().sort_index())
