# Run from the repo root: uv run --with pandas python claims/<script>.py
import sys; sys.path.insert(0,'.')
import pandas as pd, senate_minor as sm
s=pd.read_csv(sm.SEN,dtype=str,keep_default_na=False)
fn=[sm.first_and_next(r) for r in s[sm.RANKS].itertuples(index=False)]
s["first"]=[a for a,_ in fn]
x=pd.read_csv(sm.HERE/"crossover_2026.csv",dtype=str,keep_default_na=False)[["RCTab CVR Id","vt","SF"]]
m=s[["RCTab CVR Id","first"]].merge(x,on="RCTab CVR Id")
for t,d in m.groupby("vt"):
    h=d[d["first"]=="Heikes"]
    net=((h.SF=="Peltola").sum()-(h.SF=="Sullivan").sum())
    print(t,len(d),len(h),round(len(h)/len(d)*100,2),net)
