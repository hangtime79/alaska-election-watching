# Run from the repo root: uv run --with pandas python claims/<script>.py
import sys; sys.path.insert(0,'.')
import pandas as pd, collections
import senate_minor as sm
H=sm.HERE
s=pd.read_csv(sm.SEN,dtype=str,keep_default_na=False)
S={"Sullivan":"Sullivan","Peltola":"Peltola","Heikes":"Heikes","Sullivan Jr.":"Jr","Write-in":"WI"}
def col(row):
    out=[]
    for v in row:
        if v=="undervote": continue
        x=("OV("+"+".join(S.get(sm.SHORT.get(n,n),n) for n in v.split("\n"))+")") if "\n" in v else S.get(sm.SHORT.get(v,v),v)
        if x not in out: out.append(x)
    return out
s["q"]=[col(r) for r in s[sm.RANKS].itertuples(index=False)]
s=s[s.q.map(lambda q: bool(q) and q[0]=="Jr")].copy()
s["seq"]=s.q.map(" > ".join)
def grp(q):
    fin=None
    for x in q[1:]:
        if x.startswith("OV"): fin="overvote"; break
        if x in("Sullivan","Peltola"): fin=x; break
    fin=fin or "stops"
    if fin=="overvote": return "overvote"
    return f"{fin}; {'ranks Sullivan' if 'Sullivan' in q else 'no Sullivan'}"
s["grp"]=s.q.map(grp)
# lean
x=pd.read_csv(H/"crossover_2026.csv",dtype=str,keep_default_na=False)[["RCTab CVR Id","H1"]]
g=pd.read_csv(sm.GOV,usecols=["RCTab CVR Id","Rank 1"],dtype=str,keep_default_na=False)
g["gov"]=g["Rank 1"].map(lambda v:"D" if v.startswith("Kreiss") else ("R" if v.startswith(("Wilson","Bronson","Taylor")) else "o"))
L=pd.read_csv(H/"legislative_2026.csv",dtype=str)
L["d"]=(L.leg_first=="D").astype(int); L["r"]=(L.leg_first=="R").astype(int)
agg=L.groupby("RCTab CVR Id")[["d","r"]].sum()
m=s.merge(x,on="RCTab CVR Id",how="left").merge(g[["RCTab CVR Id","gov"]],on="RCTab CVR Id",how="left").merge(agg,left_on="RCTab CVR Id",right_index=True,how="left").fillna({"d":0,"r":0})
m["D"]=m.d+(m.H1.isin(["Hill","Hafner"]))+(m.gov=="D"); m["R"]=m.r+(m.H1=="Begich")+(m.gov=="R")
def lean(r):
    if r.D>0 and r.R==0: return "clearly D"
    if r.R>0 and r.D==0: return "clearly R"
    if r.D>r.R: return "leans D"
    if r.R>r.D: return "leans R"
    return "even/none"
m["lean"]=m.apply(lean,axis=1)
print("TOTAL",len(m))
LE=["clearly D","leans D","even/none","leans R","clearly R"]
for gname,d in m.groupby("grp"):
    print(f"\n## {gname}  {len(d)}")
    t=pd.crosstab(d.seq,d.lean).reindex(columns=LE,fill_value=0)
    t["n"]=t.sum(axis=1); t=t.sort_values("n",ascending=False)
    print(t.to_string())
    print("  total lean:",d.lean.value_counts().reindex(LE,fill_value=0).to_dict())

print("\n===== by vote type")
vt=pd.read_csv(H/"crossover_2026.csv",dtype=str,keep_default_na=False)[["RCTab CVR Id","vt"]]
allb=vt.vt.value_counts()
m=m.merge(vt,on="RCTab CVR Id",how="left")
def cost(r):
    g=r.grp; l=r.lean
    if g.startswith("Sullivan") or g=="overvote": return (0,0)
    w=2 if g.startswith("Peltola") else 1
    if l=="clearly D": return (0,0)
    if l=="clearly R": return (w,0)
    return (0,w)
c=m.apply(cost,axis=1); m["cR"]=[a for a,_ in c]; m["cC"]=[b for _,b in c]
for t,d in m.groupby("vt"):
    n=allb[t]
    print(f"{t:15} ballots {n:7,}  Jr {len(d):5,} ({len(d)/n*100:.2f}%)  clearR/ballot {d.cR.sum()/n*1000:.2f} per1000  contested/ballot {d.cC.sum()/n*1000:.2f} per1000  clearR {d.cR.sum()} cont {d.cC.sum()}")
n=len(vt); print("ALL", n, len(m), m.cR.sum(), m.cC.sum())
