# Run from the repo root: uv run --with pandas python claims/<script>.py
import sys; sys.path.insert(0,'.')
import pandas as pd, senate_minor as sm
x=pd.read_csv(sm.HERE/"crossover_2026.csv",dtype=str,keep_default_na=False)[["RCTab CVR Id","SF","dist"]]
g=pd.read_csv(sm.GOV,usecols=["RCTab CVR Id","Rank 1"],dtype=str,keep_default_na=False)
g["gov"]=g["Rank 1"].map(lambda v:"D" if v.startswith("Kreiss") else ("R" if v.startswith(("Wilson","Bronson","Taylor")) else "o"))
m=x.merge(g[["RCTab CVR Id","gov"]],on="RCTab CVR Id")
m["rural"]=m.dist.astype(float).isin([37,38,39,40])
for r,d in m.groupby("rural"):
    P=(d.SF=="Peltola").sum(); S=(d.SF=="Sullivan").sum(); K=(d.gov=="D").sum(); R=(d.gov=="R").sum()
    ms=(P-S)/(P+S)*100; mg=(K-R)/(K+R)*100
    print("rural" if r else "other", len(d), P,S,round(ms,2), K,R,round(mg,2), round(ms-mg,2))
